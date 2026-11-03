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

def replenish(conn, low=250, target=1000, batch=250):
    if not (0 <= low < target and 1 <= batch <= target):
        raise ValueError('invalid queue thresholds')
    before = queue_depths(conn)
    # seed() is idempotent; cap the insert batch and only refill when needed.
    persona_limit = min(batch, max(0, target-before[0])) if before[0] < low else 0
    report_limit = min(batch, max(0, target-before[1])) if before[1] < low else 0
    if persona_limit or report_limit:
        inserted = seed(conn, persona_limit=persona_limit, report_limit=report_limit)
    else:
        inserted = (0, 0)
    after = queue_depths(conn)
    LOG.info('queue personas=%s reports=%s inserted_personas=%s inserted_reports=%s',
             after[0], after[1], inserted[0], inserted[1])
    return inserted, after

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
