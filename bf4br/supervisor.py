"""Node supervisor: dynamically resize persona workers without rebuilding image."""
import logging
import os
import signal
import subprocess
import sys
import time
import psycopg

LOG=logging.getLogger("bf4br.supervisor")
STOP=False
def stop(_signal,_frame):
    global STOP
    STOP=True

def main():
    logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s")
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    dsn=os.environ["BF4BR_DSN"]
    node=os.environ.get("BF4BR_NODE",os.uname().nodename)
    children={}
    serial=0
    slots=(1,32,64)
    with psycopg.connect(dsn,autocommit=True) as conn:
        while not STOP:
            try:
                with conn.transaction():
                    with conn.cursor() as cur:
                        cur.execute("""INSERT INTO bf4br_node_controls(node_name)
                            VALUES (%s) ON CONFLICT DO NOTHING""",(node,))
                        cur.execute("""SELECT persona_workers,report_workers,paused
                            FROM bf4br_node_controls WHERE node_name=%s""",(node,))
                        persona_target,report_target,paused=cur.fetchone()
                for pid,(process,kind,draining) in list(children.items()):
                    if process.poll() is not None:
                        LOG.info("worker exited pid=%s status=%s",pid,process.returncode)
                        del children[pid]
                # Stable fleet-wide slot assignment from coordinator node registry.
                # Each node with three persona workers contributes one per platform.
                with conn.cursor() as cur:
                    cur.execute("""SELECT node_name FROM bf4br_node_controls
                        WHERE NOT paused AND (persona_workers>0 OR report_workers>0)
                        ORDER BY node_name""")
                    nodes=[r[0] for r in cur.fetchall()]
                rank=nodes.index(node) if node in nodes else 0
                daily_platform = int(os.environ["BF4BR_DAILY_PLATFORM"]) if os.environ.get("BF4BR_DAILY_PLATFORM") else None
                if daily_platform not in (None,1,32,64):
                    raise ValueError("unsupported daily platform")
                for kind,desired in (("persona",persona_target),("report",report_target)):
                    target=0 if paused else desired
                    running=[pid for pid,(_,k,draining) in children.items()
                             if k==kind and not draining]
                    while len(running)>target:
                        pid=running.pop()
                        process,_,_=children[pid]
                        process.terminate()
                        children[pid]=(process,kind,True)
                        LOG.info("draining %s worker pid=%s",kind,pid)
                    while len(running)<target:
                        serial+=1
                        # First three report slots reserve PC/PS/Xbox; fourth is flexible.
                        slot=len(running)
                        preferred=(slots[slot%3] if kind=="persona"
                                   else (slots[rank%3] if rank<3 else None))
                        env={**os.environ,"BF4BR_WORKER_ID":f"{node}-{kind}-{serial}"}
                        if preferred is not None:
                            env["BF4BR_PLATFORM"]=str(preferred)
                        else:
                            env.pop("BF4BR_PLATFORM",None)
                        module=f"bf4br.{kind}_worker"
                        if kind=="persona" and daily_platform is not None and target==1:
                            module="bf4br.daily_persona_worker"
                            env["BF4BR_PLATFORM"]=str(daily_platform)
                        process=subprocess.Popen([sys.executable,"-m",module],env=env)
                        children[process.pid]=(process,kind,False)
                        running.append(process.pid)
                        LOG.info("started %s worker pid=%s",kind,process.pid)
            except (psycopg.Error,OSError):
                LOG.exception("supervisor control loop failed; existing workers unchanged")
            time.sleep(3)
    LOG.info("supervisor stopping; draining children")
    for p,_,_ in children.values():
        if p.poll() is None:
            p.terminate()
    deadline=time.monotonic()+45
    for p,_,_ in children.values():
        if p.poll() is None:
            try:
                p.wait(timeout=max(0.1,deadline-time.monotonic()))
            except subprocess.TimeoutExpired:
                LOG.warning("worker %s did not drain; lease recovery will reclaim",p.pid)
                p.kill()
    LOG.info("supervisor stopped")

if __name__=="__main__":
    main()