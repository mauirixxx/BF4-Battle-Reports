"""Daily persona discovery worker for BF4BR."""
import logging
import os
import signal
import time
from datetime import datetime, date, timezone
import psycopg
from bf4br.daily_queue import claim, renew, release
from bf4br.persona_worker import get_page
from bf4br.retry import retry_delay
from bf4br.node_cooldown import guarded_request
from bf4br.persona_worker import process_one as process_historical
from bf4br.queue import claim as claim_historical, release as release_historical

LOG = logging.getLogger(__name__)
STOP = False

def stop(*_):
    global STOP
    STOP = True

def save_page(conn, day, platform, persona, token, cursor, payload):
    data = payload.get('data') if isinstance(payload, dict) else None
    reports = data.get('gameReports') if isinstance(data, dict) else None
    if not isinstance(reports, list):
        raise ValueError('missing gameReports')
    rows = []
    for item in reports:
        rid, stamp = int(item['gameReportId']), int(item['createdAt'])
        if rid <= 0 or stamp <= 0 or stamp > cursor:
            raise ValueError('invalid report row')
        rows.append((rid, stamp, item.get('name'), item.get('map')))
    boundary = int(datetime.combine(day, datetime.min.time(), timezone.utc).timestamp())
    oldest = min((r[1] for r in rows), default=None)
    finished = oldest is None or oldest <= boundary
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute('''SELECT cursor_epoch FROM bf4br_daily_persona_jobs
                WHERE day_utc=%s AND platform=%s AND persona_id=%s AND state='leased'
                AND lease_token=%s AND lease_until>now() FOR UPDATE''',
                (day, platform, persona, token))
            saved = cur.fetchone()
            if not saved or (saved[0] is not None and saved[0] != cursor):
                raise RuntimeError('daily lease/cursor lost')
            for rid, stamp, name, mapcode in rows:
                if stamp < boundary:
                    continue
                report_day = datetime.fromtimestamp(stamp,timezone.utc).date()
                cur.execute('''INSERT INTO history_discoveries
                    (platform,battlelog_report_id,report_timestamp,server_name,map_code)
                    VALUES (%s,%s,%s,%s,%s)
                    ON CONFLICT(platform,battlelog_report_id) DO UPDATE SET last_seen_at=now()''',
                    (platform,rid,datetime.fromtimestamp(stamp,timezone.utc),name,mapcode))
                cur.execute('''INSERT INTO history_report_sources(platform,persona_id,battlelog_report_id)
                    VALUES (%s,%s,%s) ON CONFLICT DO NOTHING''',(platform,persona,rid))
                cur.execute('''INSERT INTO bf4br_daily_report_jobs(day_utc,platform,battlelog_report_id)
                    VALUES (%s,%s,%s) ON CONFLICT DO NOTHING''',(report_day,platform,rid))
                cur.execute('''INSERT INTO bf4br_report_jobs(platform,battlelog_report_id)
                    VALUES (%s,%s) ON CONFLICT DO NOTHING''',(platform,rid))
            cur.execute('''UPDATE bf4br_daily_persona_jobs SET cursor_epoch=%s,
                state=CASE WHEN %s THEN 'done' ELSE 'leased' END,
                lease_owner=CASE WHEN %s THEN NULL ELSE lease_owner END,
                lease_token=CASE WHEN %s THEN NULL ELSE lease_token END,
                lease_until=CASE WHEN %s THEN NULL ELSE lease_until END,
                updated_at=now() WHERE day_utc=%s AND platform=%s AND persona_id=%s
                AND state='leased' AND lease_token=%s AND lease_until>now()''',
                (None if finished else oldest-1,finished,finished,finished,finished,
                 day,platform,persona,token))
            if cur.rowcount != 1:
                raise RuntimeError('daily lease expired')
    return finished, None if finished else oldest-1

def process_one(conn, day, platform, persona, token):
    with conn.cursor() as cur:
        cur.execute('''SELECT cursor_epoch FROM bf4br_daily_persona_jobs
            WHERE day_utc=%s AND platform=%s AND persona_id=%s AND lease_token=%s''',
            (day,platform,persona,token))
        cursor = cur.fetchone()[0]
    if cursor is None:
        cursor = int(time.time()) + 86400
    while not STOP:
        if not renew(conn,'persona',day,platform,persona,token):
            raise RuntimeError('daily lease lost')
        try:
            status,payload,hint = guarded_request(lambda: get_page(persona,platform,cursor), lambda r:r[0], lambda r:r[2])
        except (OSError,ValueError,TimeoutError) as exc:
            release(conn,'persona',day,platform,persona,token,delay_seconds=120,error=str(exc)[:160])
            return
        if status != 200:
            release(conn,'persona',day,platform,persona,token,
                    delay_seconds=retry_delay(status,1,hint) or 86400,error=f'HTTP {status}')
            return
        finished,cursor = save_page(conn,day,platform,persona,token,cursor,payload)
        LOG.info('daily page day=%s platform=%s persona=%s finished=%s',day,platform,persona,finished)
        if finished:
            return
        time.sleep(4)
    release(conn,'persona',day,platform,persona,token)

def main():
    logging.basicConfig(level=logging.INFO)
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    platform = int(os.environ['BF4BR_PLATFORM'])
    worker = os.environ.get('BF4BR_WORKER_ID',f'daily-{os.getpid()}')
    with psycopg.connect(os.environ['BF4BR_DSN'],autocommit=True) as conn:
        while not STOP:
            with conn.cursor() as cur:
                cur.execute('''SELECT day_utc FROM bf4br_daily_persona_jobs
                    WHERE platform=%s AND day_utc < (now() AT TIME ZONE 'UTC')::date
                    AND ((state='ready' AND next_attempt_at<=now()) OR
                         (state='leased' AND lease_until<now()))
                    ORDER BY day_utc DESC LIMIT 1''',(platform,))
                row=cur.fetchone()
            if row is None:
                historical=claim_historical(conn,'persona',worker,120,platform=platform)
                if historical:
                    job,token=historical
                    try:
                        process_historical(conn,job,token)
                    except Exception:
                        LOG.exception('historical fallback failed platform=%s persona=%s',*job)
                        release_historical(conn,'persona',*job,token,delay_seconds=120,error='fallback worker exception')
                else:
                    time.sleep(3)
                continue
            day=row[0]
            job=claim(conn,'persona',day,platform,worker)
            if not job:
                continue
            persona,token=job
            try:
                process_one(conn,day,platform,persona,token)
            except Exception as exc:
                LOG.exception('daily persona failed day=%s platform=%s persona=%s',day,platform,persona)
                try:
                    release(conn,'persona',day,platform,persona,token,delay_seconds=120,error=str(exc)[:160])
                except Exception:
                    LOG.exception('failed to release daily lease')

if __name__=='__main__':
    main()