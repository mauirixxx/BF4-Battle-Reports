# Player-specific report enrichment — implementation plan

Status: design baseline; **not deployed**. Generic collection continues unchanged.

## Invariants
- Three daily nodes continue discovery and generic report collection for PC (1), PlayStation (32), Xbox (64).
- Seven former historical nodes will eventually perform player-detail enrichment. Preserve current deployment and pacing/429 policy until a tested, controlled role switch.
- Preserve generic raw JSON. Store persona-specific responses separately with a unique (platform, report ID, persona ID) key and identity validation.
- Enrich only from a successfully imported generic report, using its actual player roster; do not infer players from a different report or platform.
- One **globally active report** at a time; up to seven distinct persona claims within it. No duplicate concurrent persona claims.
- A newly imported report does not interrupt an active report. After active report reaches a terminal report-level state, choose the newest eligible report; otherwise work backward through backlog.
- Never publish a report as complete unless all expected persona payloads have been validated and durably stored.
- Transient failures, 429s, and shutdowns retain successful player payloads and resume safely. A persistently failing persona must not freeze global progress: defer the whole incomplete report with explicit status and retry time, without mislabeling it complete.
- Lease tokens fence stale workers. Expired leases are reclaimable. Coordinator selection must be transactionally serialized, resilient to restarts, and never have two active reports.
- Graceful drain finishes or safely checkpoints in-flight requests before role changes. Reuse existing per-node pacing and 429 cooldown; do not increase request frequency.
- A report with an empty or invalid roster is quarantined for investigation, not marked complete.

## Data model proposal (requires reconciliation with live schema before writing migration)
1. Report-level enrichment jobs: (platform, report ID), generic import timestamp, expected persona count, completed count, state (pending/active/complete/deferred), retry time, coordinator generation and timestamps.
2. Player-level enrichment jobs: (platform, report ID, persona ID), state (ready/leased/done/retry), lease owner/token/expiry, failures, next attempt, last error.
3. Player-specific immutable raw response archive keyed by (platform, report ID, persona ID), with fetch timestamp, source and validation metadata.
4. Report-level completion transaction verifies actual expected roster against persisted persona payloads; never rely solely on counters.
5. Indexed newest-first report selection and efficient ready-persona claims.

## Work phases
1. Read actual production table definitions and the full current migration chain; reconcile checked-out code against canonical GitHub main and preserve uncommitted operational edits.
2. Add additive migrations and schema documentation; no destructive changes to generic tables.
3. Implement persona-aware Battlelog fetcher with report/persona identity checks and a separate archive path.
4. Implement roster seeding, globally serialized report selection, distributed persona claims, lease renewal, retry/defer, and completion fencing.
5. Unit and PostgreSQL integration tests: seven-way uniqueness, new report arrival, crash/restart, partial writes, 429, stale leases, removed personas, cross-platform IDs, and final publication gate.
6. Controlled canary on one real report with seven nodes at current pacing; measure request counts, DB/WAL growth, rate limiting, and correctness.
7. Release through normal fleet updater; drain historical workers, switch roles in a controlled wave, monitor, and retain rollback to previous roles.
8. Add operational visibility: active report, platform, expected/completed/failed personas, newest pending, historical backlog, node ownership, and estimated throughput.

## Explicit non-goals
- No higher Battlelog request rate.
- No automatic historical backfill before canary and authorization.
- No replacement of generic JSON with persona JSON.
- No changes to daily collector assignments.
