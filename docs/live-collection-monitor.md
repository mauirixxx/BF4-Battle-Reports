# Live collection monitor

The deployed website on `rnt-reports` includes `/battle-reports-live.php`, linked from the Battle Reports archive navigation. The source for the page and current archive entry point is retained in `website/`. Deploy by copying the PHP files to the web document root after reviewing local configuration. The monitor uses the local PostgreSQL `bf4_battle_reports` database and the `www-data` database role.

## Display

The monitor polls a read-only JSON endpoint every five seconds and displays active, unexpired persona leases (with the current locally recorded player name), active report leases, and the 60 most recently imported reports. It also shows import counts for the last ten minutes. The pause button stops polling. Leases indicate claimed work, not necessarily active HTTP requests.

The report feed displays two distinct UTC timestamps using ISO-style `YYYY-MM-DD HH:MM:SS UTC` formatting: **Imported (UTC)** is `battle_report_raw.imported_at`; **Match played (UTC)** is `history_discoveries.report_timestamp`. The latter is the recorded Battlelog discovery timestamp; it may be absent, in which case the UI shows a dash. This prevents confusing a freshly imported old match with a match played today.

## Security and database access

The page is restricted to loopback and the explicitly allowed private subnets in the PHP access check. Do not expose it to the public internet without a separate authentication/access-control review. The endpoint uses `pg_connect('dbname=bf4_battle_reports user=www-data')` and requires SELECT on `bf4br_persona_jobs` and `bf4br_report_jobs`, in addition to the existing read access to `players`, `battle_report_raw`, and `history_discoveries`. A 3-second SQL statement timeout bounds each polling request. No database writes or schema changes are required.

## Backlog policy

The production-safe report queue currently orders eligible claims by `next_attempt_at`, platform, and report ID. It does **not** guarantee newest match first. Changing priority requires performance validation on the large live queue; do not switch to an unindexed per-row discovery timestamp lookup without a bounded query plan and fleet test. Historical report backfill continues independently of the monitor.
