-- BF4BR archive partial-name search acceleration.
-- Run each statement outside a transaction; CREATE INDEX CONCURRENTLY cannot run in one.
-- Production deployed 2026-11-14; idempotent for existing valid indexes.
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_bf4br_players_current_name_trgm ON public.players USING gin (lower(current_name) gin_trgm_ops);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_bf4br_report_players_observed_name_trgm ON public.report_players USING gin (lower(player_name_observed) gin_trgm_ops);