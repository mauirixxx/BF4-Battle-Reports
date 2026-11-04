# BF4BR coordinator-managed request policy

Status: staged design; migration 0004 is committed but not applied, and v1.0.8 workers still use static 10s/180s constants.

## Configuration

`bf4br_node_controls.request_interval_seconds` defaults to 10 (valid 1..3600). `http_429_cooldown_seconds` defaults to 180 (valid 30..86400). Worker counts, pause state and coordinated role assignments remain as-is.

## Required implementation before activation

1. Supervisor reads both policy columns during its existing DB poll, validates values, and atomically publishes a node-local policy JSON file accessible to worker processes. Publish only after a successful DB read; on DB loss retain last known policy.
2. The existing `node_cooldown.guarded_request` reads the policy under the same flock used for request serialization, with v1.0.8 defaults if no valid policy is available. Preserve request timestamp and 429 cooldown state across policy changes and process restarts. Continue to honor longer HTTP Retry-After.
3. Extend `bf4br.control` with validated `set --request-interval-seconds` and `--http-429-cooldown-seconds`; show current values. Do not allow zero or negative delays.
4. Test mixed persona/report concurrency, runtime changes while requests are active, crash/restart, malformed config, unavailable DB, Retry-After precedence, and rolling compatibility. Ensure waiting workers renew leases or wait before claiming.
5. Apply migration to the coordinator database before deploying policy-aware workers. Canary one node, then roll across fleet, monitor 429 rates and collection progress. Preserve rollback to v1.0.8 defaults.

Future: fleet-wide defaults with per-node overrides, UI and adaptive controls; do not automatically reduce rate limits without safeguards.
