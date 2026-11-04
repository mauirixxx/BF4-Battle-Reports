"""Node-local Battlelog request gate shared across persona/report processes.

An exclusive flock covers the request and response classification, preventing
another process from issuing a request between a 429 and cooldown publication.
"""
import fcntl
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

LOG = logging.getLogger(__name__)
STATE = Path(os.environ.get('BF4BR_COOLDOWN_FILE', '/tmp/bf4br-battlelog-cooldown.json'))
DEFAULT_SECONDS = 120


def guarded_request(fn, status_of, retry_after_of=lambda result: None, sleeper=time.sleep):
    """Serialize Battlelog requests on one node; apply shared 429 cooldown."""
    STATE.parent.mkdir(parents=True, exist_ok=True)
    with open(str(STATE) + '.lock', 'a+') as lock:
        while True:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                try:
                    state = json.loads(STATE.read_text())
                except (FileNotFoundError, ValueError, OSError):
                    state = {}
                remaining = float(state.get('until_epoch', 0)) - time.time()
                if remaining <= 0:
                    result = fn()
                    status = status_of(result)
                    if status == 429:
                        header = retry_after_of(result)
                        from bf4br.retry import retry_after_seconds
                        hinted = retry_after_seconds(header, cap=86400)
                        seconds = max(DEFAULT_SECONDS, hinted or 0)
                        until = time.time() + seconds
                        tmp = STATE.with_name(STATE.name + '.tmp.' + str(os.getpid()))
                        tmp.write_text(json.dumps({'until_epoch': until, 'status': 429,
                            'retry_after': header, 'cooldown_seconds': seconds,
                            'updated_at': datetime.now(timezone.utc).isoformat()}))
                        os.replace(tmp, STATE)
                        LOG.warning('Battlelog node cooldown HTTP 429 retry_after=%r cooldown_seconds=%.1f until=%s',
                                    header, seconds, datetime.fromtimestamp(until, timezone.utc).isoformat())
                    return result
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
            sleeper(min(remaining, 5))