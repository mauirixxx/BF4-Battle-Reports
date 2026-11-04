"""Opt-in BF4BR coordinator primitives; no production activation here."""
from datetime import timedelta
from uuid import uuid4

from bf4br.assignment_planner import plan, Assignment

HEARTBEAT_SECONDS = 10
SUSPECT_SECONDS = 30
OFFLINE_SECONDS = 60
LEADER_SECONDS = 30


def heartbeat(conn, node, instance_id, pid, persona_count, report_count):
    """Heartbeat a supervisor instance. Requires its node-control registration."""
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO bf4br_node_heartbeats
                (node_name,instance_id,supervisor_pid,running_persona,running_report,seen_at)
                VALUES (%s,%s,%s,%s,%s,clock_timestamp())
                ON CONFLICT (node_name) DO UPDATE SET
                instance_id=EXCLUDED.instance_id,supervisor_pid=EXCLUDED.supervisor_pid,
                running_persona=EXCLUDED.running_persona,running_report=EXCLUDED.running_report,
                seen_at=EXCLUDED.seen_at""",
                (node,instance_id,pid,persona_count,report_count))


def healthy_nodes(conn):
    """Only nodes with recent heartbeats and unpaused controls qualify."""
    with conn.cursor() as cur:
        cur.execute("""SELECT c.node_name FROM bf4br_node_controls c
            JOIN bf4br_node_heartbeats h USING (node_name)
            WHERE NOT c.paused AND c.persona_workers > 0
              AND h.seen_at >= clock_timestamp() - interval '60 seconds'
            ORDER BY c.node_name""")
        return [row[0] for row in cur.fetchall()]


def acquire_leadership(conn, owner):
    """Atomic lease acquisition with a monotonic fencing generation.

    A running leader renews without changing generation. An expired leader
    can be replaced; its generation is incremented. No advisory-lock lifetime
    assumptions or application-clock comparisons are required.
    """
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO bf4br_coordinator_leases
                (name,owner,generation,lease_until)
                VALUES ('scheduler',%s,1,clock_timestamp()+interval '30 seconds')
                ON CONFLICT (name) DO UPDATE SET
                    owner=EXCLUDED.owner,
                    generation=CASE WHEN bf4br_coordinator_leases.owner=EXCLUDED.owner
                        THEN bf4br_coordinator_leases.generation
                        ELSE bf4br_coordinator_leases.generation+1 END,
                    lease_until=clock_timestamp()+interval '30 seconds',
                    updated_at=clock_timestamp()
                WHERE bf4br_coordinator_leases.owner=EXCLUDED.owner
                   OR bf4br_coordinator_leases.lease_until < clock_timestamp()
                RETURNING generation""", (owner,))
            row=cur.fetchone()
            return row[0] if row else None


def publish(conn, owner, generation, assignments):
    """Publish only while holding the exact unexpired leader generation.

    A database row lock fences a competing leader until this transaction ends.
    Missing nodes lose assignments; node supervisors must drain gracefully.
    """
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("""SELECT 1 FROM bf4br_coordinator_leases
                WHERE name='scheduler' AND owner=%s AND generation=%s
                  AND lease_until>clock_timestamp() FOR UPDATE""", (owner,generation))
            if cur.fetchone() is None:
                return False
            nodes=[a.node for a in assignments]
            if nodes:
                cur.execute("DELETE FROM bf4br_worker_assignments WHERE NOT (node_name=ANY(%s))", (nodes,))
            else:
                cur.execute("DELETE FROM bf4br_worker_assignments")
            for a in assignments:
                cur.execute("""INSERT INTO bf4br_worker_assignments
                    (node_name,role,platform,generation) VALUES (%s,%s,%s,%s)
                    ON CONFLICT (node_name) DO UPDATE SET
                    role=EXCLUDED.role,platform=EXCLUDED.platform,
                    generation=EXCLUDED.generation,
                    assigned_at=CASE WHEN
                        (bf4br_worker_assignments.role,bf4br_worker_assignments.platform)
                        IS DISTINCT FROM (EXCLUDED.role,EXCLUDED.platform)
                        THEN clock_timestamp() ELSE bf4br_worker_assignments.assigned_at END""",
                    (a.node,a.role,a.platform,generation))
            return True


def plan_once(conn, owner):
    generation=acquire_leadership(conn,owner)
    if generation is None:
        return None
    with conn.cursor() as cur:
        cur.execute("SELECT node_name,role,platform FROM bf4br_worker_assignments ORDER BY node_name")
        previous=[Assignment(*row) for row in cur.fetchall()]
    assignments=plan(healthy_nodes(conn),previous=previous)
    return assignments if publish(conn,owner,generation,assignments) else None
