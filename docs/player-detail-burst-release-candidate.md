# BF4BR player-detail burst — release candidate notes

Status: feature branch ready for controlled production activation; **not tagged or deployed**.

## Changes
- Opt-in four-way concurrent Battlelog player-detail HTTP downloads.
- At most 40 player-specific requests per batch, then 61 seconds of node-wide rest after the final response.
- Claim player jobs only when an HTTP slot becomes available; preserve 120-second fenced leases and the existing retry/persistence path.
- One PostgreSQL connection on the dispatcher thread; network concurrency does not increase DB connection count.
- Shared node-local flock prevents persona/report collectors from interleaving with an active burst; HTTP 429 stops new dispatch and publishes the existing node-wide cooldown (minimum 180 seconds or Retry-After).
- Existing generic report collection is unchanged; burst activation requires BF4BR_DETAIL_BURST_ENABLED=1 and the separate existing detail-worker enablement.

## Verification
- 113 Python unittest cases executed in the BF4BR runtime environment; OK, 20 skipped.
- Detail batch, four-way dispatch, 429 stop, incremental claims, and 61-second cooldown covered by isolated tests.
- No PostgreSQL load benchmark required or performed, per operator direction.
- Live Battlelog performance and 429 behavior remain to be observed after activation.

## Rollout and rollback
- Keep the feature opt-in; enable detail enrichment and burst pacing on an intended node, observe HTTP status, retry queue, and completion before broad activation.
- Rollback by disabling BF4BR_DETAIL_BURST_ENABLED, or disabling detail enrichment entirely; generic report workers continue unaffected.
- No schema migration introduced by this burst change.
