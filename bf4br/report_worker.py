"""Distributed report worker; independent legacy retry/pacing per process."""
import logging
import os
import random
import signal
import time
import psycopg
from bf4br.queue import claim,renew,release
from bf4br.report_fetch import fetch,fetch_with_headers
from bf4br.node_cooldown import guarded_request
from bf4br.report_store import archive,recover
from bf4br.report_import import import_archived

STOP=False
LOG=logging.getLogger("bf4br.report")
def stop(*_):
    global STOP
    STOP=True

def process_one(conn,job,token,fetcher=fetch,sleeper=time.sleep):
    platform,rid=job
    if not renew(conn,"report",platform,rid,token,120):
        raise RuntimeError("lease lost")
    saved=recover(conn,platform,rid)
    if saved is None:
        for attempt in range(3):
            if STOP:
                release(conn,"report",platform,rid,token)
                return "drained"
            if not renew(conn,"report",platform,rid,token,120):
                raise RuntimeError("lease lost")
            try:
                if fetcher is fetch:
                    status,payload,error,hint=guarded_request(
                        lambda:fetch_with_headers(platform,rid),lambda r:r[0],lambda r:r[3])
                else:
                    status,payload,error=fetcher(platform,rid)
            except (OSError,TimeoutError) as exc:
                status,payload,error=0,None,str(exc)
            if status==200 and payload is not None:
                try:
                    archive(conn,platform,rid,token,payload)
                    break
                except ValueError as exc:
                    error=str(exc)
            if status==429:
                release(conn,'report',platform,rid,token,delay_seconds=1200,
                        error='HTTP 429')
                return 'rate_limited'
            if attempt<2:
                base=min(60,2*(2**attempt))
                sleeper(random.uniform(base*.5,base*1.5))
        else:
            release(conn,"report",platform,rid,token,delay_seconds=1200,
                    error=f"fetch failed: {status} {error}")
            return "retry"
    # Import failure leaves raw archive and schedules recovery without refetching.
    try:
        imported=import_archived(conn,platform,rid,token)
    except Exception as exc:
        LOG.exception("archive retained, import deferred: %s/%s",platform,rid)
        release(conn,"report",platform,rid,token,delay_seconds=1200,
                error=f"import failed: {str(exc)[:160]}")
        return "import_retry"
    if not release(conn,"report",platform,rid,token,done=True):
        raise RuntimeError("report lease lost after import")
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("""UPDATE bf4br_daily_report_jobs SET state='done',
                lease_owner=NULL,lease_token=NULL,lease_until=NULL,updated_at=now()
                WHERE platform=%s AND battlelog_report_id=%s AND state<>'done'""",(platform,rid))
    return "imported"

def main():
    logging.basicConfig(level=logging.INFO)
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    worker=os.environ.get("BF4BR_WORKER_ID",f"report-{os.getpid()}")
    with psycopg.connect(os.environ["BF4BR_DSN"],autocommit=True) as conn:
        while not STOP:
            claimed=claim(conn,"report",worker,120,platform=int(os.environ["BF4BR_PLATFORM"]) if os.environ.get("BF4BR_PLATFORM") else None)
            if claimed is None:
                time.sleep(3)
                continue
            job,token=claimed
            try:
                process_one(conn,job,token)
            except Exception as exc:
                LOG.exception("report worker failure %s",job)
                try:
                    release(conn,"report",*job,token,delay_seconds=1200,error=str(exc)[:160])
                except Exception:
                    LOG.exception("report lease release failed")
            if not STOP:
                time.sleep(10)

if __name__=="__main__":
    main()