"""Database-host-only bounded queue replenishment. Never fetches Battlelog pages."""
import argparse
import logging
import os
import signal
import time

import psycopg
from bf4br.queue import seed

LOG = logging.getLogger('bf4br.feeder')
STOP = False

def stop(*_):
    global STOP
    STOP = True

def queue_depths(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM bf4br_persona_jobs WHERE state='ready' AND next_attempt_at<=now()")
        personas = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM bf4br_report_jobs WHERE state='ready' AND next_attempt_at<=now()")
        reports = cur.fetchone()[0]
    return personas, reports

def platform_depths(conn):
    with conn.cursor() as cur:
        cur.execute("""SELECT platform,
          count(*) FILTER (WHERE state='ready' AND next_attempt_at<=now())
          FROM bf4br_persona_jobs GROUP BY platform""")
        personas=dict(cur.fetchall())
        cur.execute("""SELECT platform,
          count(*) FILTER (WHERE state='ready' AND next_attempt_at<=now())
          FROM bf4br_report_jobs GROUP BY platform""")
        reports=dict(cur.fetchall())
    return personas,reports


def seed_platform(conn, platform, persona_limit, report_limit):
    """Bounded, idempotent platform-specific seeding."""
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO bf4br_persona_jobs(platform,persona_id)
                SELECT p.platform,p.persona_id FROM players p
                WHERE p.platform=%s AND NOT EXISTS (
                  SELECT 1 FROM bf4br_persona_jobs j
                  WHERE j.platform=p.platform AND j.persona_id=p.persona_id)
                ORDER BY p.id LIMIT %s ON CONFLICT DO NOTHING""",
                (platform,persona_limit))
            personas=cur.rowcount
            cur.execute("""INSERT INTO bf4br_report_jobs(platform,battlelog_report_id)
                SELECT d.platform,d.battlelog_report_id FROM history_discoveries d
                WHERE d.platform=%s AND NOT EXISTS (
                  SELECT 1 FROM battle_report_raw r
                  WHERE r.platform=d.platform AND r.battlelog_report_id=d.battlelog_report_id
                    AND r.imported_at IS NOT NULL)
                  AND NOT EXISTS (
                  SELECT 1 FROM bf4br_report_jobs j
                  WHERE j.platform=d.platform AND j.battlelog_report_id=d.battlelog_report_id)
                ORDER BY d.report_timestamp DESC LIMIT %s ON CONFLICT DO NOTHING""",
                (platform,report_limit))
            reports=cur.rowcount
    return personas,reports


def replenish(conn, low=250, target=1000, batch=250):
    if not (0 <= low < target and 1 <= batch <= target):
        raise ValueError('invalid queue thresholds')
    before=platform_depths(conn)
    inserted={}
    for platform in (1,32,64):
        p=min(batch,max(0,target-before[0].get(platform,0))) if before[0].get(platform,0)<low else 0
        r=min(batch,max(0,target-before[1].get(platform,0))) if before[1].get(platform,0)<low else 0
        inserted[platform]=seed_platform(conn,platform,p,r) if p or r else (0,0)
    after=platform_depths(conn)
    LOG.info('platform queue depths=%s inserted=%s',after,inserted)
    return inserted,after

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--interval', type=int, default=60)
    args = parser.parse_args()
    if args.interval < 10:
        parser.error('interval must be >=10 seconds')
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    with psycopg.connect(os.environ.get('BF4BR_DSN','dbname=bf4_battle_reports user=postgres'), autocommit=True) as conn:
        while not STOP:
            try:
                replenish(conn)
            except psycopg.Error:
                LOG.exception('queue refill failed')
                conn.rollback()
                if args.once:
                    raise
            if args.once:
                return
            for _ in range(args.interval):
                if STOP:
                    break
                time.sleep(1)

if __name__ == '__main__':
    main()
