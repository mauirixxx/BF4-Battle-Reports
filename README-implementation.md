# BF4BR distributed worker implementation status

## Verified foundation

The baseline BF4Reports Python collectors were copied from the live `reports` host into `main`. The PostgreSQL 18 schema of the standalone `bf4_battle_reports` database was inspected before designing the additive queue migration.

`migrations/0001_worker_queues.sql` creates two leased queues and a node-control table. It was **tested successfully** on a temporary database containing a schema-only copy of the existing database (three tables and four indexes created). **The migration has not been applied to production.**

`bf4br/queue.py` contains atomic `FOR UPDATE SKIP LOCKED` claims, lease renewal, token-fenced release and incremental queue seeding. The Python module has not yet undergone integration or concurrency tests.

## Still required before deployment

1. Run concurrency, lease expiry, fencing and crash-recovery tests against a disposable PostgreSQL database.
2. Implement persona workers that persist every page cursor, distinguish initial full-history scans from incremental refreshes, retry HTTP 429/503 with Retry-After/backoff, and never advance a completion boundary on failure.
3. Implement report workers that fetch, archive raw JSON, import parsed report/player data and safely recover from interrupted imports.
4. Add per-egress pacing, circuit breakers, supervisor, heartbeat and dynamic node controls (default three persona workers, configurable graceful drain/force stop).
5. Build and test Docker images/Compose with restricted PostgreSQL credentials and VPN connectivity; stage one canary before the ten-node rollout.
6. Document actual schema changes and rollback, and preserve the existing scripts as a fallback.

Do not enable multiple legacy downloaders by removing the single-process lock. No production database or service changes were made by this foundation commit.
