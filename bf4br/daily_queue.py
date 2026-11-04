"""Token-fenced, day-scoped queues independent of historical persona state."""
from datetime import date
from uuid import uuid4

TABLES = {'persona': ('bf4br_daily_persona_jobs', 'persona_id'),
          'report': ('bf4br_daily_report_jobs', 'battlelog_report_id')}


def _validate(day, platform):
    if type(day) is not date or platform not in (1,32,64):
        raise ValueError('invalid UTC day or platform')


def claim(conn, kind, day, platform, worker, seconds=120):
    _validate(day, platform)
    if seconds < 1: raise ValueError('invalid lease')
    table,key=TABLES[kind]
    token=uuid4()
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(f'''WITH candidate AS (
                SELECT day_utc,platform,{key} FROM {table}
                WHERE day_utc=%s AND platform=%s
                  AND ((state='ready' AND next_attempt_at<=now())
                    OR (state='leased' AND lease_until<now()))
                ORDER BY next_attempt_at,{key}
                FOR UPDATE SKIP LOCKED LIMIT 1)
                UPDATE {table} j SET state='leased',lease_owner=%s,
                    lease_token=%s,lease_until=now()+(%s*interval '1 second'),
                    updated_at=now()
                FROM candidate c WHERE j.day_utc=c.day_utc
                  AND j.platform=c.platform AND j.{key}=c.{key}
                RETURNING j.{key}''', (day,platform,worker,token,seconds))
            row=cur.fetchone()
    return (row[0],token) if row else None


def renew(conn,kind,day,platform,item,token,seconds=120):
    _validate(day,platform)
    table,key=TABLES[kind]
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(f'''UPDATE {table} SET lease_until=now()+(%s*interval '1 second'),updated_at=now()
                WHERE day_utc=%s AND platform=%s AND {key}=%s
                  AND state='leased' AND lease_token=%s AND lease_until>now()''',
                (seconds,day,platform,item,token))
            return cur.rowcount==1


def release(conn,kind,day,platform,item,token,*,done=False,delay_seconds=0,error=None):
    _validate(day,platform)
    table,key=TABLES[kind]
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(f"""SELECT lease_owner FROM {table} WHERE day_utc=%s AND platform=%s AND {key}=%s
                AND state='leased' AND lease_token=%s AND lease_until>now() FOR UPDATE""",(day,platform,item,token))
            owner_row=cur.fetchone()
            cur.execute(f'''UPDATE {table} SET state=%s,
                next_attempt_at=now()+(%s*interval '1 second'),
                lease_owner=NULL,lease_token=NULL,lease_until=NULL,
                failures=failures+(%s::integer),last_error=%s,updated_at=now()
                WHERE day_utc=%s AND platform=%s AND {key}=%s
                  AND state='leased' AND lease_token=%s AND lease_until>now()
                RETURNING lease_owner''',
                ('done' if done else 'ready',delay_seconds,1 if error else 0,
                 error,day,platform,item,token))
            row=cur.fetchone()
            if row and error:
                worker=owner_row[0] if owner_row and owner_row[0] else 'unattributed'
                node=worker.rsplit('-',2)[0] if '-persona-' in worker or '-report-' in worker else worker
                cur.execute('''INSERT INTO bf4br_collector_error_history
                    (node_name,worker_id,job_kind,platform,item_id,day_utc,error_message)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)''',
                    (node,worker,'daily_persona' if kind=='persona' else 'daily_report',platform,item,day,str(error)))
            return row is not None
