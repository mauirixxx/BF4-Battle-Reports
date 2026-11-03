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
7. Roll out remaining nodes incrementally; keep `reports` collector-free except for explicitly bounded test runs.

**Before rollout:** confirm importer equivalence for player-name history and timestamp behavior on more representative real reports, review production DB role grants and credentials, and check current worker shutdown behavior. A successful single-report canary is not blanket authorization for ten nodes.

## 2026-11-03 cross-site production canary (bounded)

- `reports`: PostgreSQL 18.6 at `192.168.200.49`; `hnl-01`: Honolulu worker at `192.168.5.70`.
- Created dedicated `bf4br_collector` PostgreSQL login, scoped table grants, and SCRAM `pg_hba.conf` entry for `192.168.5.70/32`. Verified authenticated Python psycopg connection using a protected passfile.
- Registered node controls: `hnl-01` one persona/one report worker, **paused**; `reports` zero persona/one report worker, **paused**. The canary deliberately bypassed supervisor controls with explicitly bounded one-shot workers, **two report jobs per site**, to test concurrency. No persistent service or persona worker was started.
- Four platform-1 reports were seeded, both sites concurrently claimed distinct jobs using token-fenced leases.
- `reports` imported IDs `2115119935475624320` (100 players) and `2115151036395608320` (62 players).
- `hnl-01` imported `2115149075541076352` (94 players).
- `hnl-01` deferred `2115624300955880000` because the HTTP 200 payload was **incomplete**; job is `ready` with one failure and retry delay, no normalized import.
- Post-run database verification: 3 jobs `done`, 1 `ready`, **0 leased**; 256 report-player associations across successful reports. Both bounded processes exited with code 0.
- The one-shot canary scripts were removed from both machines. The node controls remain paused. `reports` was used only as an explicitly requested temporary canary worker, not converted to a production collector.
- Before enabling ongoing collection, examine incomplete-report handling and verify supervisor pause/resume and graceful shutdown on the remote node. Multi-site concurrency was verified for report workers, not yet persona workers or a persistent multi-node supervisor.

## 2026-11-03 supervisor deployment on hnl-01

- `/opt/bf4br/.venv` has Python and psycopg 3.3.7; `/root/.pgpass` mode 0600 holds the dedicated database credential. Never commit this file.
- Installed `/etc/systemd/system/bf4br-supervisor.service`, configured `BF4BR_NODE=hnl-01`, `BF4BR_DSN` with direct IP `192.168.200.49`, username `bf4br_collector`, and passfile. **Quote the entire systemd Environment assignment when its value contains spaces**; otherwise libpq falls back to root/root. Startup restart fixed this.
- Enabled systemd startup. Supervisor runs on `hnl-01` only. The `reports` node control stays paused and is not running a production supervisor.
- Validated pause -> resume -> pause/drain -> resume. Paused supervisor had no worker children; resumed spawned one persona and one report child; pause terminated both gracefully.
- First live persona attempt found a missing `INSERT,UPDATE` grant on `history_discoveries`; added this grant to `bf4br_collector`. Retry succeeded and logged `page saved ... reports=10`.
- Verified live history pages accumulating and new report jobs being enqueued automatically. Last observation: `hnl-01` unpaused with one persona and one report worker; `reports` paused. This is an ongoing first-node canary, **not yet sustained multi-collector-node production**.
- Operational control: `systemctl status bf4br-supervisor.service`, `journalctl -u bf4br-supervisor.service -f`; pause with `python -m bf4br.control --node hnl-01 pause` using an authenticated `BF4BR_DSN`, resume similarly. Check job states and lease owners before expanding concurrency.

## Fleet controller on reports (phase 1: observe-only)

- Installed `bf4br-deployer.service` on `reports`, running as local `postgres` with PostgreSQL peer authentication, no embedded passwords. The unit source is `deploy/systemd/bf4br-deployer.service`.
- `bf4br/deployer.py` polls GitHub `origin/main` every 300 seconds and reads registered node controls. Logs current checkout SHA, remote main SHA, whether an update exists, and configured worker counts/paused state.
- **This is an observation-only foundation, not yet an automatic updater.** It never executes SSH, changes worker controls, installs releases, or restarts services.
- Remote `root@192.168.5.70` SSH from `reports` was tested with `BatchMode=yes` and **failed public-key authentication**. Do not enable unattended deployment until a dedicated, restricted deployment identity, pinned host keys, remote command authorization, and least-privilege credentials are established.
- Next deployment phase: approved immutable release/tag manifest; remote host inventory; exclusive rollout lock; preflight checks; one-node-at-a-time drain and bounded lease wait; atomic versioned releases and isolated virtualenvs; restart and HTTP/database health validation; automatic rollback and halt on failure; explicit database migration compatibility gate.
- Operator checks: `systemctl status bf4br-deployer.service`; `journalctl -u bf4br-deployer.service -n 30 --no-pager`. A one-time audit can be run with `runuser -u postgres -- /opt/bf4br/.venv/bin/python -m bf4br.deployer --once` from `/opt/bf4br`.
