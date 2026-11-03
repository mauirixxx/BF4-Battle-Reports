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
            cur.execute(f'''UPDATE {table} SET state=%s,
                next_attempt_at=now()+(%s*interval '1 second'),
                lease_owner=NULL,lease_token=NULL,lease_until=NULL,
                failures=failures+(%s::integer),last_error=%s,updated_at=now()
                WHERE day_utc=%s AND platform=%s AND {key}=%s
                  AND state='leased' AND lease_token=%s AND lease_until>now()''',
                ('done' if done else 'ready',delay_seconds,1 if error else 0,
                 error,day,platform,item,token))
            return cur.rowcount==1
