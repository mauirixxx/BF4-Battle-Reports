"""Coordinator-only detail advancement, fenced by scheduler leadership.

Hold the coordinator lease row lock throughout all queue transitions so a
successor cannot acquire leadership during an in-flight advancement pass.
"""
from bf4br.detail_queue import seed_reports,settle_report,activate


def advance_if_leader(conn, owner, seed_limit=250):
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("""SELECT generation FROM bf4br_coordinator_leases
                WHERE name='scheduler' AND owner=%s
                  AND lease_until>clock_timestamp()
                FOR UPDATE""",(owner,))
            row=cur.fetchone()
            if row is None:
                return None
            seeded=seed_reports(conn,limit=seed_limit)
            settled=settle_report(conn)
            activated=activate(conn)
            return {'generation':row[0],'seeded':seeded,
                    'settled':settled,'activated':activated}
