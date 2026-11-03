"""Battlelog transient-error classification and bounded retry scheduling."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import random

TRANSIENT_HTTP = {408, 425, 429, 500, 502, 503, 504}

def retry_after_seconds(header, now=None, cap=3600):
    if not header:
        return None
    header = header.strip()
    try:
        seconds = float(header)
    except ValueError:
        try:
            moment = parsedate_to_datetime(header)
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=timezone.utc)
            now = now or datetime.now(timezone.utc)
            seconds = (moment - now).total_seconds()
        except (ValueError, TypeError, OverflowError):
            return None
    return min(cap, max(0.0, seconds))

def retry_delay(status, attempt, retry_after=None, rng=None, cap=3600):
    """Return retry delay, or None for a nontransient response.

    Uses exponential backoff with full jitter; Retry-After is a lower bound
    for 429/503, within the configured cap.
    """
    if status not in TRANSIENT_HTTP:
        return None
    rng = rng or random
    base = min(cap, 2 ** min(max(0, attempt), 12))
    delay = rng.uniform(base * 0.5, base)
    hint = retry_after_seconds(retry_after, cap=cap) if status in (429, 503) else None
    return min(cap, max(delay, hint or 0.0))
