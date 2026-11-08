"""Opt-in four-way detail worker using existing fenced player persistence.

A node-local flock reserves the Battlelog IP for the complete burst. Other
persona/report workers continue using guarded_request and cannot interleave.
"""
import fcntl
import json
import logging
import os
import time
from datetime import datetime, timezone

from bf4br import node_cooldown
from bf4br.detail_batch import DEFAULT_BATCH_SIZE, DEFAULT_COOLDOWN_SECONDS
from bf4br.detail_burst import run_burst
from bf4br.detail_fetch import fetch_detail
from bf4br.detail_queue import claim_player, renew_player, retry_player, save_player
from bf4br.retry import retry_delay, retry_after_seconds

LOG = logging.getLogger(__name__)


def _publish_429(result):
    hint = result[3]
    _, minimum = node_cooldown.policy_values()
    seconds = max(minimum, retry_after_seconds(hint, cap=86400) or 0)
    now = time.time()
    try:
        state = json.loads(node_cooldown.STATE.read_text())
    except (OSError, ValueError):
        state = {}
    state.update(until_epoch=max(float(state.get('until_epoch', 0)), now + seconds),
                 last_request_epoch=now, status=429, retry_after=hint,
                 cooldown_seconds=seconds, updated_at=datetime.now(timezone.utc).isoformat())
    path = node_cooldown.STATE
    tmp = path.with_name(path.name + '.tmp.' + str(os.getpid()))
    tmp.write_text(json.dumps(state))
    os.replace(tmp, path)
    LOG.warning('detail burst HTTP 429; node cooldown %.1f seconds', seconds)


def process_batch(conn, worker, *, stopped=lambda: False, fetcher=fetch_detail,
                  sleeper=time.sleep, batch_size=DEFAULT_BATCH_SIZE,
                  cooldown_seconds=DEFAULT_COOLDOWN_SECONDS):
    """Claim and persist at most 40 details; no new database schema required.

    One PostgreSQL connection is used ONLY on the calling thread. Concurrent
    threads do HTTP fetches only. All successful responses are saved with their
    existing lease tokens. The node lock excludes other local Battlelog traffic.
    """
    node_cooldown.STATE.parent.mkdir(parents=True, exist_ok=True)
    if not (1 <= batch_size <= 40 and cooldown_seconds >= 61):
        raise ValueError("invalid detail burst pacing")
    with open(str(node_cooldown.STATE) + '.lock', 'a+') as lock:
        while not stopped():
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                try:
                    state = json.loads(node_cooldown.STATE.read_text())
                except (OSError, ValueError):
                    state = {}
                interval, _ = node_cooldown.policy_values()
                remaining = max(float(state.get('until_epoch', 0)) - time.time(),
                                float(state.get('last_request_epoch', 0)) + interval - time.time())
                if remaining <= 0:
                    break
            finally:
                if remaining > 0:
                    fcntl.flock(lock, fcntl.LOCK_UN)
            sleeper(min(remaining, 1))
        else:
            return 0, False

        # Exclusive node lock stays held until the last in-flight response has
        # been classified. Other local collector processes cannot bypass a 429.
        try:
            claimed = []
            for _ in range(min(batch_size, 40)):
                if stopped():
                    break
                item = claim_player(conn, worker)
                if item is None:
                    break
                claimed.append(item)
            if not claimed:
                return 0, False

            def fetch(item):
                job, _ = item
                return fetcher(*job)

            def handle(item, result):
                job, token = item
                status, payload, error, hint = result
                if status == 429:
                    _publish_429(result)
                if status != 200 or payload is None:
                    delay = retry_delay(status, 1, hint)
                    retry_player(conn, job, token, f'HTTP {status}: {error}',
                                 86400 if delay is None else delay)
                    return
                try:
                    save_player(conn, job, token, payload)
                except ValueError as exc:
                    retry_player(conn, job, token, f'invalid detail: {exc}', 86400)

            # Renew before dispatch; the caller does not sleep with active claims.
            eligible = []
            for job, token in claimed:
                if renew_player(conn, job, token):
                    eligible.append((job, token))
            try:
                count, limited = run_burst(eligible, fetch, handle,
                                           batch_size=batch_size, stopped=stopped)
            finally:
                # Unstarted claims must not sit leased until expiry.
                # This includes jobs held back by a 429 or shutdown.
                # Successful/retried jobs have already cleared their tokens.
                for job, token in claimed:
                    retry_player(conn, job, token, 'burst not dispatched', 0)
            if count:
                now = time.time()
                try:
                    state = json.loads(node_cooldown.STATE.read_text())
                except (OSError, ValueError):
                    state = {}
                state['last_request_epoch'] = now
                tmp = node_cooldown.STATE.with_name(node_cooldown.STATE.name + '.tmp.' + str(os.getpid()))
                tmp.write_text(json.dumps(state))
                os.replace(tmp, node_cooldown.STATE)
            # Reserve a full 61-second rest for this node after the last
            # response. The wait happens OUTSIDE the node lock so graceful
            # shutdown and unrelated processes can inspect state safely.
            if count and not limited:
                state["until_epoch"] = max(float(state.get("until_epoch", 0)),
                                           time.time() + cooldown_seconds)
                state["status"] = "detail_batch_idle"
                tmp = node_cooldown.STATE.with_name(node_cooldown.STATE.name + ".tmp." + str(os.getpid()))
                tmp.write_text(json.dumps(state))
                os.replace(tmp, node_cooldown.STATE)
            return count, limited
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
