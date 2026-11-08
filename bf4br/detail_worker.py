"""BF4BR v2 player-detail worker; opt-in only after coordinated fleet rollout."""
import logging
import os
import signal
import time

import psycopg
from bf4br.detail_fetch import fetch_detail
from bf4br.detail_burst_worker import process_batch
from bf4br.detail_queue import (claim_player,renew_player,
                                save_player,retry_player)
from bf4br.node_cooldown import guarded_request,wait_until_clear
from bf4br.retry import retry_delay

LOG=logging.getLogger(__name__)
STOP=False


def stop(*_):
    global STOP
    STOP=True


def process_one(conn,job,token,fetcher=fetch_detail):
    if not renew_player(conn,job,token):
        raise RuntimeError('detail lease lost before request')
    try:
        status,payload,error,hint=guarded_request(
            lambda: fetcher(*job),lambda result:result[0],
            lambda result:result[3],
            on_wait=lambda: (_ for _ in ()).throw(InterruptedError("detail shutdown")) if STOP else renew_player(conn,job,token) or
            (_ for _ in ()).throw(RuntimeError('detail lease lost during cooldown')))
    except InterruptedError:
        retry_player(conn,job,token,"shutdown during cooldown",0)
        return "drained"
    except (OSError,TimeoutError,ValueError) as exc:
        retry_player(conn,job,token,str(exc),1200)
        return 'retry'
    if status!=200 or payload is None:
        delay=retry_delay(status,1,hint)
        if delay is None:
            delay=86400
        retry_player(conn,job,token,f'HTTP {status}: {error}',delay)
        return 'retry'
    try:
        save_player(conn,job,token,payload)
    except ValueError as exc:
        retry_player(conn,job,token,f'invalid detail: {exc}',86400)
        return 'invalid'
    return 'done'


def main():
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    worker=os.environ.get('BF4BR_WORKER_ID',f'detail-{os.getpid()}')
    with psycopg.connect(os.environ['BF4BR_DSN'],autocommit=True) as conn:
        burst_enabled=os.environ.get("BF4BR_DETAIL_BURST_ENABLED") == "1"
        while not STOP:
            if burst_enabled:
                count=0
                try:
                    count, limited=process_batch(conn,worker,stopped=lambda: STOP)
                    LOG.info("detail burst dispatched=%s rate_limited=%s",count,limited)
                except Exception:
                    LOG.exception("detail burst failed; existing leases remain fenced and recoverable")
                    time.sleep(2)
                if not STOP and count == 0:
                    time.sleep(2)
                continue
            wait_until_clear()
            claimed=claim_player(conn,worker)
            if claimed is None:
                time.sleep(2)
                continue
            job,token=claimed
            try:
                outcome=process_one(conn,job,token)
                LOG.info('detail job %s result=%s',job,outcome)
            except Exception as exc:
                LOG.exception('detail worker failure %s',job)
                try:
                    retry_player(conn,job,token,str(exc),1200)
                except psycopg.Error:
                    LOG.exception('unable to release failed detail lease')
            # No extra network request here: guarded_request enforces node pacing.
    LOG.info('detail worker drained')


if __name__=='__main__':
    main()
