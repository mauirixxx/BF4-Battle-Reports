"""BF4BR persona collector: one leased persona per process, page-by-page."""
import json
import logging
import os
import signal
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import psycopg
from bf4br.queue import claim, renew, release
from bf4br.persona_store import persist_page
from bf4br.retry import retry_delay
from bf4br.node_cooldown import guarded_request
from bf4br.assignment_planner import next_platform

LOG=logging.getLogger("bf4br.persona")
STOP=False

def stop(_signal,_frame):
    global STOP
    STOP=True

def get_page(persona,platform,cursor,timeout=25):
    url=f"https://battlelog.battlefield.com/bf4/warsawbattlereportspopulatemore/{persona}/2048/{platform}/{cursor}/"
    request=Request(url,headers={"User-Agent":"BF4BR/0.1","Accept":"application/json"})
    try:
        with urlopen(request,timeout=timeout) as response:
            status=response.status
            body=response.read(8*1024*1024+1)
            hint=response.headers.get("Retry-After")
    except HTTPError as e:
        status=e.code
        hint=e.headers.get("Retry-After")
        body=b""
    if status!=200:
        return status,None,hint
    if len(body)>8*1024*1024:
        raise ValueError("history response too large")
    return status,json.loads(body),hint

def process_one(conn,job,token):
    platform,persona=job
    with conn.cursor() as cur:
        cur.execute("""SELECT cursor_epoch,boundary_epoch
            FROM bf4br_persona_jobs WHERE platform=%s AND persona_id=%s
            AND lease_token=%s""",(platform,persona,token))
        cursor,boundary=cur.fetchone()
    if cursor is None:
        cursor=int(time.time())+86400
        # Persist the initial cursor before the first network request.
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute("""UPDATE bf4br_persona_jobs SET cursor_epoch=%s,
                    boundary_epoch=COALESCE(boundary_epoch,
                      (SELECT extract(epoch FROM newest_report_at)::bigint
                       FROM history_persona_refreshes
                       WHERE platform=%s AND persona_id=%s))
                    WHERE platform=%s AND persona_id=%s AND lease_token=%s
                    AND state='leased' AND lease_until>now()""",
                    (cursor,platform,persona,platform,persona,token))
                if cur.rowcount!=1:
                    raise RuntimeError("lease lost during initialization")
    pages=0
    while not STOP:
        if not renew(conn,"persona",platform,persona,token,120):
            raise RuntimeError("lease lost before fetch")
        try:
            status,payload,hint=guarded_request(lambda: get_page(persona,platform,cursor), lambda r:r[0], lambda r:r[2])
        except (URLError,TimeoutError,OSError,ValueError) as e:
            LOG.warning("fetch failed platform=%s persona=%s error=%s",platform,persona,e)
            release(conn,"persona",platform,persona,token,delay_seconds=60,error=str(e))
            return
        if status!=200:
            delay=retry_delay(status,1,hint)
            if delay is None:
                delay=86400
            LOG.warning("HTTP %s persona=%s retry in %.1fs",status,persona,delay)
            release(conn,"persona",platform,persona,token,delay_seconds=delay,
                    error=f"HTTP {status}")
            return
        result=persist_page(conn,platform,persona,token,cursor,payload)
        pages+=1
        LOG.info("page saved platform=%s persona=%s page=%s reports=%s finished=%s",
                 platform,persona,pages,result["saved"],result["finished"])
        if result["finished"]:
            return
        cursor=result["next_cursor"]
        time.sleep(4)
    # Graceful drain: release current persona for another worker to resume.
    release(conn,"persona",platform,persona,token,delay_seconds=0)

def main():
    logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s")
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    dsn=os.environ["BF4BR_DSN"]
    worker=os.environ.get("BF4BR_WORKER_ID",f"persona-{os.getpid()}")
    rotating=os.environ.get('BF4BR_ROTATING') == '1'
    if rotating and os.environ.get('BF4BR_PLATFORM'):
        raise ValueError('rotating persona must not have a fixed platform')
    platform=next_platform(None) if rotating else (int(os.environ['BF4BR_PLATFORM']) if os.environ.get('BF4BR_PLATFORM') else None)
    with psycopg.connect(dsn,autocommit=True) as conn:
        while not STOP:
            job=claim(conn,"persona",worker,120,platform=platform)
            if not job:
                # An empty platform must not strand the flexible tenth slot.
                if rotating:
                    platform=next_platform(platform)
                time.sleep(3)
                continue
            row,token=job
            try:
                process_one(conn,row,token)
            except Exception:
                LOG.exception("persona job failed %s",row)
                try:
                    release(conn,"persona",*row,token,delay_seconds=120,
                            error="worker exception")
                except Exception:
                    LOG.exception("failed to release job")
                time.sleep(3)
            finally:
                # Advance only after the claimed persona finishes, releases,
                # or fails. Never switch platform while holding its lease.
                if rotating:
                    platform=next_platform(platform)

if __name__=="__main__":
    main()
