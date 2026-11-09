-- Development-only migration: do NOT apply until integration acceptance.
-- Tracks external batch lifecycle independently of report-centric completion.
BEGIN;
SET LOCAL lock_timeout = '5s';
CREATE TABLE bf4br_external_workers (
 worker_id text PRIMARY KEY,
 key_sha256 char(64) NOT NULL UNIQUE,
 enabled boolean NOT NULL DEFAULT true,
 cooldown_until timestamptz NOT NULL DEFAULT '-infinity'::timestamptz,
 active_batch_id uuid,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 CHECK (length(worker_id) BETWEEN 1 AND 128),
 CHECK (key_sha256 ~ '^[0-9a-f]{64}$')
);
CREATE TABLE bf4br_external_batches (
 batch_id uuid PRIMARY KEY,
 worker_id text NOT NULL REFERENCES bf4br_external_workers(worker_id),
 platform smallint NOT NULL CHECK (platform IN (1,32,64)),
 persona_id bigint NOT NULL CHECK (persona_id > 0),
 state text NOT NULL DEFAULT 'active' CHECK (state IN ('active','completed','expired')),
 created_at timestamptz NOT NULL DEFAULT now(),
 completed_at timestamptz,
 updated_at timestamptz NOT NULL DEFAULT now(),
 CHECK ((state='completed') = (completed_at IS NOT NULL))
);
CREATE TABLE bf4br_external_batch_items (
 batch_id uuid NOT NULL REFERENCES bf4br_external_batches(batch_id),
 platform smallint NOT NULL,
 battlelog_report_id bigint NOT NULL,
 persona_id bigint NOT NULL,
 lease_token uuid NOT NULL,
 PRIMARY KEY(batch_id,platform,battlelog_report_id,persona_id),
 FOREIGN KEY(platform,battlelog_report_id,persona_id)
   REFERENCES bf4br_detail_players(platform,battlelog_report_id,persona_id)
);
CREATE INDEX bf4br_external_batch_worker_idx
 ON bf4br_external_batches(worker_id,created_at DESC);
CREATE INDEX bf4br_external_batch_item_job_idx
 ON bf4br_external_batch_items(platform,battlelog_report_id,persona_id);
ALTER TABLE bf4br_external_workers
 ADD CONSTRAINT bf4br_external_worker_active_batch_fkey
 FOREIGN KEY(active_batch_id) REFERENCES bf4br_external_batches(batch_id)
 DEFERRABLE INITIALLY DEFERRED;
-- Deliberately no grant to existing bf4br_collector: API uses a dedicated role.
COMMIT;

[executed on device: reports (d4380674-2627-4f06-a351-173869e82fbe)]