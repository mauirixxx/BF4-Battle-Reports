"""Bounded concurrent detail dispatch, based on the standalone v4 probe.

The caller owns job claims, PostgreSQL persistence, node-wide request gating,
and the 61-second inter-batch cooldown. This module does not touch the DB.
"""
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

from bf4br.detail_batch import validate_burst_policy


def run_burst(jobs, fetch, handle, *, concurrency=4, batch_size=40,
              stopped=lambda: False):
    """Run at most batch_size jobs, with at most concurrency active requests.

    fetch(job) returns a result whose HTTP status is result[0]. handle(job,result)
    persists/classifies the result. On 429, stop dispatching new work and drain
    in-flight work. Return (dispatched, stopped_on_429). Jobs not dispatched are
    left to the caller's existing retry/claim machinery.
    """
    validate_burst_policy(batch_size, concurrency, 61)
    jobs = iter(jobs)
    pending = {}
    dispatched = 0
    rate_limited = False

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        def submit():
            nonlocal dispatched
            if dispatched >= batch_size or stopped():
                return False
            try:
                job = next(jobs)
            except StopIteration:
                return False
            pending[pool.submit(fetch, job)] = job
            dispatched += 1
            return True

        for _ in range(concurrency):
            if not submit():
                break
        while pending:
            done, _ = wait(tuple(pending), return_when=FIRST_COMPLETED)
            completed = []
            for future in done:
                job = pending.pop(future)
                result = future.result()
                completed.append((job, result))
                if result[0] == 429:
                    rate_limited = True
            for job, result in completed:
                handle(job, result)
            if not rate_limited and not stopped():
                for _ in completed:
                    submit()
    return dispatched, rate_limited
