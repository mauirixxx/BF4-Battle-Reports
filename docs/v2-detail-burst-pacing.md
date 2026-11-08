# BF4BR v2 player-detail burst pacing — release preparation

**Status: release candidate on feature branch. Not enabled, tagged, or deployed.**

## Intent

Reuse the existing `bf4br.detail_worker`, player-detail job queue, per-player raw persistence, retry/fencing, coordinator, supervisor, and migration 0007/0008. Experiment with **up to 4 concurrent requests**, **40 player requests per batch**, then **61 seconds of rest after the last response completes** before another batch. Keep the existing ten-node coordinator allocation and do not change generic report collection in this feature.

## Current code findings

- `detail_worker.process_one` claims and saves a **single** persona detail at a time, using `detail_queue`'s existing fenced leases and raw JSON archive.
- `node_cooldown.guarded_request` holds an exclusive `flock` **while the HTTP request executes**. Adding threads to the current code would not create concurrent requests. Its shared gate also protects persona and generic report traffic from racing with a 429.
- `detail_queue` already supports individual retries and durable success; the coordinator already seeds, activates, and settles detail reports. No new database table or Alembic migration is proposed for this throughput change.
- The current detail pipeline is **opt-in and not deployed** on the production fleet; do not confuse it with existing generic report workers.

## Implementation constraints before activation

1. Preserve the shared node-wide 429 gate, but replace request-long serialization for detail bursts with an explicit **node-local reservation/active-burst mechanism**. Other Battlelog clients on the same IP must not bypass an active cooldown or race with a 429. No change to the default conservative behavior until feature opt-in.
2. Keep each persona claim's **own lease token**, with a single PostgreSQL connection on the dispatcher thread; never share a psycopg connection concurrently across threads. Reuse `save_player`/`retry_player` rather than creating a second persistence path.
3. Keep no more than 4 in-flight HTTP requests and no more than 40 dispatched requests per burst, even across failures. A 429 stops dispatching new work, records the existing node-wide cooldown, and lets already-running requests finish/checkpoint.
4. Start the 61-second cooldown **after all in-flight requests from the batch finish**. Make waits interruptible for shutdown and preserve lease ownership/renewal. Do not spend an expiring lease sleeping without renewal.
5. Count every Battlelog request made by other worker types on the node against the shared pacing policy. Avoid assuming a dedicated-IP detail worker when the supervisor also runs generic/persona requests.
6. Validate with isolated tests (burst cap, 429 race, concurrent persistence, restart/lease expiry, interrupted cooldown, mixed worker traffic) and the user's ongoing v4 soak results. Do not publish a release until those pass.

## Release candidate

`detail_burst.py` dispatches up to four concurrent HTTP requests, while `detail_burst_worker.py` handles persistence on one PostgreSQL connection, shared node-wide locking, 429 classification and the post-batch 61-second cooldown. Player jobs are claimed incrementally as HTTP slots open, preventing a 40-job backlog of expiring leases. The feature is opt-in with `BF4BR_DETAIL_BURST_ENABLED=1` and requires the existing detail pipeline to be enabled separately. Generic report collection remains unchanged.

Release verification: run the full `unittest` suite with the production Python environment and confirm the supervisor opt-in configuration before tagging.
