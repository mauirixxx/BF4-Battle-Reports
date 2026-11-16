-- BF4BR manual report submission: additive queue priority metadata.
-- Staged only. Apply after worker code and integration tests are accepted.
BEGIN;
SET LOCAL lock_timeout = '5s';
ALTER TABLE bf4br_report_jobs ADD COLUMN IF NOT EXISTS manual_priority boolean NOT NULL DEFAULT false;
ALTER TABLE bf4br_detail_reports ADD COLUMN IF NOT EXISTS manual_priority boolean NOT NULL DEFAULT false;
CREATE TABLE IF NOT EXISTS bf4br_manual_report_requests (
 platform smallint NOT NULL CHECK (platform IN (1,32,64)),
 battlelog_report_id bigint NOT NULL CHECK (battlelog_report_id > 0),
 requested_persona_id bigint CHECK (requested_persona_id > 0),
 requested_at timestamptz NOT NULL DEFAULT now(),
 last_requested_at timestamptz NOT NULL DEFAULT now(),
 request_count integer NOT NULL DEFAULT 1 CHECK (request_count > 0),
 PRIMARY KEY(platform,battlelog_report_id)
);
-- No web-role INSERT grant: a restricted submission service must validate/rate-limit requests.
COMMIT;
