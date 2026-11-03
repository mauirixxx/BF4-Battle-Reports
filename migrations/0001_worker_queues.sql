-- BF4BR additive queue migration; existing report tables remain unchanged.
BEGIN;
CREATE TABLE IF NOT EXISTS bf4br_persona_jobs (
 platform smallint NOT NULL CHECK (platform IN (1,32,64)),
 persona_id bigint NOT NULL CHECK (persona_id > 0),
 state text NOT NULL DEFAULT 'ready' CHECK (state IN ('ready','leased','done')),
 cursor_epoch bigint,
 newest_epoch bigint,
 boundary_epoch bigint,
 last_completed_at timestamptz,
 next_attempt_at timestamptz NOT NULL DEFAULT now(),
 lease_owner text,
 lease_token uuid,
 lease_until timestamptz,
 failures integer NOT NULL DEFAULT 0,
 last_error text,
 updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(platform,persona_id)
);
CREATE INDEX IF NOT EXISTS bf4br_persona_ready_idx ON bf4br_persona_jobs(next_attempt_at) WHERE state='ready';
CREATE INDEX IF NOT EXISTS bf4br_persona_lease_idx ON bf4br_persona_jobs(lease_until) WHERE state='leased';
CREATE TABLE IF NOT EXISTS bf4br_report_jobs (
 platform smallint NOT NULL CHECK (platform IN (1,32,64)),
 battlelog_report_id bigint NOT NULL,
 state text NOT NULL DEFAULT 'ready' CHECK (state IN ('ready','leased','done')),
 next_attempt_at timestamptz NOT NULL DEFAULT now(),
 lease_owner text,
 lease_token uuid,
 lease_until timestamptz,
 failures integer NOT NULL DEFAULT 0,
 last_error text,
 updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(platform,battlelog_report_id)
);
CREATE INDEX IF NOT EXISTS bf4br_report_ready_idx ON bf4br_report_jobs(next_attempt_at) WHERE state='ready';
CREATE INDEX IF NOT EXISTS bf4br_report_lease_idx ON bf4br_report_jobs(lease_until) WHERE state='leased';
CREATE TABLE IF NOT EXISTS bf4br_node_controls (
 node_name text PRIMARY KEY,
 persona_workers integer NOT NULL DEFAULT 3 CHECK (persona_workers BETWEEN 0 AND 64),
 report_workers integer NOT NULL DEFAULT 1 CHECK (report_workers BETWEEN 0 AND 64),
 paused boolean NOT NULL DEFAULT false,
 updated_at timestamptz NOT NULL DEFAULT now()
);
COMMIT;
