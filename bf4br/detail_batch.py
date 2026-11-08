"""Pure scheduling primitives for opt-in v4-style detail bursts.

No database access, worker activation, or Battlelog requests occur here.
"""
from collections.abc import Iterable, Iterator
from itertools import islice

DEFAULT_BATCH_SIZE = 40
DEFAULT_CONCURRENCY = 4
DEFAULT_COOLDOWN_SECONDS = 61


def batches(items: Iterable, size: int = DEFAULT_BATCH_SIZE) -> Iterator[tuple]:
    """Yield bounded groups without pre-consuming the entire job stream."""
    if not isinstance(size, int) or isinstance(size, bool) or size < 1:
        raise ValueError('batch size must be a positive integer')
    iterator = iter(items)
    while group := tuple(islice(iterator, size)):
        yield group


def validate_burst_policy(batch_size=DEFAULT_BATCH_SIZE,
                          concurrency=DEFAULT_CONCURRENCY,
                          cooldown_seconds=DEFAULT_COOLDOWN_SECONDS):
    """Validate experimental burst parameters before any worker uses them."""
    if any(type(v) is not int for v in (batch_size, concurrency, cooldown_seconds)):
        raise ValueError('burst policy requires integer values')
    if not (1 <= concurrency <= batch_size <= 40):
        raise ValueError('burst policy requires 1 <= concurrency <= batch_size <= 40')
    if cooldown_seconds < 61:
        raise ValueError('cooldown must be at least 61 seconds')
    return batch_size, concurrency, cooldown_seconds
