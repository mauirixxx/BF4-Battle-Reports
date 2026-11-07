-- BF4BR v2.0.0: additive player-specific report enrichment storage.
-- Apply once after 0001..0006, before enabling any v2 detail workers.
-- Generic reports, generic workers, and existing assignments remain unchanged.
BEGIN;
SET LOCAL lock_timeout = '5s';
CREATE TABLE IF NOT EXISTS bf4br_detail_reports (
 platform smallint NOT NULL CHECK (platform IN (1,32,64)),
 battlelog_report_id bigint NOT NULL CHECK (battlelog_report_id > 0),
 report_timestamp timestamptz NOT NULL,
 state text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','active','complete','deferred')),
 expected_players integer NOT NULL DEFAULT 0 CHECK (expected_players >= 0),
 retry_after timestamptz NOT NULL DEFAULT now(),
 activated_at timestamptz,
 completed_at timestamptz,
 last_error text,
 updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(platform,battlelog_report_id),
 FOREIGN KEY(platform,battlelog_report_id) REFERENCES battle_reports(platform,battlelog_report_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS bf4br_detail_one_active_idx ON bf4br_detail_reports ((1)) WHERE state='active';
CREATE INDEX IF NOT EXISTS bf4br_detail_report_pick_idx ON bf4br_detail_reports (report_timestamp DESC,platform,battlelog_report_id) WHERE state IN ('pending','deferred');
CREATE TABLE IF NOT EXISTS bf4br_detail_players (
 platform smallint NOT NULL,
 battlelog_report_id bigint NOT NULL,
 persona_id bigint NOT NULL CHECK (persona_id > 0),
 state text NOT NULL DEFAULT 'ready' CHECK (state IN ('ready','leased','done','retry')),
 lease_owner text,
 lease_token uuid,
 lease_until timestamptz,
 next_attempt_at timestamptz NOT NULL DEFAULT now(),
 failures integer NOT NULL DEFAULT 0 CHECK (failures >= 0),
 last_error text,
 updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(platform,battlelog_report_id,persona_id),
 FOREIGN KEY(platform,battlelog_report_id) REFERENCES bf4br_detail_reports(platform,battlelog_report_id),
 FOREIGN KEY(platform,persona_id) REFERENCES players(platform,persona_id)
);
CREATE INDEX IF NOT EXISTS bf4br_detail_player_claim_idx ON bf4br_detail_players(platform,battlelog_report_id,next_attempt_at) WHERE state IN ('ready','retry');
CREATE INDEX IF NOT EXISTS bf4br_detail_player_expired_idx ON bf4br_detail_players(lease_until) WHERE state='leased';
CREATE TABLE IF NOT EXISTS bf4br_player_report_raw (
 platform smallint NOT NULL,
 battlelog_report_id bigint NOT NULL,
 persona_id bigint NOT NULL CHECK (persona_id > 0),
 raw_response jsonb NOT NULL,
 fetched_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(platform,battlelog_report_id,persona_id),
 FOREIGN KEY(platform,battlelog_report_id,persona_id) REFERENCES bf4br_detail_players(platform,battlelog_report_id,persona_id)
);
GRANT SELECT,INSERT,UPDATE,DELETE ON bf4br_detail_reports,bf4br_detail_players,bf4br_player_report_raw TO bf4br_collector;
COMMIT;
