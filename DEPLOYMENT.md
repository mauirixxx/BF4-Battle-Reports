# BF4BR database schema and distributed rollout

Verified 2026-11-02 against PostgreSQL 18.6 on `reports`, database `bf4_battle_reports`.

## Existing data stays in place

The distributed BF4BR workers continue to write to the original database. Existing tables include `battle_report_raw`, `battle_report_details`, `battle_reports`, `report_players`, `players`, `player_name_history`, `servers`, `history_pages`, and `history_discoveries`. No data transfer or rewrite was performed.

The legacy report tables retain their original column names. Important keys:
- `battle_report_raw(platform, battlelog_report_id)`: `raw_response` JSONB, `fetched_at`, `imported_at`.
- `battle_report_details(platform, battlelog_report_id)`: `report_json` JSONB, `extracted_at`.
- `battle_reports`: internal `id`, platform, Battlelog ID, server ID, report timestamp and collected timestamp.
- `players`: internal ID, platform/persona ID, current name and observation timestamp, earliest/latest report timestamps.
- `servers`: internal ID, GUID and current name.
- `report_players`: report ID, player ID and observed player name.
- `player_name_history`: player ID, name, observed timestamp and source report ID.

## Additive production migration 0001

`migrations/0001_worker_queues.sql` was applied successfully on 2026-11-02 using a single transaction. It created:

- `bf4br_persona_jobs`: primary key `(platform, persona_id)`; state `ready|leased|done`; cursor/newest/boundary epochs; completion and next-attempt timestamps; owner, UUID lease token, lease expiry, failures and error. Partial ready/lease indexes.
- `bf4br_report_jobs`: primary key `(platform, battlelog_report_id)`; same state, retry and lease fencing fields, partial ready/lease indexes.
- `bf4br_node_controls`: primary key `node_name`; `persona_workers` default 3; `report_workers` default 1; `paused` default false; updated timestamp. Worker counts constrained 0..64.

All three tables were independently verified in `information_schema.columns` after migration. Counts immediately after migration: **0 persona jobs, 0 report jobs, 0 node controls**. No workers were started, and no job queue was seeded as part of migration.

## Operational architecture

- `reports` remains PostgreSQL and isolated Docker integration/canary test host, **not a production collector**.
- Ten intended dedicated collection nodes each have their own outbound public IP.
- Each worker independently uses the proven legacy request pacing. **No fleet-wide or per-host request rate coordination** is required.
- PostgreSQL leases and fencing coordinate **ownership of work**, not HTTP request timing.
- Persona worker default: three per node; report worker default: one per node. Change counts via node controls; pause/drain for safe maintenance.
- Report downloader: 5-second connect timeout, 20-second total timeout, three attempts, 10-second delay between report jobs; 20-minute deferred retry on failure.
- Raw report archived before normalized import. An import retry reuses the archive without another HTTP request.
- A stale lease token cannot archive or import a report; expired jobs can be reclaimed.

## Tests and canary evidence

- 16/16 Docker PostgreSQL integration/regression tests passed, including lease fencing, 503/timeout retry, import recovery, and worker crash/reclaim.
- Bounded live Battlelog read from `reports`: platform 64, report 2108797019914111296, HTTP 200, 94,433 bytes, 3.53 seconds.
- Legacy parser and new parser matched 78 player identities on the real report.
- Full Docker worker live canary archived and imported the same report into **disposable** PostgreSQL; `imported_at` populated and 78 report-player rows verified.
- Production database was not used for the canary.

## First production-node rollout checklist

1. Verify the target node's outbound public IP is unique and its PostgreSQL connectivity and privileges are appropriate.
2. Install the GitHub main checkout and runtime dependencies; configure `BF4BR_DSN`, `BF4BR_NODE`, and node identity securely, without committing credentials.
3. Register a node control row **paused initially**, with bounded persona/report worker counts. Confirm the node name is unique.
4. Seed a small, explicitly approved set of persona/report jobs; do not unleash the entire backlog.
5. Start supervisor, observe claims, lease renewals, retry logs, raw archives, imported report counts and any HTTP 403/429/503.
6. Verify pause/drain, restart recovery and no duplicate reports. Only then authorize a second node and verify cross-node unique claims.
7. Roll out remaining nodes incrementally; keep `reports` collector-free.

**Before rollout:** confirm importer equivalence for player-name history and timestamp behavior on more representative real reports, review production DB role grants and credentials, and check current worker shutdown behavior. A successful single-report canary is not blanket authorization for ten nodes.
