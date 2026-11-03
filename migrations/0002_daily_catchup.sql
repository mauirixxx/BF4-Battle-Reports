-- BF4BR v1.0.5: independent daily catch-up state. Apply only after review.
-- Historical bf4br_persona_jobs cursors and leases are never modified.
BEGIN;
CREATE TABLE IF NOT EXISTS bf4br_daily_persona_jobs (
 day_utc date NOT NULL,
 platform smallint NOT NULL CHECK (platform IN (1,32,64)),
 persona_id bigint NOT NULL CHECK (persona_id>0),
 state text NOT NULL DEFAULT 'ready' CHECK (state IN ('ready','leased','done')),
 cursor_epoch bigint,
 next_attempt_at timestamptz NOT NULL DEFAULT now(),
 lease_owner text,
 lease_token uuid,
 lease_until timestamptz,
 failures integer NOT NULL DEFAULT 0,
 last_error text,
 updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(day_utc,platform,persona_id)
);
CREATE INDEX IF NOT EXISTS bf4br_daily_persona_ready_idx ON bf4br_daily_persona_jobs(day_utc,platform,next_attempt_at) WHERE state='ready';
CREATE INDEX IF NOT EXISTS bf4br_daily_persona_lease_idx ON bf4br_daily_persona_jobs(lease_until) WHERE state='leased';
CREATE TABLE IF NOT EXISTS bf4br_daily_report_jobs (
 day_utc date NOT NULL,
 platform smallint NOT NULL CHECK (platform IN (1,32,64)),
 battlelog_report_id bigint NOT NULL CHECK (battlelog_report_id>0),
 state text NOT NULL DEFAULT 'ready' CHECK (state IN ('ready','leased','done')),
 next_attempt_at timestamptz NOT NULL DEFAULT now(),
 lease_owner text,
 lease_token uuid,
 lease_until timestamptz,
 failures integer NOT NULL DEFAULT 0,
 last_error text,
 updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(day_utc,platform,battlelog_report_id)
);
CREATE INDEX IF NOT EXISTS bf4br_daily_report_ready_idx ON bf4br_daily_report_jobs(day_utc,platform,next_attempt_at) WHERE state='ready';
CREATE INDEX IF NOT EXISTS bf4br_daily_report_lease_idx ON bf4br_daily_report_jobs(lease_until) WHERE state='leased';
CREATE TABLE IF NOT EXISTS bf4br_daily_windows (
 day_utc date PRIMARY KEY,
 created_at timestamptz NOT NULL DEFAULT now(),
 last_import_at timestamptz,
 missing_persona_sessions bigint NOT NULL DEFAULT 0,
 unsupported_platform_sessions bigint NOT NULL DEFAULT 0,
 imported_personas bigint NOT NULL DEFAULT 0
);
COMMIT;
