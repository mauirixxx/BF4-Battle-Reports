# BF4BR production database schema reference

Verified from live PostgreSQL 18.6 database `bf4_battle_reports` on `rnt-reports` on 2026-11-16 using `pg_dump --schema-only --no-owner --no-privileges`.

**Developer rule:** Before schema-dependent changes, inspect this reference, the current SQL migrations, and the live schema. Reconcile any discrepancies before implementation; update this reference with every schema change. This is a documentation snapshot, **not** a migration to execute.

## Full live DDL snapshot

```sql
--
-- PostgreSQL database dump
--


-- Dumped from database version 18.6 (Ubuntu 18.6-0ubuntu0.26.04.1)
-- Dumped by pg_dump version 18.6 (Ubuntu 18.6-0ubuntu0.26.04.1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: pg_trgm; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;


--
-- Name: EXTENSION pg_trgm; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pg_trgm IS 'text similarity measurement and index searching based on trigrams';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: battle_report_details; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.battle_report_details (
    platform smallint NOT NULL,
    battlelog_report_id bigint NOT NULL,
    report_json jsonb NOT NULL,
    extracted_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: battle_report_download_attempts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.battle_report_download_attempts (
    platform smallint NOT NULL,
    battlelog_report_id bigint NOT NULL,
    attempts integer DEFAULT 0 NOT NULL,
    last_attempt_at timestamp with time zone,
    last_result text
);


--
-- Name: battle_report_fetch_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.battle_report_fetch_log (
    id bigint NOT NULL,
    attempted_at timestamp with time zone DEFAULT now() NOT NULL,
    platform smallint NOT NULL,
    battlelog_report_id bigint NOT NULL,
    attempt_number integer NOT NULL,
    outcome text NOT NULL,
    http_status integer,
    curl_exit integer,
    elapsed_ms integer,
    response_bytes integer,
    content_type text,
    error_message text,
    response_body text,
    response_truncated boolean DEFAULT false NOT NULL
);


--
-- Name: battle_report_fetch_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.battle_report_fetch_log ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.battle_report_fetch_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: battle_report_raw; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.battle_report_raw (
    platform smallint NOT NULL,
    battlelog_report_id bigint NOT NULL,
    raw_response jsonb NOT NULL,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL,
    imported_at timestamp with time zone,
    CONSTRAINT battle_report_raw_platform_check CHECK ((platform = ANY (ARRAY[1, 32, 64])))
);


--
-- Name: battle_reports; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.battle_reports (
    id bigint NOT NULL,
    platform smallint NOT NULL,
    battlelog_report_id bigint NOT NULL,
    server_id bigint NOT NULL,
    report_timestamp timestamp with time zone NOT NULL,
    collected_at timestamp with time zone NOT NULL,
    CONSTRAINT battle_reports_platform_check CHECK ((platform = ANY (ARRAY[1, 32, 64])))
);


--
-- Name: battle_reports_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.battle_reports ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.battle_reports_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: bf4br_collector_error_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bf4br_collector_error_history (
    id bigint NOT NULL,
    occurred_at timestamp with time zone DEFAULT now() NOT NULL,
    node_name text NOT NULL,
    worker_id text NOT NULL,
    job_kind text NOT NULL,
    platform smallint NOT NULL,
    item_id bigint NOT NULL,
    day_utc date,
    error_message text NOT NULL,
    CONSTRAINT bf4br_collector_error_history_job_kind_check CHECK ((job_kind = ANY (ARRAY['historical_persona'::text, 'daily_persona'::text, 'report'::text, 'daily_report'::text]))),
    CONSTRAINT bf4br_collector_error_history_platform_check CHECK ((platform = ANY (ARRAY[1, 32, 64])))
);


--
-- Name: bf4br_collector_error_history_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.bf4br_collector_error_history ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.bf4br_collector_error_history_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: bf4br_coordinator_leases; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bf4br_coordinator_leases (
    name text NOT NULL,
    owner uuid NOT NULL,
    generation bigint DEFAULT 1 NOT NULL,
    lease_until timestamp with time zone NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT bf4br_coordinator_leases_generation_check CHECK ((generation > 0))
);


--
-- Name: bf4br_daily_persona_jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bf4br_daily_persona_jobs (
    day_utc date NOT NULL,
    platform smallint NOT NULL,
    persona_id bigint NOT NULL,
    state text DEFAULT 'ready'::text NOT NULL,
    cursor_epoch bigint,
    next_attempt_at timestamp with time zone DEFAULT now() NOT NULL,
    lease_owner text,
    lease_token uuid,
    lease_until timestamp with time zone,
    failures integer DEFAULT 0 NOT NULL,
    last_error text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT bf4br_daily_persona_jobs_persona_id_check CHECK ((persona_id > 0)),
    CONSTRAINT bf4br_daily_persona_jobs_platform_check CHECK ((platform = ANY (ARRAY[1, 32, 64]))),
    CONSTRAINT bf4br_daily_persona_jobs_state_check CHECK ((state = ANY (ARRAY['ready'::text, 'leased'::text, 'done'::text])))
);


--
-- Name: bf4br_daily_report_jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bf4br_daily_report_jobs (
    day_utc date NOT NULL,
    platform smallint NOT NULL,
    battlelog_report_id bigint NOT NULL,
    state text DEFAULT 'ready'::text NOT NULL,
    next_attempt_at timestamp with time zone DEFAULT now() NOT NULL,
    lease_owner text,
    lease_token uuid,
    lease_until timestamp with time zone,
    failures integer DEFAULT 0 NOT NULL,
    last_error text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT bf4br_daily_report_jobs_battlelog_report_id_check CHECK ((battlelog_report_id > 0)),
    CONSTRAINT bf4br_daily_report_jobs_platform_check CHECK ((platform = ANY (ARRAY[1, 32, 64]))),
    CONSTRAINT bf4br_daily_report_jobs_state_check CHECK ((state = ANY (ARRAY['ready'::text, 'leased'::text, 'done'::text])))
);


--
-- Name: bf4br_daily_windows; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bf4br_daily_windows (
    day_utc date NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    last_import_at timestamp with time zone,
    missing_persona_sessions bigint DEFAULT 0 NOT NULL,
    unsupported_platform_sessions bigint DEFAULT 0 NOT NULL,
    imported_personas bigint DEFAULT 0 NOT NULL
);


--
-- Name: bf4br_detail_players; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bf4br_detail_players (
    platform smallint NOT NULL,
    battlelog_report_id bigint NOT NULL,
    persona_id bigint NOT NULL,
    state text DEFAULT 'ready'::text NOT NULL,
    lease_owner text,
    lease_token uuid,
    lease_until timestamp with time zone,
    next_attempt_at timestamp with time zone DEFAULT now() NOT NULL,
    failures integer DEFAULT 0 NOT NULL,
    last_error text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT bf4br_detail_players_failures_check CHECK ((failures >= 0)),
    CONSTRAINT bf4br_detail_players_persona_id_check CHECK ((persona_id > 0)),
    CONSTRAINT bf4br_detail_players_state_check CHECK ((state = ANY (ARRAY['ready'::text, 'leased'::text, 'done'::text, 'retry'::text])))
);


--
-- Name: bf4br_detail_reports; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bf4br_detail_reports (
    platform smallint NOT NULL,
    battlelog_report_id bigint NOT NULL,
    report_timestamp timestamp with time zone NOT NULL,
    state text DEFAULT 'pending'::text NOT NULL,
    expected_players integer DEFAULT 0 NOT NULL,
    retry_after timestamp with time zone DEFAULT now() NOT NULL,
    activated_at timestamp with time zone,
    completed_at timestamp with time zone,
    last_error text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT bf4br_detail_reports_battlelog_report_id_check CHECK ((battlelog_report_id > 0)),
    CONSTRAINT bf4br_detail_reports_expected_players_check CHECK ((expected_players >= 0)),
    CONSTRAINT bf4br_detail_reports_platform_check CHECK ((platform = ANY (ARRAY[1, 32, 64]))),
    CONSTRAINT bf4br_detail_reports_state_check CHECK ((state = ANY (ARRAY['pending'::text, 'active'::text, 'complete'::text, 'deferred'::text])))
);


--
-- Name: bf4br_external_batch_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bf4br_external_batch_items (
    batch_id uuid NOT NULL,
    platform smallint NOT NULL,
    battlelog_report_id bigint NOT NULL,
    persona_id bigint NOT NULL,
    lease_token uuid NOT NULL
);


--
-- Name: bf4br_external_batches; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bf4br_external_batches (
    batch_id uuid NOT NULL,
    worker_id text NOT NULL,
    platform smallint NOT NULL,
    persona_id bigint NOT NULL,
    state text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    completed_at timestamp with time zone,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT bf4br_external_batches_check CHECK (((state = 'completed'::text) = (completed_at IS NOT NULL))),
    CONSTRAINT bf4br_external_batches_persona_id_check CHECK ((persona_id > 0)),
    CONSTRAINT bf4br_external_batches_platform_check CHECK ((platform = ANY (ARRAY[1, 32, 64]))),
    CONSTRAINT bf4br_external_batches_state_check CHECK ((state = ANY (ARRAY['active'::text, 'completed'::text, 'expired'::text])))
);


--
-- Name: bf4br_external_workers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bf4br_external_workers (
    worker_id text NOT NULL,
    key_sha256 character(64) NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    cooldown_until timestamp with time zone DEFAULT '-infinity'::timestamp with time zone NOT NULL,
    active_batch_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT bf4br_external_workers_key_sha256_check CHECK ((key_sha256 ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT bf4br_external_workers_worker_id_check CHECK (((length(worker_id) >= 1) AND (length(worker_id) <= 128)))
);


--
-- Name: bf4br_node_controls; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bf4br_node_controls (
    node_name text NOT NULL,
    persona_workers integer DEFAULT 3 NOT NULL,
    report_workers integer DEFAULT 1 NOT NULL,
    paused boolean DEFAULT false NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    request_interval_seconds integer DEFAULT 10 NOT NULL,
    http_429_cooldown_seconds integer DEFAULT 180 NOT NULL,
    CONSTRAINT bf4br_node_controls_http_429_cooldown_seconds_check CHECK (((http_429_cooldown_seconds >= 30) AND (http_429_cooldown_seconds <= 86400))),
    CONSTRAINT bf4br_node_controls_persona_workers_check CHECK (((persona_workers >= 0) AND (persona_workers <= 64))),
    CONSTRAINT bf4br_node_controls_report_workers_check CHECK (((report_workers >= 0) AND (report_workers <= 64))),
    CONSTRAINT bf4br_node_controls_request_interval_seconds_check CHECK (((request_interval_seconds >= 1) AND (request_interval_seconds <= 3600)))
);


--
-- Name: bf4br_node_heartbeats; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bf4br_node_heartbeats (
    node_name text NOT NULL,
    instance_id uuid NOT NULL,
    seen_at timestamp with time zone DEFAULT now() NOT NULL,
    supervisor_pid integer NOT NULL,
    running_persona integer DEFAULT 0 NOT NULL,
    running_report integer DEFAULT 0 NOT NULL,
    CONSTRAINT bf4br_node_heartbeats_running_persona_check CHECK ((running_persona >= 0)),
    CONSTRAINT bf4br_node_heartbeats_running_report_check CHECK ((running_report >= 0)),
    CONSTRAINT bf4br_node_heartbeats_supervisor_pid_check CHECK ((supervisor_pid > 0))
);


--
-- Name: bf4br_persona_jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bf4br_persona_jobs (
    platform smallint NOT NULL,
    persona_id bigint NOT NULL,
    state text DEFAULT 'ready'::text NOT NULL,
    cursor_epoch bigint,
    newest_epoch bigint,
    boundary_epoch bigint,
    last_completed_at timestamp with time zone,
    next_attempt_at timestamp with time zone DEFAULT now() NOT NULL,
    lease_owner text,
    lease_token uuid,
    lease_until timestamp with time zone,
    failures integer DEFAULT 0 NOT NULL,
    last_error text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT bf4br_persona_jobs_persona_id_check CHECK ((persona_id > 0)),
    CONSTRAINT bf4br_persona_jobs_platform_check CHECK ((platform = ANY (ARRAY[1, 32, 64]))),
    CONSTRAINT bf4br_persona_jobs_state_check CHECK ((state = ANY (ARRAY['ready'::text, 'leased'::text, 'done'::text])))
);


--
-- Name: bf4br_player_report_raw; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bf4br_player_report_raw (
    platform smallint NOT NULL,
    battlelog_report_id bigint NOT NULL,
    persona_id bigint NOT NULL,
    raw_response jsonb NOT NULL,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT bf4br_player_report_raw_persona_id_check CHECK ((persona_id > 0))
);


--
-- Name: bf4br_report_jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bf4br_report_jobs (
    platform smallint NOT NULL,
    battlelog_report_id bigint NOT NULL,
    state text DEFAULT 'ready'::text NOT NULL,
    next_attempt_at timestamp with time zone DEFAULT now() NOT NULL,
    lease_owner text,
    lease_token uuid,
    lease_until timestamp with time zone,
    failures integer DEFAULT 0 NOT NULL,
    last_error text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT bf4br_report_jobs_platform_check CHECK ((platform = ANY (ARRAY[1, 32, 64]))),
    CONSTRAINT bf4br_report_jobs_state_check CHECK ((state = ANY (ARRAY['ready'::text, 'leased'::text, 'done'::text])))
);


--
-- Name: bf4br_worker_assignments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bf4br_worker_assignments (
    node_name text NOT NULL,
    role text NOT NULL,
    platform smallint,
    generation bigint NOT NULL,
    assigned_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT bf4br_worker_assignments_check CHECK ((((role = 'rotating'::text) AND (platform IS NULL)) OR ((role <> 'rotating'::text) AND (platform IS NOT NULL)))),
    CONSTRAINT bf4br_worker_assignments_generation_check CHECK ((generation > 0)),
    CONSTRAINT bf4br_worker_assignments_platform_check CHECK ((platform = ANY (ARRAY[1, 32, 64]))),
    CONSTRAINT bf4br_worker_assignments_role_check CHECK ((role = ANY (ARRAY['daily'::text, 'historical'::text, 'rotating'::text])))
);


--
-- Name: history_checkpoints; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.history_checkpoints (
    platform smallint NOT NULL,
    persona_id bigint NOT NULL,
    next_cursor bigint NOT NULL,
    pages_saved integer DEFAULT 0 NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: history_discoveries; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.history_discoveries (
    platform smallint NOT NULL,
    battlelog_report_id bigint NOT NULL,
    report_timestamp timestamp with time zone NOT NULL,
    server_name text,
    map_code text,
    first_seen_at timestamp with time zone DEFAULT now() NOT NULL,
    last_seen_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT history_discoveries_platform_check CHECK ((platform = ANY (ARRAY[1, 32, 64])))
);


--
-- Name: history_discovery_failures; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.history_discovery_failures (
    platform smallint NOT NULL,
    persona_id bigint NOT NULL,
    failures integer DEFAULT 0 NOT NULL,
    last_failed_at timestamp with time zone DEFAULT now() NOT NULL,
    retry_after timestamp with time zone NOT NULL,
    last_reason text NOT NULL
);


--
-- Name: history_pages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.history_pages (
    platform smallint NOT NULL,
    persona_id bigint NOT NULL,
    cursor_used bigint NOT NULL,
    retrieved_at timestamp with time zone DEFAULT now() NOT NULL,
    raw_response jsonb NOT NULL,
    report_count integer NOT NULL,
    next_cursor bigint
);


--
-- Name: history_persona_refreshes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.history_persona_refreshes (
    platform smallint NOT NULL,
    persona_id bigint NOT NULL,
    last_success_at timestamp with time zone DEFAULT now() NOT NULL,
    newest_report_at timestamp with time zone,
    last_pages integer DEFAULT 0 NOT NULL
);


--
-- Name: history_report_sources; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.history_report_sources (
    platform smallint NOT NULL,
    persona_id bigint NOT NULL,
    battlelog_report_id bigint NOT NULL,
    discovered_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: player_name_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.player_name_history (
    id bigint NOT NULL,
    player_id bigint NOT NULL,
    player_name text NOT NULL,
    observed_at timestamp with time zone NOT NULL,
    source_report_id bigint
);


--
-- Name: player_name_history_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.player_name_history ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.player_name_history_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: players; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.players (
    id bigint NOT NULL,
    platform smallint NOT NULL,
    persona_id bigint NOT NULL,
    current_name text NOT NULL,
    current_name_observed_at timestamp with time zone NOT NULL,
    earliest_report_at timestamp with time zone NOT NULL,
    latest_report_at timestamp with time zone NOT NULL,
    CONSTRAINT players_platform_check CHECK ((platform = ANY (ARRAY[1, 32, 64])))
);


--
-- Name: players_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.players ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.players_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: report_players; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.report_players (
    report_id bigint NOT NULL,
    player_id bigint NOT NULL,
    player_name_observed text NOT NULL
);


--
-- Name: servers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.servers (
    id bigint NOT NULL,
    server_guid uuid NOT NULL,
    current_name text NOT NULL
);


--
-- Name: servers_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.servers ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.servers_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: battle_report_details battle_report_details_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.battle_report_details
    ADD CONSTRAINT battle_report_details_pkey PRIMARY KEY (platform, battlelog_report_id);


--
-- Name: battle_report_download_attempts battle_report_download_attempts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.battle_report_download_attempts
    ADD CONSTRAINT battle_report_download_attempts_pkey PRIMARY KEY (platform, battlelog_report_id);


--
-- Name: battle_report_fetch_log battle_report_fetch_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.battle_report_fetch_log
    ADD CONSTRAINT battle_report_fetch_log_pkey PRIMARY KEY (id);


--
-- Name: battle_report_raw battle_report_raw_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.battle_report_raw
    ADD CONSTRAINT battle_report_raw_pkey PRIMARY KEY (platform, battlelog_report_id);


--
-- Name: battle_reports battle_reports_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.battle_reports
    ADD CONSTRAINT battle_reports_pkey PRIMARY KEY (id);


--
-- Name: battle_reports battle_reports_platform_battlelog_report_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.battle_reports
    ADD CONSTRAINT battle_reports_platform_battlelog_report_id_key UNIQUE (platform, battlelog_report_id);


--
-- Name: bf4br_collector_error_history bf4br_collector_error_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bf4br_collector_error_history
    ADD CONSTRAINT bf4br_collector_error_history_pkey PRIMARY KEY (id);


--
-- Name: bf4br_coordinator_leases bf4br_coordinator_leases_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bf4br_coordinator_leases
    ADD CONSTRAINT bf4br_coordinator_leases_pkey PRIMARY KEY (name);


--
-- Name: bf4br_daily_persona_jobs bf4br_daily_persona_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bf4br_daily_persona_jobs
    ADD CONSTRAINT bf4br_daily_persona_jobs_pkey PRIMARY KEY (day_utc, platform, persona_id);


--
-- Name: bf4br_daily_report_jobs bf4br_daily_report_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bf4br_daily_report_jobs
    ADD CONSTRAINT bf4br_daily_report_jobs_pkey PRIMARY KEY (day_utc, platform, battlelog_report_id);


--
-- Name: bf4br_daily_windows bf4br_daily_windows_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bf4br_daily_windows
    ADD CONSTRAINT bf4br_daily_windows_pkey PRIMARY KEY (day_utc);


--
-- Name: bf4br_detail_players bf4br_detail_players_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bf4br_detail_players
    ADD CONSTRAINT bf4br_detail_players_pkey PRIMARY KEY (platform, battlelog_report_id, persona_id);


--
-- Name: bf4br_detail_reports bf4br_detail_reports_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bf4br_detail_reports
    ADD CONSTRAINT bf4br_detail_reports_pkey PRIMARY KEY (platform, battlelog_report_id);


--
-- Name: bf4br_external_batch_items bf4br_external_batch_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bf4br_external_batch_items
    ADD CONSTRAINT bf4br_external_batch_items_pkey PRIMARY KEY (batch_id, platform, battlelog_report_id, persona_id);


--
-- Name: bf4br_external_batches bf4br_external_batches_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bf4br_external_batches
    ADD CONSTRAINT bf4br_external_batches_pkey PRIMARY KEY (batch_id);


--
-- Name: bf4br_external_workers bf4br_external_workers_key_sha256_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bf4br_external_workers
    ADD CONSTRAINT bf4br_external_workers_key_sha256_key UNIQUE (key_sha256);


--
-- Name: bf4br_external_workers bf4br_external_workers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bf4br_external_workers
    ADD CONSTRAINT bf4br_external_workers_pkey PRIMARY KEY (worker_id);


--
-- Name: bf4br_node_controls bf4br_node_controls_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bf4br_node_controls
    ADD CONSTRAINT bf4br_node_controls_pkey PRIMARY KEY (node_name);


--
-- Name: bf4br_node_heartbeats bf4br_node_heartbeats_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bf4br_node_heartbeats
    ADD CONSTRAINT bf4br_node_heartbeats_pkey PRIMARY KEY (node_name);


--
-- Name: bf4br_persona_jobs bf4br_persona_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bf4br_persona_jobs
    ADD CONSTRAINT bf4br_persona_jobs_pkey PRIMARY KEY (platform, persona_id);


--
-- Name: bf4br_player_report_raw bf4br_player_report_raw_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bf4br_player_report_raw
    ADD CONSTRAINT bf4br_player_report_raw_pkey PRIMARY KEY (platform, battlelog_report_id, persona_id);


--
-- Name: bf4br_report_jobs bf4br_report_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bf4br_report_jobs
    ADD CONSTRAINT bf4br_report_jobs_pkey PRIMARY KEY (platform, battlelog_report_id);


--
-- Name: bf4br_worker_assignments bf4br_worker_assignments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bf4br_worker_assignments
    ADD CONSTRAINT bf4br_worker_assignments_pkey PRIMARY KEY (node_name);


--
-- Name: history_checkpoints history_checkpoints_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.history_checkpoints
    ADD CONSTRAINT history_checkpoints_pkey PRIMARY KEY (platform, persona_id);


--
-- Name: history_discoveries history_discoveries_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.history_discoveries
    ADD CONSTRAINT history_discoveries_pkey PRIMARY KEY (platform, battlelog_report_id);


--
-- Name: history_discovery_failures history_discovery_failures_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.history_discovery_failures
    ADD CONSTRAINT history_discovery_failures_pkey PRIMARY KEY (platform, persona_id);


--
-- Name: history_pages history_pages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.history_pages
    ADD CONSTRAINT history_pages_pkey PRIMARY KEY (platform, persona_id, cursor_used);


--
-- Name: history_persona_refreshes history_persona_refreshes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.history_persona_refreshes
    ADD CONSTRAINT history_persona_refreshes_pkey PRIMARY KEY (platform, persona_id);


--
-- Name: history_report_sources history_report_sources_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.history_report_sources
    ADD CONSTRAINT history_report_sources_pkey PRIMARY KEY (platform, persona_id, battlelog_report_id);


--
-- Name: player_name_history player_name_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.player_name_history
    ADD CONSTRAINT player_name_history_pkey PRIMARY KEY (id);


--
-- Name: players players_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.players
    ADD CONSTRAINT players_pkey PRIMARY KEY (id);


--
-- Name: players players_platform_persona_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.players
    ADD CONSTRAINT players_platform_persona_id_key UNIQUE (platform, persona_id);


--
-- Name: report_players report_players_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.report_players
    ADD CONSTRAINT report_players_pkey PRIMARY KEY (report_id, player_id);


--
-- Name: servers servers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.servers
    ADD CONSTRAINT servers_pkey PRIMARY KEY (id);


--
-- Name: servers servers_server_guid_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.servers
    ADD CONSTRAINT servers_server_guid_key UNIQUE (server_guid);


--
-- Name: battle_report_fetch_log_lookup; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX battle_report_fetch_log_lookup ON public.battle_report_fetch_log USING btree (platform, battlelog_report_id, attempted_at DESC);


--
-- Name: bf4br_collector_error_history_recent_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX bf4br_collector_error_history_recent_idx ON public.bf4br_collector_error_history USING btree (occurred_at DESC);


--
-- Name: bf4br_daily_persona_lease_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX bf4br_daily_persona_lease_idx ON public.bf4br_daily_persona_jobs USING btree (lease_until) WHERE (state = 'leased'::text);


--
-- Name: bf4br_daily_persona_ready_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX bf4br_daily_persona_ready_idx ON public.bf4br_daily_persona_jobs USING btree (day_utc, platform, next_attempt_at) WHERE (state = 'ready'::text);


--
-- Name: bf4br_daily_report_lease_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX bf4br_daily_report_lease_idx ON public.bf4br_daily_report_jobs USING btree (lease_until) WHERE (state = 'leased'::text);


--
-- Name: bf4br_daily_report_ready_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX bf4br_daily_report_ready_idx ON public.bf4br_daily_report_jobs USING btree (day_utc, platform, next_attempt_at) WHERE (state = 'ready'::text);


--
-- Name: bf4br_detail_active_order_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX bf4br_detail_active_order_idx ON public.bf4br_detail_reports USING btree (report_timestamp DESC, platform, battlelog_report_id) WHERE (state = 'active'::text);


--
-- Name: bf4br_detail_player_claim_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX bf4br_detail_player_claim_idx ON public.bf4br_detail_players USING btree (platform, battlelog_report_id, next_attempt_at) WHERE (state = ANY (ARRAY['ready'::text, 'retry'::text]));


--
-- Name: bf4br_detail_player_expired_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX bf4br_detail_player_expired_idx ON public.bf4br_detail_players USING btree (lease_until) WHERE (state = 'leased'::text);


--
-- Name: bf4br_detail_report_pick_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX bf4br_detail_report_pick_idx ON public.bf4br_detail_reports USING btree (report_timestamp DESC, platform, battlelog_report_id) WHERE (state = ANY (ARRAY['pending'::text, 'deferred'::text]));


--
-- Name: bf4br_external_batch_item_job_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX bf4br_external_batch_item_job_idx ON public.bf4br_external_batch_items USING btree (platform, battlelog_report_id, persona_id);


--
-- Name: bf4br_external_batch_worker_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX bf4br_external_batch_worker_idx ON public.bf4br_external_batches USING btree (worker_id, created_at DESC);


--
-- Name: bf4br_node_heartbeats_seen_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX bf4br_node_heartbeats_seen_idx ON public.bf4br_node_heartbeats USING btree (seen_at);


--
-- Name: bf4br_persona_lease_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX bf4br_persona_lease_idx ON public.bf4br_persona_jobs USING btree (lease_until) WHERE (state = 'leased'::text);


--
-- Name: bf4br_persona_ready_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX bf4br_persona_ready_idx ON public.bf4br_persona_jobs USING btree (next_attempt_at) WHERE (state = 'ready'::text);


--
-- Name: bf4br_report_lease_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX bf4br_report_lease_idx ON public.bf4br_report_jobs USING btree (lease_until) WHERE (state = 'leased'::text);


--
-- Name: bf4br_report_ready_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX bf4br_report_ready_idx ON public.bf4br_report_jobs USING btree (next_attempt_at) WHERE (state = 'ready'::text);


--
-- Name: idx_battle_report_raw_imported; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_battle_report_raw_imported ON public.battle_report_raw USING btree (imported_at);


--
-- Name: idx_bf4br_players_current_name_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bf4br_players_current_name_trgm ON public.players USING gin (lower(current_name) public.gin_trgm_ops);


--
-- Name: idx_bf4br_report_players_observed_name_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bf4br_report_players_observed_name_trgm ON public.report_players USING gin (lower(player_name_observed) public.gin_trgm_ops);


--
-- Name: idx_history_discoveries_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_history_discoveries_time ON public.history_discoveries USING btree (report_timestamp);


--
-- Name: idx_history_sources_persona; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_history_sources_persona ON public.history_report_sources USING btree (platform, persona_id);


--
-- Name: idx_name_history_player_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_name_history_player_time ON public.player_name_history USING btree (player_id, observed_at);


--
-- Name: idx_report_players_player; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_report_players_player ON public.report_players USING btree (player_id, report_id);


--
-- Name: idx_reports_server_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_reports_server_time ON public.battle_reports USING btree (server_id, report_timestamp);


--
-- Name: idx_reports_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_reports_timestamp ON public.battle_reports USING btree (report_timestamp);


--
-- Name: battle_reports battle_reports_server_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.battle_reports
    ADD CONSTRAINT battle_reports_server_id_fkey FOREIGN KEY (server_id) REFERENCES public.servers(id);


--
-- Name: bf4br_detail_players bf4br_detail_players_platform_battlelog_report_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bf4br_detail_players
    ADD CONSTRAINT bf4br_detail_players_platform_battlelog_report_id_fkey FOREIGN KEY (platform, battlelog_report_id) REFERENCES public.bf4br_detail_reports(platform, battlelog_report_id);


--
-- Name: bf4br_detail_players bf4br_detail_players_platform_persona_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bf4br_detail_players
    ADD CONSTRAINT bf4br_detail_players_platform_persona_id_fkey FOREIGN KEY (platform, persona_id) REFERENCES public.players(platform, persona_id);


--
-- Name: bf4br_detail_reports bf4br_detail_reports_platform_battlelog_report_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bf4br_detail_reports
    ADD CONSTRAINT bf4br_detail_reports_platform_battlelog_report_id_fkey FOREIGN KEY (platform, battlelog_report_id) REFERENCES public.battle_reports(platform, battlelog_report_id);


--
-- Name: bf4br_external_batch_items bf4br_external_batch_items_batch_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bf4br_external_batch_items
    ADD CONSTRAINT bf4br_external_batch_items_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES public.bf4br_external_batches(batch_id);


--
-- Name: bf4br_external_batch_items bf4br_external_batch_items_platform_battlelog_report_id_pe_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bf4br_external_batch_items
    ADD CONSTRAINT bf4br_external_batch_items_platform_battlelog_report_id_pe_fkey FOREIGN KEY (platform, battlelog_report_id, persona_id) REFERENCES public.bf4br_detail_players(platform, battlelog_report_id, persona_id);


--
-- Name: bf4br_external_batches bf4br_external_batches_worker_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bf4br_external_batches
    ADD CONSTRAINT bf4br_external_batches_worker_id_fkey FOREIGN KEY (worker_id) REFERENCES public.bf4br_external_workers(worker_id);


--
-- Name: bf4br_external_workers bf4br_external_worker_active_batch_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bf4br_external_workers
    ADD CONSTRAINT bf4br_external_worker_active_batch_fkey FOREIGN KEY (active_batch_id) REFERENCES public.bf4br_external_batches(batch_id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: bf4br_node_heartbeats bf4br_node_heartbeats_node_name_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bf4br_node_heartbeats
    ADD CONSTRAINT bf4br_node_heartbeats_node_name_fkey FOREIGN KEY (node_name) REFERENCES public.bf4br_node_controls(node_name);


--
-- Name: bf4br_player_report_raw bf4br_player_report_raw_platform_battlelog_report_id_perso_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bf4br_player_report_raw
    ADD CONSTRAINT bf4br_player_report_raw_platform_battlelog_report_id_perso_fkey FOREIGN KEY (platform, battlelog_report_id, persona_id) REFERENCES public.bf4br_detail_players(platform, battlelog_report_id, persona_id);


--
-- Name: bf4br_worker_assignments bf4br_worker_assignments_node_name_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bf4br_worker_assignments
    ADD CONSTRAINT bf4br_worker_assignments_node_name_fkey FOREIGN KEY (node_name) REFERENCES public.bf4br_node_controls(node_name);


--
-- Name: history_report_sources history_report_sources_platform_battlelog_report_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.history_report_sources
    ADD CONSTRAINT history_report_sources_platform_battlelog_report_id_fkey FOREIGN KEY (platform, battlelog_report_id) REFERENCES public.history_discoveries(platform, battlelog_report_id);


--
-- Name: player_name_history player_name_history_player_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.player_name_history
    ADD CONSTRAINT player_name_history_player_id_fkey FOREIGN KEY (player_id) REFERENCES public.players(id);


--
-- Name: player_name_history player_name_history_source_report_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.player_name_history
    ADD CONSTRAINT player_name_history_source_report_id_fkey FOREIGN KEY (source_report_id) REFERENCES public.battle_reports(id);


--
-- Name: report_players report_players_player_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.report_players
    ADD CONSTRAINT report_players_player_id_fkey FOREIGN KEY (player_id) REFERENCES public.players(id);


--
-- Name: report_players report_players_report_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.report_players
    ADD CONSTRAINT report_players_report_id_fkey FOREIGN KEY (report_id) REFERENCES public.battle_reports(id);


--
-- PostgreSQL database dump complete
--



```
