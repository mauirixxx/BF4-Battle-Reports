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
                target=0 if paused else persona_target
                # Don't count draining processes as available capacity.
                for pid,record in list(children.items()):
                    process,draining=record
                    if process.poll() is not None:
                        LOG.info("worker exited pid=%s status=%s",pid,process.returncode)
                        del children[pid]
                running=[pid for pid,(_,draining) in children.items() if not draining]
                while len(running)>target:
                    pid=running.pop()
                    process,_=children[pid]
                    process.terminate()
                    children[pid]=(process,True)
                    LOG.info("draining persona worker pid=%s",pid)
                while len(running)<target:
                    serial+=1
                    env={**os.environ,"BF4BR_WORKER_ID":f"{node}-persona-{serial}"}
                    p=subprocess.Popen([sys.executable,"-m","bf4br.persona_worker"],env=env)
                    children[p.pid]=(p,False)
                    running.append(p.pid)
                    LOG.info("started persona worker pid=%s",p.pid)
                if report_target:
                    LOG.warning("report_workers=%s configured but report worker is not implemented",report_target)
            except (psycopg.Error,OSError):
                LOG.exception("supervisor control loop failed; existing workers unchanged")
            time.sleep(3)
    LOG.info("supervisor stopping; draining children")
    for p,_ in children.values():
        if p.poll() is None:
            p.terminate()
    deadline=time.monotonic()+45
    for p,_ in children.values():
        if p.poll() is None:
            try:
                p.wait(timeout=max(0.1,deadline-time.monotonic()))
            except subprocess.TimeoutExpired:
                LOG.warning("worker %s did not drain; lease recovery will reclaim",p.pid)
                p.kill()
    LOG.info("supervisor stopped")

if __name__=="__main__":
    main()
