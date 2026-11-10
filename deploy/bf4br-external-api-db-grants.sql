-- REVIEW BEFORE USE. Run after migration 0009, as a PostgreSQL administrator.
-- Create role/password separately using a secrets manager or psql prompt.
-- The API role must not inherit bf4br_collector privileges.
GRANT CONNECT ON DATABASE bf4_battle_reports TO bf4br_api;
GRANT USAGE ON SCHEMA public TO bf4br_api;
GRANT SELECT ON public.players, public.report_players, public.battle_reports,
    public.bf4br_detail_reports, public.bf4br_detail_players,
    public.bf4br_player_report_raw, public.bf4br_external_workers,
    public.bf4br_external_batches, public.bf4br_external_batch_items TO bf4br_api;
GRANT INSERT, UPDATE ON public.bf4br_detail_reports,
    public.bf4br_detail_players, public.bf4br_player_report_raw,
    public.bf4br_external_workers, public.bf4br_external_batches,
    public.bf4br_external_batch_items TO bf4br_api;
-- No DELETE, no schema DDL, no blanket grants to other tables.

[executed on device: reports (d4380674-2627-4f06-a351-173869e82fbe)]