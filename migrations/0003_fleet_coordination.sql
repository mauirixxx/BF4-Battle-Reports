-- BF4BR v1.0.6: additive, opt-in fleet coordination schema.
-- Do not activate centrally assigned roles until every supervisor supports them.
BEGIN;
CREATE TABLE IF NOT EXISTS bf4br_node_heartbeats (
 node_name text PRIMARY KEY REFERENCES bf4br_node_controls(node_name),
 instance_id uuid NOT NULL,
 seen_at timestamptz NOT NULL DEFAULT now(),
 supervisor_pid integer NOT NULL CHECK (supervisor_pid > 0),
 running_persona integer NOT NULL DEFAULT 0 CHECK (running_persona >= 0),
 running_report integer NOT NULL DEFAULT 0 CHECK (running_report >= 0)
);
CREATE TABLE IF NOT EXISTS bf4br_coordinator_leases (
 name text PRIMARY KEY,
 owner uuid NOT NULL,
 generation bigint NOT NULL DEFAULT 1 CHECK (generation > 0),
 lease_until timestamptz NOT NULL,
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS bf4br_worker_assignments (
 node_name text PRIMARY KEY REFERENCES bf4br_node_controls(node_name),
 role text NOT NULL CHECK (role IN ('daily','historical','rotating')),
 platform smallint CHECK (platform IN (1,32,64)),
 generation bigint NOT NULL CHECK (generation > 0),
 assigned_at timestamptz NOT NULL DEFAULT now(),
 CHECK ((role='rotating' AND platform IS NULL) OR (role<>'rotating' AND platform IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS bf4br_node_heartbeats_seen_idx ON bf4br_node_heartbeats(seen_at);
COMMIT;
