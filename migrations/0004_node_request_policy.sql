-- BF4BR request policy; additive migration, apply before enabling policy-aware workers.
BEGIN;
ALTER TABLE bf4br_node_controls
  ADD COLUMN IF NOT EXISTS request_interval_seconds integer NOT NULL DEFAULT 10
    CHECK (request_interval_seconds BETWEEN 1 AND 3600),
  ADD COLUMN IF NOT EXISTS http_429_cooldown_seconds integer NOT NULL DEFAULT 180
    CHECK (http_429_cooldown_seconds BETWEEN 30 AND 86400);
COMMIT;
