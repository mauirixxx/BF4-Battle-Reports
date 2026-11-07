"""BF4BR central scheduler. Opt-in: --publish required to write assignments."""
import argparse
import logging
import os
import signal
import time
from uuid import uuid4

import psycopg
from bf4br.assignment_planner import plan, Assignment
from bf4br.fleet_coordination import healthy_nodes, plan_once
from bf4br.detail_queue import seed_reports,settle_report,activate

LOG = logging.getLogger('bf4br.scheduler')
STOP = False


def stop(*_):
    global STOP
    STOP = True


def main(argv=None):
    parser = argparse.ArgumentParser(description='BF4BR v1.0.6 central worker scheduler')
    parser.add_argument('--once', action='store_true', help='run a single scheduling pass')
    parser.add_argument('--detail-queue', action='store_true', help='opt in to coordinator-owned v2 detail queue advancement; requires --publish')
    parser.add_argument('--publish', action='store_true', help='opt in to assignment writes')
    parser.add_argument('--interval', type=int, default=10, help='loop interval in seconds (default: 10)')
    args = parser.parse_args(argv)
    if args.detail_queue and not args.publish:
        parser.error('--detail-queue requires --publish')
    if args.interval < 5:
        parser.error('interval must be at least 5 seconds')
    dsn = os.environ.get('BF4BR_DSN')
    if not dsn:
        parser.error('BF4BR_DSN must be configured')
    logging.basicConfig(level=logging.INFO)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    owner = uuid4()
    conn = None
    try:
        while not STOP:
            try:
                if conn is None or conn.closed:
                    conn = psycopg.connect(dsn, autocommit=True, connect_timeout=5)
                    LOG.info('scheduler database connection established')
                if args.publish:
                    assignments = plan_once(conn, owner)
                    if assignments is None:
                        LOG.info('standby: another coordinator owns the lease')
                    else:
                        LOG.info('published assignments: %s', assignments)
                        if args.detail_queue:
                            # Leadership must be held by this scheduler. A successor
                            # can safely resume because queue transitions are transactional.
                            seeded=seed_reports(conn,limit=250)
                            outcomes=settle_report(conn)
                            opened=activate(conn)
                            LOG.info('detail queue seeded=%s settled=%s activated=%s',seeded,outcomes,opened)
                else:
                    with conn.cursor() as cur:
                        cur.execute('SELECT node_name,role,platform FROM bf4br_worker_assignments ORDER BY node_name')
                        previous=[Assignment(*row) for row in cur.fetchall()]
                    LOG.info('DRY RUN assignments: %s', plan(healthy_nodes(conn),previous=previous))
            except (psycopg.OperationalError, psycopg.InterfaceError):
                LOG.exception('scheduler connection lost; reconnecting on next pass')
                if conn is not None:
                    try:
                        conn.close()
                    except psycopg.Error:
                        pass
                conn = None
                if args.once:
                    raise
            except psycopg.Error:
                LOG.exception('scheduler database failure; no assignment published')
                if args.once:
                    raise
            if args.once:
                return
            time.sleep(args.interval)
    finally:
        if conn is not None:
            conn.close()


if __name__ == '__main__':
    main()
