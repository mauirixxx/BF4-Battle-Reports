-- v1.0.10 hotfix: permit collector role to append error history.
-- Apply after 0005. No existing data or schema objects are removed.
BEGIN;
GRANT INSERT ON TABLE bf4br_collector_error_history TO bf4br_collector;
GRANT USAGE ON SEQUENCE bf4br_collector_error_history_id_seq TO bf4br_collector;
COMMIT;
