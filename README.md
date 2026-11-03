# BF4 Battle Reports (BF4BR)

Battlefield 4 battle-report discovery, archival and player-history project.

## Current state

The initial commit captures the existing, standalone Python collectors from the `reports` host. Their PostgreSQL database (`bf4_battle_reports`) and data are **not** bundled in this repository. The current scripts are manual/continuous collectors; distributed Docker workers and live queue controls are planned, not yet deployed.

See `README-operations.md` for the original operational commands.

## Planned architecture

- Self-feeding persona discovery with resumable page cursors and 429/503 retry handling.
- Database-coordinated, leased battle-report download queue for ten nodes.
- Docker-based workers, configurable discovery concurrency (three per node initially), and graceful/forced drain controls.
- Reuse the existing PostgreSQL database; no production schema or service changes until migrations and tests are verified.

Never commit credentials, database dumps, or raw player-report data to this repository.

## v1.0.3 platform fairness

See [docs/v1.0.3-fairness.md](docs/v1.0.3-fairness.md) for per-platform feeder targets, worker assignment, and fresh-first report ordering.
