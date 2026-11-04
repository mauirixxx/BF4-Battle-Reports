# BF4 Battle Reports (BF4BR)

Battlefield 4 battle-report discovery, archival, and player-history collection.

## Current release

**v1.0.5** was published on 2026-11-04 from commit `df24fee`. Publication does not itself confirm that every collector has upgraded or that daily collection is activated.

The production architecture includes a PostgreSQL-backed queue feeder, leased persona/report workers, per-node supervisors, a fleet release updater, and an observation-only deployment monitor. Historical backfill remains operational independently of daily catch-up.

## v1.0.5: daily UTC catch-up

This release adds a separate daily persona queue, a UTC day importer, a daily persona worker, midnight-overlap handling, and prioritization of reports discovered through the daily lane. The intended configuration reallocates three of the ten existing persona workers (one each for PC, PlayStation, and Xbox) to daily work while seven continue historical backfill. It does not increase the total persona worker count or per-worker pacing.

Daily activation requires the relevant migration, importer scheduling, and designated node configuration. **Do not infer activation from the published GitHub release alone.**

See [v1.0.5 daily catch-up](docs/v1.0.5-daily-catchup.md), [deployment operations](DEPLOYMENT.md), and [v1.0.3 platform fairness](docs/v1.0.3-fairness.md).

## Release and operations

Official stable GitHub Releases are the update trigger; pushes to `main` are not. The release updater and the observation-only deployer are separate services. Verify the latest published release, each node's installed version, and active worker allocation after publication.

The original standalone collectors and their operational notes are retained in [README-operations.md](README-operations.md). The PostgreSQL database and credentials are not part of the repository.

Never commit credentials, database dumps, or raw player-report data.
