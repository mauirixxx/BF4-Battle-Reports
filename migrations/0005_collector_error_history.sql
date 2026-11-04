-- v1.0.10: append-only collector failure history; existing queues unchanged.
BEGIN;
CREATE TABLE IF NOT EXISTS bf4br_collector_error_history (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 occurred_at timestamptz NOT NULL DEFAULT now(),
 node_name text NOT NULL,
 worker_id text NOT NULL,
 job_kind text NOT NULL CHECK (job_kind IN ('historical_persona','daily_persona','report','daily_report')),
 platform smallint NOT NULL CHECK (platform IN (1,32,64)),
 item_id bigint NOT NULL,
 day_utc date,
 error_message text NOT NULL
);
CREATE INDEX IF NOT EXISTS bf4br_collector_error_history_recent_idx ON bf4br_collector_error_history (occurred_at DESC);
GRANT SELECT ON bf4br_collector_error_history TO "www-data";
COMMIT;
