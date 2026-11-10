"""Standalone HTTPS client for BF4BR external player-detail enrichment."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import logging
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from bf4br.detail_fetch import fetch_detail

LOG = logging.getLogger("bf4br.external_worker")


class APIError(RuntimeError):
    def __init__(self, status, detail):
        super().__init__(f"API HTTP {status}: {detail}")
        self.status = status


def api_post(base, key, route, payload):
    data = json.dumps(payload, separators=(",", ":")).encode()
    req = Request(base.rstrip("/") + "/api/v1/" + route, data=data,
                  headers={"Authorization": "Bearer " + key,
                           "Content-Type": "application/json",
                           "User-Agent": "bf4br-external-worker/0.1"},
                  method="POST")
    try:
        with urlopen(req, timeout=35) as response:
            return json.load(response)
    except HTTPError as exc:
        raise APIError(exc.code, exc.read(2048).decode(errors="replace")) from exc


def retry_after_seconds(value):
    if not value:
        return 0
    try:
        return max(0, int(float(value)))
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
            return max(0, int((date - datetime.now(timezone.utc)).total_seconds()) + 1)
        except (TypeError, ValueError, OverflowError):
            return 0


def request_detail(platform, persona, item):
    status, payload, error, retry_after = fetch_detail(platform, item["report_id"], persona)
    return item, status, payload, error, retry_after


def run_batch(base, key, *, concurrency=4):
    claim = api_post(base, key, "work/claim", {})
    if not claim.get("batch_id"):
        LOG.info("No eligible work returned")
        return {"claimed": 0, "stored": 0, "failed": 0, "rate_limited": False}
    batch = claim["batch_id"]
    platform, persona = claim["platform"], claim["persona_id"]
    items = claim["reports"]
    LOG.info("Claimed batch %s: platform=%s persona=%s reports=%d",
             batch, platform, persona, len(items))
    stored = failed = 0
    limited = False
    max_retry = 0
    last_battlelog = None
    pending = {}
    iterator = iter(items)

    def action(item):
        return {"batch_id": batch, "platform": platform,
                "persona_id": persona, "report_id": item["report_id"],
                "token": item["token"]}

    def settle(item, status, payload, error, retry_after):
        nonlocal stored, failed, limited, max_retry
        if status == 429:
            limited = True
            max_retry = max(max_retry, retry_after_seconds(retry_after), 180)
        if status == 200 and isinstance(payload, dict):
            try:
                api_post(base, key, "work/renew", action(item))
                api_post(base, key, "enrichment", {**action(item), "payload": payload})
                stored += 1
                return
            except APIError as exc:
                LOG.warning("Upload failed for report %s: %s", item["report_id"], exc)
        reason = f"Battlelog HTTP {status}: {error or 'no valid payload'}"
        if status == 200:
            reason = "Invalid or unaccepted player-detail payload"
        api_post(base, key, "work/fail",
                 {**action(item), "reason": reason[:500],
                  "retry_seconds": max(60, min(86400, max_retry or 1200))})
        failed += 1

    def dispatch(pool):
        nonlocal last_battlelog
        try:
            item = next(iterator)
        except StopIteration:
            return False
        # Renew before dispatch to protect against time spent in this batch.
        api_post(base, key, "work/renew", action(item))
        future = pool.submit(request_detail, platform, persona, item)
        pending[future] = item
        last_battlelog = time.monotonic()
        return True

    try:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            for _ in range(min(concurrency, len(items))):
                dispatch(pool)
            while pending:
                future = next(as_completed(tuple(pending)))
                item = pending.pop(future)
                try:
                    _, status, payload, error, retry_after = future.result()
                except Exception as exc:
                    status, payload, error, retry_after = 0, None, str(exc), None
                last_battlelog = time.monotonic()
                settle(item, status, payload, error, retry_after)
                LOG.info("Report %s: HTTP %s; stored=%s failed=%s",
                         item["report_id"], status, stored, failed)
                if not limited:
                    dispatch(pool)
        # Explicitly release all never-dispatched reservations.
        for item in iterator:
            api_post(base, key, "work/fail",
                     {**action(item), "reason": "Not dispatched; batch interrupted by HTTP 429",
                      "retry_seconds": max(60, max_retry or 1200)})
            failed += 1
        if limited:
            api_post(base, key, "work/rate-limited",
                     {"batch_id": batch, "retry_after_seconds": max_retry})
        api_post(base, key, "work/complete", {"batch_id": batch})
        LOG.info("Batch complete: stored=%d failed=%d rate_limited=%s",
                 stored, failed, limited)
    except Exception:
        LOG.exception("Batch interrupted; remaining leases will expire if not settled")
        raise
    return {"claimed": len(items), "stored": stored, "failed": failed,
            "rate_limited": limited, "last_request": last_battlelog}


def main(argv=None):
    parser = argparse.ArgumentParser(description="BF4BR external player enrichment")
    parser.add_argument("--api-url", default="https://reports.bf4playerstats.com")
    parser.add_argument("--key-file", default="/root/bf4br-external-worker.key")
    parser.add_argument("--concurrency", type=int, default=4, choices=range(1, 5))
    parser.add_argument("--once", action="store_true", help="Run exactly one batch and exit")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    key = Path(args.key_file).read_text().strip()
    if not key:
        parser.error("API key file is empty")
    while True:
        started = time.monotonic()
        try:
            result = run_batch(args.api_url, key, concurrency=args.concurrency)
        except APIError as exc:
            if exc.status in (409, 429):
                LOG.warning("Server cooldown/busy: %s", exc)
                if args.once:
                    return 2
                time.sleep(61)
                continue
            raise
        if args.once:
            return 0
        # Server cooldown begins on completion, so never claim earlier than that.
        time.sleep(max(61, 61 - (time.monotonic() - started)))


if __name__ == "__main__":
    raise SystemExit(main())
