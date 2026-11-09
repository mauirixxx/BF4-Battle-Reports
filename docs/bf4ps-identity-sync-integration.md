# BF4BR → BF4PS identity and name-history integration

Status: **production active, 2026-11-08**. This describes the existing outbound read-only integration; it is **not** an inbound enrichment API.

## Data flow and ownership

BF4BR PostgreSQL database `bf4_battle_reports` on `reports` (192.168.200.49) is the source of player identities and observed names. A standalone BF4PS importer on `tcou` (192.168.10.71) reads BF4BR using PostgreSQL role `bf4br_identity_sync`, which has only CONNECT, schema USAGE, and SELECT on `public.players` and `public.player_name_history`. PostgreSQL 18 `pg_hba.conf` permits that role from tcou's /32 using SCRAM; secrets live in `/etc/bf4-player-stats/bf4br-sync.env` on tcou, never in Git.

The importer code, systemd service and timer are managed on the BF4PS side: `player-collector/bf4ps/bf4br_identity_sync.py`, `bf4ps-bf4br-sync.service`, `bf4ps-bf4br-sync.timer`. It independently reads BF4BR source rows in ascending IDs, persists BF4PS soldiers and searchable aliases, and checkpoints source IDs in BF4PS `discovery_state` under `bf4br_identities` and `bf4br_names`. The checkpoints are source-row IDs, not counts of new soldiers.

## Semantics

BF4BR `players` includes `id`, `platform`, `persona_id`, `current_name`, and `current_name_observed_at`; `player_name_history` includes `id`, `player_id`, `player_name`, and `observed_at`. Platform codes 1, 32, 64 map to BF4PS pc, ps4, xboxone. Existing BF4PS current names are never overwritten; observed names are recorded as aliases. Historical report timestamps are **not** name observation timestamps: Battlelog may return the name current at download time for an old report. BF4PS active player exclusions are respected.

BF4PS's existing BF4SW discovery path remains separate and unchanged. There is no BF4PS → BF4BR reverse sync, no BF4SW → BF4BR feed, and no direct external PostgreSQL write permission.

## Operations and caveats

The importer uses short batches (currently 100 identities per transaction), retries PostgreSQL deadlock SQLSTATE 40P01 with bounded backoff, and logs scanned/new/duplicate/excluded/invalid identity outcomes per committed batch. The oneshot invocation bounds each stream to 10,000 source rows; the timer schedules repeat runs. Operators on tcou can use `journalctl -u bf4ps-bf4br-sync.service -f` and `/usr/local/bin/bf4br-sync-progress`. The name-history stream may lag the identity stream. Do not reset either cursor without a planned replay.

## Future inbound player-enrichment API — design only

A future external-worker API should be a separately authenticated service that validates submissions and writes to BF4BR through a narrowly privileged server-side database role. It should not reuse `bf4br_identity_sync` (read-only) or expose PostgreSQL credentials to external workers. Before implementation, define trusted worker identity, authorization scope, versioned request schema, payload size and rate limits, idempotency/deduplication keys, provenance and observation timestamps, report/player identity reconciliation, rejection semantics, auditability, and operational rollout/rollback. Database migrations and this schema reference must be updated together if persistence changes.
