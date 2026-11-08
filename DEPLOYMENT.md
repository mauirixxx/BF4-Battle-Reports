# BF4BR database schema and distributed rollout

**Release context:** Latest published stable release is **v2.0.1 (2026-11-07)**. This document contains dated v1.x deployment history and initial-schema descriptions; it is **not a current fleet-version inventory**. v2.0.1 is a graceful-shutdown/upgrade reliability release, with no new migration or configuration requirement; player-detail enrichment remains opt-in and disabled per the published release notes. See [v2.0.1](https://github.com/mauirixxx/BF4-Battle-Reports/releases/tag/v2.0.1), [v2.0.0 rollout history](docs/v2.0.0-rollout.md), and [current schema reference](docs/database-schema-reference.md).

Verified 2026-11-02 against PostgreSQL 18.6 on `reports`, database `bf4_battle_reports`.

> **Current operational schema (verified 2026-11-05):** See [`docs/database-schema-reference.md`](docs/database-schema-reference.md) for the read-only production DDL snapshot of BF4BR queue, coordinator, pacing, heartbeat, assignment, fetch-log and collector-error-history objects. The `0001` migration and the initial rollout values below describe the **2026-11-02 baseline**, not the complete v1.0.10 schema. Do not treat the snapshot as an executable migration or infer that later additions are represented by `0001`.

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

## Fleet SSH bootstrap from reports (2026-11-03)

- Generated a **dedicated Ed25519 SSH key** on `reports`: private key `/root/.ssh/bf4br_fleet_ed25519` (mode 0600); public key `/root/.ssh/bf4br_fleet_ed25519.pub`. Never commit, copy, or display the private key. Public fingerprint: `SHA256:dbqjG1lCVoTgEDukkAdzXypb+OpySjSluZ4lZV4ylIY`.
- Authorized this key in `/root/.ssh/authorized_keys` on **all 17 other currently connected machines**, with `from="192.168.200.49"` source restriction. This is **root SSH access** and should be treated as highly privileged; source restrictions are not a substitute for a dedicated least-privilege deploy account. The private key is currently unencrypted for unattended use, increasing the importance of protecting `reports`.
- Independently read each target's `/etc/ssh/ssh_host_ed25519_key.pub` over the authorized remote management channel. Pinned those public host keys to `/root/.ssh/bf4br_known_hosts` on `reports`, with `StrictHostKeyChecking yes`.
- Created `/root/.ssh/config` aliases for the 17 targets, mapping each hostname to its private IP and the dedicated key/known-hosts file. Operators on `reports` can use `ssh hnl-01`, `ssh mak-db-02`, `ssh tcou`, etc.
- **Verified 17/17** passwordless SSH connections from `reports` using pinned host keys, each returning the expected hostname. All tests were read-only `hostname` commands.
- Access is currently one-way: `reports` to the other machines, not an all-to-all SSH mesh. Do not distribute the private key to targets.
- The `bf4br-deployer.service` still runs as `postgres` in **observation-only mode**. Its service account does **not** have this root SSH private key. Automatic deployments remain disabled pending a scoped deployment identity, restricted sudo/remote commands, and tested rollback.
- To revoke access, remove the `bf4br-reports-deployment` authorized key entry from each target and retire the corresponding private key on `reports`.

### DNS host expansion (2026-11-03)

Added four verified DNS nodes: `mak-dns-01` (`192.168.10.87`), `mak-dns-02` (`192.168.10.88`), `hnl-dns-01` (`192.168.5.87`), and `kah-dns-01` (`192.168.21.87`). Installed the same source-restricted public key in root authorized_keys; pinned their directly obtained Ed25519 host keys in `/root/.ssh/bf4br_known_hosts`; added SSH aliases to `/root/.ssh/config`; verified passwordless `ssh <hostname> hostname` for all four. Fleet access now covers **21 remote targets plus reports**. `rnt-dns-01` was not in the connected device inventory and has not been enrolled. This change does not enable automated deployment or change DNS services.

## Release-only updater implementation (2026-11-03)

- GitHub `v1.0.0` is published and independently resolved to commit `4db6a41b916ec5e7a3daeefddd991f32ffb190e4`. The `v1.0.1` fix is committed to main but **not released**.
- `bf4br/release_coordinator.py` checks only published stable GitHub Releases, rejects drafts/prereleases, validates semantic-version tags, and resolves the tag's commit SHA. It never treats a push to `main` as deployment approval.
- `bf4br/fleet_upgrade.py` provides an **opt-in** single-host coordinator (currently hardcoded `hnl-01`) with an exclusive local lock, verified-commit archive staging, isolated virtualenv and pinned-SSH remote invocation. `--check` is read-only; `--deploy` is not yet approved for live use.
- `bf4br/release_switch.py` provides a remote, locked supervisor stop/switch/restart, a legacy-directory backup, and best-effort rollback on failed restart. This is an **initial implementation, not a production-certified updater**.
- Unit tests verify version eligibility, tag resolution, SHA mismatch rejection, and filesystem rollback; 15 unit tests pass and 10 PostgreSQL integration tests remain skipped without the disposable test DSN.
- **Safety gates still required:** explicit node pause/drain and database lease verification; robust post-restart worker/database health checks (service-active alone is insufficient); test interrupted/failed deployment and rollback in a disposable environment; protect immutable version directories from accidental overwrite; use a dedicated least-privilege remote deployment identity rather than unattended root SSH; production coordinator service/timer configuration and approved release pinning. The existing `bf4br-deployer.service` remains observation-only as `postgres` and has not been replaced or given root SSH access.
- The staged `/opt/bf4br-releases/v1.0.0` on `hnl-01` is not activated. The live `/opt/bf4br` directory and supervisor are unchanged. **Do not publish v1.0.1 until a verified v1.0.0 baseline is running under the coordinator.**

### Updater hardening progress

- Coordinator now pauses `hnl-01` through `bf4br.control` using local PostgreSQL peer authentication and waits for **zero node-owned leases** across both job queues before switching; it attempts to resume after the operation. Current live node remains unpaused.
- Remote switcher now checks systemd supervisor MainPID and runs a read-only PostgreSQL `SELECT 1` using the active release virtualenv and supervisor's configured DSN. This read-only health probe returned `healthy: True` on the live `hnl-01` installation.
- Existing version directories are rejected unless their SHA marker matches the release tag commit; a partial/unmarked staging directory requires deliberate cleanup and restaging. The previously staged `v1.0.0` has no marker and must be reconciled before deployment.
- Current tests: 17 passed, 10 skipped (disposable PostgreSQL integration DSN not configured). No live deployment switch, rollback injection, or automatic release polling has been performed.
- **Still blocked for unattended activation:** least-privilege remote deployment identity (the existing root SSH key is too broad); database lease draining under real workloads and failure injection; atomic staging of incomplete directories; persistent systemd release watcher with a verified initial baseline and durable rollout state. The original observation-only service remains active.
## Planned v1.0.2: distributed queue feed and randomized persona claims

- `bf4br.feeder` runs on the PostgreSQL/coordinator host only, not collector nodes. It checks due-ready queue depths every 60 seconds and inserts up to 250 new personas/reports per cycle for queues below 250, targeting a maximum of 1,000 due-ready entries per queue per refill. Inserts are idempotent; previously discovered rows remain intact.
- Persona claims use randomized eligible-row selection with `FOR UPDATE SKIP LOCKED`, retaining exclusive leases, fencing, checkpoints, and retry scheduling. Report claims retain chronological due ordering.
- `bf4br.fleet_upgrade` discovers registered collector nodes from `bf4br_node_controls` (excluding the coordinator hostname aliases) and upgrades them sequentially, staging a published immutable release and draining each host before switching, with health check and rollback. Existing v1.0.1 installs without a release-state marker are verified using the immutable SHA marker.
- Enable feeder on the coordinator only after release publication and validation: install `deploy/systemd/bf4br-feeder.service` as `/etc/systemd/system/bf4br-feeder.service`, then `systemctl daemon-reload && systemctl enable --now bf4br-feeder.service`.
- Host rename from `reports` to `rnt-reports` is a separate infrastructure operation; keep compatibility alias and check backups, SSH, monitoring, and hostname-based references before changing it. No hostname change is included in this code release.
- Note: initial feeder seeding scans existing player/discovery tables. Measure database query costs and report queue growth before increasing thresholds or expanding beyond two collectors.
