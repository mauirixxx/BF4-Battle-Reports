"""PostgreSQL queue claims with SKIP LOCKED and lease-token fencing."""
import uuid

QUEUES = {
    "persona": ("bf4br_persona_jobs", "persona_id"),
    "report": ("bf4br_report_jobs", "battlelog_report_id"),
}

def claim(conn, kind, worker, lease_seconds=120, platform=None):
    table, key = QUEUES[kind]
    if platform is not None and platform not in (1, 32, 64):
        raise ValueError("unsupported platform")
    token = uuid.uuid4()
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(f"""
                WITH candidate AS (
                    SELECT platform,{key} FROM {table}
                    WHERE ((state='ready' AND next_attempt_at <= now())
                       OR (state='leased' AND lease_until < now()))
                       AND (%s::smallint IS NULL OR platform=%s)
                    ORDER BY {"random()" if kind == "persona" else "(SELECT d.report_timestamp FROM history_discoveries d WHERE d.platform=" + table + ".platform AND d.battlelog_report_id=" + table + ".battlelog_report_id) DESC NULLS LAST,next_attempt_at,platform," + key}
                    FOR UPDATE SKIP LOCKED LIMIT 1
                )
                UPDATE {table} j
                SET state='leased',lease_owner=%s,lease_token=%s,
                    lease_until=now()+(%s * interval '1 second'),updated_at=now()
                FROM candidate c
                WHERE j.platform=c.platform AND j.{key}=c.{key}
                RETURNING j.platform,j.{key}
            """, (platform, platform, worker, token, lease_seconds))
            row = cur.fetchone()
    return (row, token) if row else None

def renew(conn, kind, platform, item, token, seconds=120):
    table, key = QUEUES[kind]
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(f"""UPDATE {table}
                SET lease_until=now()+(%s * interval '1 second'),updated_at=now()
                WHERE platform=%s AND {key}=%s AND lease_token=%s
                  AND state='leased' AND lease_until>now()""",
                (seconds,platform,item,token))
            return cur.rowcount == 1

def release(conn, kind, platform, item, token, delay_seconds=0, error=None, done=False):
    table, key = QUEUES[kind]
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(f"""UPDATE {table}
                SET state=%s,next_attempt_at=now()+(%s * interval '1 second'),
                    lease_owner=NULL,lease_token=NULL,lease_until=NULL,
                    failures=failures+(%s::integer),last_error=%s,updated_at=now()
                WHERE platform=%s AND {key}=%s AND state='leased'
                  AND lease_token=%s AND lease_until>now()""",
                ('done' if done else 'ready',delay_seconds,1 if error else 0,
                 error,platform,item,token))
            return cur.rowcount == 1

def seed(conn, limit=1000, persona_limit=None, report_limit=None):
    """Incrementally enqueue existing identities and report IDs."""
    if persona_limit is None: persona_limit = limit
    if report_limit is None: report_limit = limit
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO bf4br_persona_jobs(platform,persona_id)
                SELECT p.platform,p.persona_id FROM players p
                WHERE NOT EXISTS (
                    SELECT 1 FROM bf4br_persona_jobs j
                    WHERE j.platform=p.platform AND j.persona_id=p.persona_id)
                ORDER BY p.id LIMIT %s ON CONFLICT DO NOTHING""",(persona_limit,))
            personas = cur.rowcount
            cur.execute("""INSERT INTO bf4br_report_jobs(platform,battlelog_report_id)
                SELECT d.platform,d.battlelog_report_id FROM history_discoveries d
                WHERE NOT EXISTS (
                    SELECT 1 FROM battle_report_raw r
                    WHERE r.platform=d.platform AND r.battlelog_report_id=d.battlelog_report_id
                      AND r.imported_at IS NOT NULL)
                  AND NOT EXISTS (
                    SELECT 1 FROM bf4br_report_jobs j
                    WHERE j.platform=d.platform
                      AND j.battlelog_report_id=d.battlelog_report_id)
                ORDER BY d.report_timestamp DESC LIMIT %s ON CONFLICT DO NOTHING""",
                (report_limit,))
            reports = cur.rowcount
    return personas,reports
