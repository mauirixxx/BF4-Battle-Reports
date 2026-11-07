-- BF4BR v2 rolling detail pipeline: multiple active reports are allowed.
-- Required after 0007 and before enabling detail workers.
BEGIN;
SET LOCAL lock_timeout='5s';
DROP INDEX IF EXISTS bf4br_detail_one_active_idx;
CREATE INDEX IF NOT EXISTS bf4br_detail_active_order_idx
 ON bf4br_detail_reports (report_timestamp DESC,platform,battlelog_report_id)
 WHERE state='active';
COMMIT;
