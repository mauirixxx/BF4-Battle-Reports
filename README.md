# BF4 Battle Reports (BF4BR)

Battlefield 4 battle-report discovery, archival, and player-history collection.

## Current published release

**v2.0.1** was published on **2026-11-07** (commit `e29b25426ab4155cd708976351853d9f30a747b5`). See the [official v2.0.1 release notes](https://github.com/mauirixxx/BF4-Battle-Reports/releases/tag/v2.0.1).

v2.0.1 is a **worker-shutdown and fleet-upgrade reliability maintenance release** following v2.0.0. It makes HTTP 429 cooldown waits interruptible during graceful drain, preserves existing PostgreSQL lease fencing/recovery, and does not require new database migrations or configuration changes. The published release reports **105 passing regression tests**.

**Published version is not a live fleet-version check.** Verify individual node versions and active assignments in the deployment monitor; older version references in historical rollout notes are dated snapshots, not current status.

## Distributed collection and player-detail enrichment

The production architecture includes a PostgreSQL-backed queue feeder, leased historical/daily persona and report workers, a central coordinator, per-node supervisors, a fleet release updater, and monitoring. Three daily nodes are intended to cover PC, PlayStation, and Xbox, with seven nodes available for historical or enrichment roles as coordinated.

v2.0.0 introduced the **opt-in player-detail enrichment pipeline**: separate persona-specific Battlelog requests, fenced per-player claims, durable raw JSON persistence, retry/recovery, and coordinator-managed report activation/completion. **The v2.0.1 release notes explicitly state that player-detail enrichment remains disabled until activated.** Do not infer deployment or activation from source code, migrations, or a published release.

The next experimental enhancement is **four concurrent player-detail requests, batches of 40, and a 61-second cooldown after the final response completes**. This work is on the [feature/v2-detail-burst-pacing branch](https://github.com/mauirixxx/BF4-Battle-Reports/tree/feature/v2-detail-burst-pacing); it is **not part of v2.0.1**, and has not been enabled in production.

## Historical release documentation

- [v2.0.0 rollout and verification history](docs/v2.0.0-rollout.md) — development log and dated pre-release observations.
- [Player-detail enrichment design](docs/player-detail-enrichment-plan.md) — historical design, with later rolling-pipeline changes described in the rollout notes.
- [v1.0.5 daily UTC catch-up](docs/v1.0.5-daily-catchup.md).
- [Deployment operations](DEPLOYMENT.md) and [current schema reference](docs/database-schema-reference.md).
- [v1.0.3 platform fairness](docs/v1.0.3-fairness.md).

## Release and operations

Official stable GitHub Releases are the update trigger; pushes to `main` are not. The release updater and observation-only deployer are separate services. Verify the published release, each node's installed version, and active worker allocation after publication.

The original standalone collectors and their operational notes are retained in [README-operations.md](README-operations.md). The PostgreSQL database and credentials are not part of the repository.

Never commit credentials, database dumps, or raw player-report data.
