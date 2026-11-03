-- Disposable integration-only subset of the pre-existing BF4BR schema.
CREATE TABLE history_discoveries (
 platform smallint NOT NULL,battlelog_report_id bigint NOT NULL,
 report_timestamp timestamptz NOT NULL,server_name text,map_code text,
 first_seen_at timestamptz NOT NULL DEFAULT now(),
 last_seen_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(platform,battlelog_report_id));
CREATE TABLE history_report_sources (
 platform smallint NOT NULL,persona_id bigint NOT NULL,
 battlelog_report_id bigint NOT NULL,discovered_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(platform,persona_id,battlelog_report_id));
CREATE TABLE history_pages (
 platform smallint NOT NULL,persona_id bigint NOT NULL,cursor_used bigint NOT NULL,
 retrieved_at timestamptz NOT NULL DEFAULT now(),raw_response jsonb NOT NULL,
 report_count integer NOT NULL,next_cursor bigint,
 PRIMARY KEY(platform,persona_id,cursor_used));
CREATE TABLE history_persona_refreshes (
 platform smallint NOT NULL,persona_id bigint NOT NULL,
 last_success_at timestamptz NOT NULL DEFAULT now(),
 newest_report_at timestamptz,last_pages integer NOT NULL DEFAULT 0,
 PRIMARY KEY(platform,persona_id));
