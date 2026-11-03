"""Pure UTC day-window and BF4SW session normalization for v1.0.5.

No database writes and no changes to historical persona cursors.
"""
from datetime import date, datetime, time, timedelta, timezone

PLATFORM_CODES = {"pc": 1, "ps4/5": 32, "ps4": 32, "ps5": 32,
                  "playstation": 32, "xbox": 64, "xboxone": 64,
                  "xbox one": 64}


def previous_utc_day(now: datetime) -> tuple[datetime, datetime]:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    end = datetime.combine(now.astimezone(timezone.utc).date(), time.min,
                           tzinfo=timezone.utc)
    return end - timedelta(days=1), end


def session_overlaps(time_joined: datetime, last_seen: datetime,
                     time_left: datetime | None, start: datetime,
                     end: datetime) -> bool:
    for value in (time_joined, last_seen, start, end):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("session timestamps must be timezone-aware")
    observed_end = time_left if time_left is not None else last_seen
    if observed_end.tzinfo is None or observed_end.utcoffset() is None:
        raise ValueError("time_left must be timezone-aware")
    return time_joined < end and observed_end >= start


def platform_code(label: str) -> int | None:
    return PLATFORM_CODES.get(str(label).strip().lower())
