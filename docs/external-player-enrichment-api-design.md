# External player-centric enrichment API — implementation design

Status: **design and development only; no production API, listener, migration, or worker activated**.

## User-approved cycle

1. An authenticated external worker calls `POST /api/v1/work/claim` to receive one random eligible `(platform, persona_id)` and up to **40 most recent unenriched** report IDs, ordered by actual report timestamp descending (tie-break by report ID). Search older reports to fill the batch; do not stop at the newest 40 reports if some are already enriched. Never assign a report for another persona simply because it appears in the same scoreboard.
2. The worker fetches only that player's detail endpoint for the assigned reports, uploads each valid response via `POST /api/v1/enrichment`, and acknowledges the batch via `POST /api/v1/work/complete` (including explicit failures/retries). Do not accept a worker's assertion that a report is complete without validated persisted data.
3. After the **last Battlelog request completes**, the worker waits **61 seconds** before the next player's Battlelog requests. API calls and uploads do not count as Battlelog requests. Honor HTTP 429 and Retry-After with the longer cooldown; persist the cooldown across worker restarts. Never use a 61-second sleep as a substitute for a 429 cooldown.
4. Repeat indefinitely. Empty-eligibility responses use a bounded backoff, not busy polling.

## Public route and runtime

Use Python FastAPI/ASGI on the `reports` host bound to loopback only, behind Apache. Existing public reverse proxy at `reports.bf4playerstats.com` must forward `/api/` to the ASGI service without changing `/` and existing PHP report pages. Expose `/api/v1/health` for readiness and authenticated worker endpoints. API versioning starts at v1. Do not expose PostgreSQL to external workers.

## Identity, authorization and validation

- Worker credentials are per-worker revocable API keys; store only hashes server-side, use TLS, avoid credentials in query strings and logs. Separate claim/submit/admin scopes. Restrict payload size, content type, JSON nesting, request rates and concurrency. Record worker ID, submission timestamp and failure reason for audit.
- Claim response contains a unique batch ID, a fencing token, `(platform, persona_id)`, report IDs, expiration, and server time. Use secure unpredictable tokens; validate ownership on every submission. Workers must be able to renew leases while fetching a 40-report batch, and resume/reconcile after a crash. Do not set a fixed 120-second batch lease without renewal.
- Validate `payload.id`, `payload.platform`, `payload.players[persona_id]`, `payload.playerReport.personaId`, and `payload.playerReport.stats` using the existing `bf4br.detail_queue.save_player` identity rules. Store original validated JSON, not just derived stats. Reject wrong persona, platform, report, stale token, invalid JSON and oversized payload. Repeat identical submissions are idempotent; conflicting payloads are flagged for review, not silently overwritten.

## Existing schema and concurrency boundaries

Production migrations `0007_player_detail_enrichment.sql` and `0008_rolling_detail_pipeline.sql` already provide `bf4br_detail_reports`, `bf4br_detail_players`, and `bf4br_player_report_raw`. The existing v2 pipeline is **report-centric** and its player jobs require a parent report row. New selection is **player-centric**, so do not simply reuse `claim_player()` or mark a report `complete` when one persona succeeds. The existing unique raw key `(platform,battlelog_report_id,persona_id)` is the durable duplicate boundary.

Source membership is `report_players` joined to `battle_reports` and `players`; report time comes from `battle_reports`, not a name observation timestamp. Candidate selection must exclude existing raw rows, active unexpired leases, and ineligible retry states. Atomic reservations must prevent two external workers and the existing ten-node detail fleet from claiming the same player/report pair. Before writing SQL, reconcile the production schema and migration chain, benchmark newest-first membership lookup, and decide whether to extend `bf4br_detail_players` or add a dedicated player-batch table with a shared reservation mechanism. Do not introduce a second, disconnected lease system.

Avoid `ORDER BY random()` across the full million-plus-player table. Use an indexed, bounded candidate-selection strategy with randomized starting points and a bounded fallback; verify fairness and eligibility under sparse coverage. Track exhausted players and re-evaluate when new reports arrive or retry windows expire.

## Failure semantics

- Only validated and durably committed payloads become `done`.
- Lease expiry and process crashes return unfinished work to the eligible pool after a bounded retry delay; stale tokens cannot overwrite new owners.
- On 429, stop dispatch, honor Retry-After/minimum cooldown, and release or renew outstanding leases appropriately.
- Enforce per-worker pacing server-side where possible, but the external worker remains responsible for its Battlelog request cadence. Do not allow repeated API claims to bypass cooldown.
- Keep generic report collection, BF4PS identity import, and existing ten-node assignments unchanged during development.

## Implementation gates

1. Verify production table definitions, keys, indexes, existing detail worker state machine, and Apache routing.
2. Write migration and update `docs/database-schema-reference.md` in the same change; create scoped API role/credentials only after review.
3. Implement pure candidate-selection and validation functions, then transactional claim, renewal, submission, completion, and recovery.
4. Unit and PostgreSQL integration tests: 40 newest **unenriched** ordering, duplicates, concurrent claims, stale token, invalid persona, partial completion, retries, crash, 429, and compatibility with existing report-centric workers.
5. Local loopback API canary, Apache `/api` routing test, then one external worker canary. No fleet changes or broad activation without acceptance results.

[executed on device: reports (d4380674-2627-4f06-a351-173869e82fbe)]