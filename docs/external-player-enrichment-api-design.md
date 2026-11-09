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

## Development checkpoint — atomic player/report reservation (2026-11-09 UTC)

`bf4br/external_enrichment_selection.py` provides advisory read-only candidate discovery. `bf4br/external_enrichment_claim.py` now provides a **transactional reservation primitive**: lock one `players` row with `FOR UPDATE SKIP LOCKED`, find up to 40 newest eligible report memberships, create missing report/job parents, and fence each claimed `bf4br_detail_players` row with its own UUID token and lease. It rechecks durable raw duplicates and existing job leases during the update. This reuses the existing v2 job lease table rather than creating an incompatible second queue. It does **not** activate a report or mark a report complete. The API layer must use the returned per-report tokens, not treat them as one shared token.

Current validation is **eight mock-based unit tests** covering selection and reservation SQL structure, limits and empty/locked-player behavior. These do not establish real PostgreSQL transactional behavior, fairness, speed, or compatibility under concurrent production writes. No database migration or production listener has been applied. Before deployment: reconcile the report-centric coordinator settlement behavior, test live-schema-compatible transactions inside a rolled-back integration database, test concurrent claims, add claim renewal and explicit failure/release handling, and implement authenticated API endpoints. Avoid enabling this development primitive directly on production.

## HTTP prototype checkpoint (not deployable)

`bf4br/external_enrichment_api.py` now sketches a FastAPI health endpoint, bearer-key authentication, claim, per-report renewal, upload (reusing `save_player`), and explicit retry release. Dependencies are isolated in `requirements-api.txt` and are **not installed** in the host's system Python. The prototype is deliberately **not activated**. Remaining blockers: a durable worker/batch assignment ledger; worker ownership checks on every mutation (the existing per-report token alone is insufficient for worker-level authorization); server-enforced cooldowns; idempotent submission acknowledgements after lost HTTP responses; explicit batch completion; payload-size limits; request throttling; safe status handling; and real PostgreSQL concurrency/integration tests. The initial claim primitive now excludes existing `active`/`complete` report-centric parents to protect their roster-count invariant; this restriction may reduce fill rate and requires a designed compatibility policy before activation.

## Development checkpoint — worker ownership fencing

`bf4br/external_enrichment_ownership.py` wraps the existing v2 save/renew/retry operations with an explicit `lease_owner`, `lease_token`, `state='leased'`, unexpired-lease check under `SELECT ... FOR UPDATE`, held through the mutation in one transaction. The API now uses these worker-specific wrappers, so possession of another worker's UUID alone is not sufficient to mutate its job. This is a development hardening step, **not** a production authorization audit. The API still lacks per-worker key registry, server-side rate/cooldown enforcement, idempotent acknowledgements, batch completion, and payload-size limits. FastAPI dependencies are not installed in system Python; API tests remain skipped until isolated installation.

## Development checkpoint — proposed durable batch schema (not deployed)

Migration `0009_external_enrichment_batches.sql` proposes a worker registry, durable batch header and batch item ledger. `bf4br/external_enrichment_batch.py` prototypes serialized per-worker batch creation and completion plus a conservative 61-second server-side cooldown beginning at batch completion acknowledgement. This **does not yet wire into the HTTP API** and has not been integration tested. Important outstanding design work: batch recovery on crashes, expired batch ownership, 429 cooldown reporting, token ownership checks against batch items, lost-response idempotency, and ensuring `start_batch` and the reservation callback use one atomic transaction. Do not deploy this migration until these gates are resolved.

## Development checkpoint — API/batch ledger integration (not deployed)

The claim endpoint now invokes `start_batch()` around random player discovery and `claim_player_batch()` in a single nested transaction, returning `batch_id` and per-report tokens. Renew/upload/fail require a matching active batch item in addition to the existing worker/token lease fencing. `POST /api/v1/work/complete` now invokes `finish_batch()` and starts the conservative 61-second server cooldown. On a later claim, an abandoned active batch with no still-valid owned leases is marked `expired`, and cooldown is set before another claim; cleanup commits before the API reports a 429 cooldown. **No migration has been applied and this has not been tested against PostgreSQL.** The present prototype still requires stronger synchronization between batch ownership checks and batch completion, idempotent uploads, 429 policy persistence, per-worker key authentication, payload limits, and proper live-schema integration testing. No API process is running.

## First PostgreSQL integration acceptance — isolated scratch database (2026-11-09)

Created a separate `bf4br_external_api_test` PostgreSQL database on the reports host, restored production **schema only**, and applied proposed migration 0009 there. `tests/integration_external_enrichment_postgres.py` uses synthetic server/player/report memberships and two competing worker connections. **PASS**: 40 newest of 45 reports; exactly one worker reserves the player; foreign-worker lease mutation rejected; one valid player response saved; premature batch completion rejected; other jobs released for retry; batch completion sets a future cooldown. The test truncates only its named scratch database fixtures and must never target production. First run found a psycopg timestamp decoding failure for the `'-infinity'` worker cooldown default; corrected by querying only the active batch UUID and evaluating cooldown server-side as a boolean. The integration test passed after this correction.

This is a first integration gate, not rollout approval: additional tests are required for the existing report-centric coordinator, cross-worker report overlaps, crashes and lease expiry, 429 policy, HTTP authentication and payload bounds, and concurrency stress. No production migration, service, or proxy change was made.

## Crash/recovery and coordinator integration (scratch, 2026-11-09)

Added `tests/integration_external_enrichment_recovery.py`, run after the first scratch integration fixture. **PASS**: real report-centric `activate()` preserves its expected-player roster invariant; player-centric selection skips the activated report; forced lease expiration simulates a dead worker; the next claim expires its abandoned batch and persists a 61-second cooldown; a later claim can reclaim the eligible work. Added `FOR UPDATE` on the external worker row during batch-item membership validation to serialize it against batch completion and replacement (API mutation handlers hold the surrounding transaction). These checks are isolated to `bf4br_external_api_test`; no production database modification. Outstanding: 429-specific server cooldown persistence, real HTTP-level tests and dependency installation, per-worker API-key registry, upload retry idempotency, request size limits, and stress testing with multiple distinct players.

## API boundary hardening checkpoint (2026-11-09)

Authentication now resolves the SHA-256 bearer token against the proposed `bf4br_external_workers` registry and rejects disabled/unrecognized workers. This replaces the prototype's single process-wide key. FastAPI middleware enforces a 2 MiB request body cap (both declared Content-Length and streamed content). HTTP tests now run using FastAPI/httpx; 21 unit/API tests passed and both scratch PostgreSQL integration scenarios passed. For testing, FastAPI and httpx were installed in the pre-existing `/opt/bf4br/.venv` environment on the reports host; no API service was started and no production schema migration applied. Before deployment, isolate API dependencies into a dedicated venv, verify per-worker authentication end-to-end against scratch PostgreSQL, implement 429-specific durable cooldown and idempotent upload acknowledgements, and test the reverse proxy and request-size enforcement against actual ASGI HTTP traffic.

## Durable HTTP 429 reporting checkpoint (2026-11-09)

Added `POST /api/v1/work/rate-limited` with an authenticated `batch_id` and `retry_after_seconds` constrained to 180..86400. The server locks the worker's active batch and persists `cooldown_until=GREATEST(existing,now()+duration)`, without releasing or renewing individual report leases. In scratch PostgreSQL, `tests/integration_external_enrichment_rate_limit.py` confirms a 300-second cooldown, rejects another worker's batch, and verifies crash recovery does not shorten the 429 cooldown to the ordinary 61-second floor. The suite passed 23 unit/API tests plus 3 scratch PostgreSQL scenarios. Outstanding: the external client must report 429s; idempotent upload acknowledgement; full HTTP tests against scratch PostgreSQL; verify behavior of leases during extended cooldown and complete/fail semantics. Production remains untouched.

## Idempotent upload acknowledgement and ASGI HTTP acceptance (2026-11-09)

A repeated `POST /api/v1/enrichment` now acknowledges the *identical* already-persisted JSON for the original worker/batch/item/token when the item is `done` and its batch is still `active` or `completed`. The duplicate path locks the worker before checking the batch ledger and saved JSON, preserving lock ordering with the normal lifecycle. A changed payload, different worker, or mismatched token is not accepted as an idempotent replay. The API returns `{'stored':true,'already_stored':true}` on a verified retry and `already_stored:false` on a new save. This permits recovery after a lost HTTP acknowledgement even if the worker completed the batch before retrying.

The first actual ASGI HTTP test exposed an issue with BaseHTTPMiddleware consuming the request body, yielding HTTP 422 for a valid upload. Replaced it with pure ASGI middleware that enforces the 2 MiB body cap, including streaming without Content-Length, then replays the buffered request body to FastAPI. `tests/integration_external_enrichment_http.py` passes against isolated scratch PostgreSQL with HTTP 200 for an identical retry, 409 for altered JSON, 401 for an invalid bearer key, and 413 for oversized requests. The complete scratch suite passed: 23 unit/API tests and five PostgreSQL scenarios (base claims, idempotency, HTTP, crash recovery, durable 429). No production schema, service, or proxy changes were made. Remaining gates include HTTP new-claim/new-save/fail/renew coverage, a dedicated API service identity and grants, client behavior, and reverse proxy validation.

[executed on device: reports (d4380674-2627-4f06-a351-173869e82fbe)]