# BF4BR live operational schema reference

Verified read-only against `reports` PostgreSQL 18.6 (`bf4_battle_reports`) on 2026-11-05 using `pg_dump --schema-only --no-owner --no-privileges` for `public.bf4br_*` and `public.battle_report_fetch_log`.

**This is a snapshot of existing production objects, not a migration.** It covers BF4BR queue/coordinator/monitoring tables only, not the complete archive schema. `migrations/0001_worker_queues.sql` is the original baseline and does **not** reproduce every object below; subsequent production changes need a separately reconciled migration history before any schema rollout. Do not execute this reference against production.

`battle_report_fetch_log` has no `node_name`; node attribution is possible only by correlating a fetch attempt with a single unambiguous `bf4br_collector_error_history` node on the same platform and report ID in a short time window. Never infer node from a released lease.

```sql
--
-- PostgreSQL database dump
--






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
-- Name: battle_report_fetch_log battle_report_fetch_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.battle_report_fetch_log
    ADD CONSTRAINT battle_report_fetch_log_pkey PRIMARY KEY (id);


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
-- Name: bf4br_node_heartbeats bf4br_node_heartbeats_node_name_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bf4br_node_heartbeats
    ADD CONSTRAINT bf4br_node_heartbeats_node_name_fkey FOREIGN KEY (node_name) REFERENCES public.bf4br_node_controls(node_name);


--
-- Name: bf4br_worker_assignments bf4br_worker_assignments_node_name_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bf4br_worker_assignments
    ADD CONSTRAINT bf4br_worker_assignments_node_name_fkey FOREIGN KEY (node_name) REFERENCES public.bf4br_node_controls(node_name);
```
