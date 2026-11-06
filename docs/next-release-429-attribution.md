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

## Pre-release verification update (2026-11-05)

- Live BF4BR operational schema captured read-only in `docs/database-schema-reference.md`; `DEPLOYMENT.md` distinguishes the initial migration from the current state.
- Public live-monitor fetch errors now correlate with a *single unambiguous* persistent `report` history node within ±30 seconds, suppressing corresponding duplicate rows. Older unmatched fetch records remain `Unknown`.
- `bf4br/fleet_upgrade.py` now refuses to switch a node until **all four** historical/daily persona/report lease queues have drained; new `tests/test_fleet_drain.py` covers both success and failure.
- Existing supervisor reconnect fault injection updated to reflect DB-controlled request interval and cooldown columns.
- For isolated integration tests on `reports`, run as PostgreSQL peer-authenticated user with **separate writable request policy and cooldown files**. The root-owned `/tmp/bf4br-request-policy.json` and `/tmp/bf4br-battlelog-cooldown.json.lock` must not be shared by postgres-run tests. Example: `runuser -u postgres -- env BF4BR_REQUEST_POLICY_FILE=/tmp/bf4br-integration-policy-postgres.json BF4BR_COOLDOWN_FILE=/tmp/bf4br-integration-cooldown-postgres.json BF4BR_TEST_DSN='dbname=bf4br_integration user=postgres' PYTHONPATH=/opt/bf4br-main-synced /opt/bf4br/.venv/bin/python -m unittest discover -s tests -q`.
- The production coordinator's `/opt/bf4br/bf4br/fleet_upgrade.py` was backed up and updated to match GitHub main. `--check` confirmed v1.0.10 remains the latest published release and listed ten eligible nodes; **no deployment was initiated**.
- The original `/opt/bf4br` checkout still contains old history and uncommitted modifications. It is deliberately preserved; `/opt/bf4br-main-synced` is the clean verified main worktree.

**Verification result:** Complete isolated PostgreSQL suite passed **90/90** on 2026-11-05 after using separate writable policy and cooldown files; the prior five failures were test-environment permission conflicts with root-owned shared `/tmp` files. No collector code change was required for those failures. The rolling upgrade has not started. Before tagging v1.0.11, verify the staged upgrade/rollback plan and fleet service health.

## Live rollout incident / follow-up (2026-11-06 UTC)

- v1.0.11 published at immutable commit `19f7d859e79bc5d901ab6d0b892f1ddc4ae14369`; `hnl-01` and `hnl-02` upgraded first.
- `hnl-03` repeatedly failed the original 100-second drain because rows retain `state='leased'` after the owning worker exits; no worker reclaims them while node is paused. Corrected coordinator-side drain to count only unexpired leases (`lease_until>now()`) in all four queues and allow 240 seconds. Changes are in main (after the v1.0.11 tag) and applied to the `reports` deployer, **not** to the immutable v1.0.11 worker artifact.
- A long-running `daily_persona_worker` historical fallback continued processing after SIGTERM; its daily worker STOP flag does not necessarily stop `persona_worker.process_one` immediately. After confirming the worker was still saving pages and had not stopped, the specific worker was terminated; committed pages persisted, its fenced lease was allowed to expire naturally, and `hnl-03` switched to v1.0.11 with healthy supervisor. **Follow-up needed:** make historical fallback observe daily-worker shutdown without forced termination, with a regression test; release in a future worker version rather than mutating v1.0.11.
- Automatic timer was stopped during repair, then restarted; sequential upgrade resumed. Confirm all ten nodes and pause states after completion.
