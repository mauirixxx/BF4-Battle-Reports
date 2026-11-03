CREATE TABLE servers(id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,server_guid uuid UNIQUE,current_name text);
CREATE TABLE battle_reports(id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 platform smallint,battlelog_report_id bigint,server_id bigint,report_timestamp timestamptz,
 collected_at timestamptz,UNIQUE(platform,battlelog_report_id));
CREATE TABLE players(id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 platform smallint,persona_id bigint,current_name text,current_name_observed_at timestamptz,
 earliest_report_at timestamptz,latest_report_at timestamptz,UNIQUE(platform,persona_id));
CREATE TABLE report_players(report_id bigint,player_id bigint,player_name_observed text,PRIMARY KEY(report_id,player_id));
CREATE TABLE player_name_history(id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 player_id bigint,player_name text,observed_at timestamptz,source_report_id bigint);
