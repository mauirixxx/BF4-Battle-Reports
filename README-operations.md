# Battle Reports manual operations

This is the standalone `bf4_battle_reports` project, not BF4PS. No scheduled runs.

## Discover a specific player's entire history

`python3 /opt/bf4reports/player_discovery.py --personaid 236753552`

Optionally supply `--platform 1` (PC), `32` (PlayStation), or `64` (Xbox). The platform is inferred when the persona exists on exactly one platform. The first successful targeted run scans newest to oldest until the history endpoint returns an empty list, even if older bounded history checkpoints exist. Later targeted runs scan only from newest until the previously completed high-water mark. All discovered report IDs and raw pages remain stored. Requests are spaced by 4 seconds and invalid HTTP-200 responses log their JSON type, response size, and a short preview. A failed/invalid page does not advance `history_persona_refreshes.last_success_at` or its high-water mark; a subsequent run retries from the newest page. `history_checkpoints` retains its original oldest-page semantics for bounded discovery.

## Download all eligible report IDs

`python3 /opt/bf4reports/bf4reports.py download --limit all`

Runs existing downloader in 100-item batches, with the existing 10-second request delay and 20-minute retry cooldown. Ctrl+C stops. A non-200 HTTP response stops immediately after its diagnostic is recorded. HTTP 200 with JSON null is an unsuccessful report attempt but does not stop the whole run. When no eligible work remains but report IDs are cooling down, the command sleeps until the earliest retry is eligible, then resumes automatically. It exits only when no pending cooldown work remains. A repeated identical batch without progress is treated as an error and stops.

The new PostgreSQL table `history_persona_refreshes` stores `(platform,persona_id)` plus `last_success_at`, `newest_report_at`, and `last_pages`. Existing `history_checkpoints` schema and bounded discovery behavior remain unchanged.