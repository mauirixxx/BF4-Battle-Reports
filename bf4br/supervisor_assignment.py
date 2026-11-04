"""Assignment reading and process identity for opt-in coordinated supervisors."""
from bf4br.assignment_runtime import desired_persona_specs


def read_assignment(conn, node):
    with conn.cursor() as cur:
        cur.execute('''SELECT a.role,a.platform FROM bf4br_worker_assignments a
            JOIN bf4br_coordinator_leases l ON l.name='scheduler'
            WHERE a.node_name=%s AND a.generation=l.generation
              AND l.lease_until>clock_timestamp()''', (node,))
        return cur.fetchone()


def desired_specs(assignment, persona_target, paused):
    return desired_persona_specs(None if paused else assignment, persona_target)


def worker_module(spec):
    if spec.role == 'daily':
        return 'bf4br.daily_persona_worker'
    return 'bf4br.persona_worker'
