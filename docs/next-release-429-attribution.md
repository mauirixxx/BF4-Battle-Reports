# BF4BR next release: reliable 429 node attribution (preparation)

Status: **investigation / not released**. Current deployed fleet observed at v1.0.10; proposed next version requires confirmation of release/tag state before numbering.

## Verified implementation facts (2026-11-05)

- Both deployed `bf4br/queue.py` and `bf4br/daily_queue.py` already insert `bf4br_collector_error_history` rows **in the same transaction** as a successful error release, reading `lease_owner` under a row lock before clearing it.
- Historical persona errors use `job_kind=historical_persona`; daily persona uses `daily_persona`; report uses `report`. The historical and report queue share the same release function.
- The public monitor's `battle_report_fetch_log` error query explicitly selects `NULL::text AS node_name`, explaining why those rows show Unknown regardless of worker release logging. The monitor also includes a legacy fallback query that reconstructs names from `lease_owner` after release, which may be NULL.
- The live monitor now includes a ten-minute 429 breakdown from persistent history and a union of attributed history, mutable job errors, and active node cooldowns for 429 Hell.
- Current queue code does **not** log errors when lease release fails fencing; do not falsely attribute these as successful releases.

## Release gates

1. Reconcile repository documentation and migrations with the live database: `DEPLOYMENT.md` and `migrations/0001_worker_queues.sql` predate `bf4br_collector_error_history` and other live additions. Inspect authoritative DDL and bring version-controlled schema docs/migrations into alignment **before any schema-dependent changes**.
2. Verify current GitHub release/tag and deployed worker source hashes. The `reports` host checkout has uncommitted modifications and an old commit; do not package it blindly or overwrite production.
3. Reproduce a 429 via an isolated test double (no real Battlelog requests). Assert history persists node, worker, platform, item ID, job kind, and error after a successful fenced release; test historical, daily and report paths; assert no false event on stale-token release.
4. Make the web monitor prefer matching attributed history for report fetch errors, rather than displaying a duplicate Unknown row. Document unavoidable unattributed legacy fetch records.
5. If tests expose a missing worker-side attribution path, implement the smallest change, run unit and disposable PostgreSQL integration tests, and confirm no change to request pacing, retry delay, coordinator assignments, or lease fencing.
6. Tag a version only after the above pass. Use the documented fleet auto-upgrader with staged verification, node/version visibility, health checks, and rollback. Never restart all ten nodes at once.

## Scope

Goal: accurate **current** 429 node and request-type reporting, with persistent events for historical trends. No historical backfill of unrecorded node identities. No change to collection throughput or Battlelog request frequency.
