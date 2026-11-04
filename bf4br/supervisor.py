"""Node supervisor: dynamically resize persona workers without rebuilding image."""
import logging
import json
from pathlib import Path
import os
import signal
import subprocess
import sys
import time
from uuid import uuid4
import psycopg
from bf4br.fleet_coordination import heartbeat
from bf4br.supervisor_assignment import read_assignment, desired_specs, worker_module

LOG=logging.getLogger("bf4br.supervisor")
POLICY = Path(os.environ.get("BF4BR_REQUEST_POLICY_FILE", "/tmp/bf4br-request-policy.json"))

def publish_request_policy(interval, cooldown):
    """Atomic publication; never delete the last good policy on DB failure."""
    if not (type(interval) is int and 1 <= interval <= 3600 and type(cooldown) is int and 30 <= cooldown <= 86400):
        raise ValueError("invalid request policy")
    POLICY.parent.mkdir(parents=True, exist_ok=True)
    temp = POLICY.with_name(POLICY.name + ".tmp." + str(os.getpid()))
    try:
        temp.write_text(json.dumps({"request_interval_seconds": interval, "http_429_cooldown_seconds": cooldown}))
        os.replace(temp, POLICY)
    finally:
        temp.unlink(missing_ok=True)

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
    coordinated=os.environ.get('BF4BR_COORDINATED') == '1'
    # A coordinated node must advertise health or it will never be assigned.
    heartbeat_enabled=coordinated or os.environ.get('BF4BR_ENABLE_HEARTBEATS') == '1'
    active_specs={}
    instance_id=uuid4()
    last_heartbeat=0.0
    slots=(1,32,64)
    conn=None
    try:
        while not STOP:
            try:
                if conn is None or conn.closed:
                    conn=psycopg.connect(dsn,autocommit=True,connect_timeout=5)
                    last_heartbeat=0.0
                    LOG.info('supervisor database connection established')
                with conn.transaction():
                    with conn.cursor() as cur:
                        cur.execute("""INSERT INTO bf4br_node_controls(node_name)
                            VALUES (%s) ON CONFLICT DO NOTHING""",(node,))
                        cur.execute("""SELECT persona_workers,report_workers,paused,request_interval_seconds,http_429_cooldown_seconds
                            FROM bf4br_node_controls WHERE node_name=%s""",(node,))
                        persona_target,report_target,paused,interval,cooldown=cur.fetchone()
                publish_request_policy(interval,cooldown)
                for pid,(process,kind,draining) in list(children.items()):
                    if process.poll() is not None:
                        LOG.info("worker exited pid=%s status=%s",pid,process.returncode)
                        del children[pid]
                        active_specs.pop(pid,None)
                # Opt-in heartbeat; default remains the v1.0.5 behavior.
                # Heartbeat failure never interrupts existing collector jobs.
                if heartbeat_enabled and time.monotonic()-last_heartbeat >= 10:
                    try:
                        heartbeat(conn,node,instance_id,os.getpid(),
                                  sum(k=='persona' and not draining for _,k,draining in children.values()),
                                  sum(k=='report' and not draining for _,k,draining in children.values()))
                        last_heartbeat=time.monotonic()
                    except psycopg.Error:
                        LOG.exception('heartbeat failed; collector jobs unchanged')
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
                # Coordinated persona roles are opt-in. Report workers retain
                # their existing independent configuration and pacing.
                if coordinated:
                    assignment=read_assignment(conn,node)
                    specs=desired_specs(assignment,persona_target,paused)
                    desired_spec=specs[0] if specs else None
                    # Never overlap old and new persona jobs on one node.
                    # Wait for the old process to exit after SIGTERM before
                    # starting its replacement.
                    for pid,(process,kind,draining) in list(children.items()):
                        if kind!='persona' or draining:
                            continue
                        if active_specs.get(pid)!=desired_spec:
                            process.terminate()
                            children[pid]=(process,kind,True)
                            LOG.info('draining persona for assignment change pid=%s',pid)
                    active_persona=[pid for pid,(_,kind,_) in children.items() if kind=='persona']
                    if desired_spec is not None and not active_persona:
                        serial+=1
                        env={**os.environ,'BF4BR_WORKER_ID':f'{node}-persona-{serial}'}
                        if desired_spec.platform is None:
                            env.pop('BF4BR_PLATFORM',None)
                        else:
                            env['BF4BR_PLATFORM']=str(desired_spec.platform)
                        if desired_spec.role=='rotating':
                            env['BF4BR_ROTATING']='1'
                        else:
                            env.pop('BF4BR_ROTATING',None)
                        process=subprocess.Popen([sys.executable,'-m',worker_module(desired_spec)],env=env)
                        children[process.pid]=(process,'persona',False)
                        active_specs[process.pid]=desired_spec
                        LOG.info('started coordinated persona pid=%s role=%s platform=%s',
                                 process.pid,desired_spec.role,desired_spec.platform)
                for kind,desired in (("persona",persona_target),("report",report_target)):
                    if coordinated and kind=='persona':
                        continue
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
            except (psycopg.OperationalError,psycopg.InterfaceError):
                LOG.exception('supervisor database connection lost; keeping existing workers')
                if conn is not None:
                    try:
                        conn.close()
                    except psycopg.Error:
                        pass
                conn=None
            except (psycopg.Error,OSError):
                LOG.exception("supervisor control loop failed; existing workers unchanged")
            time.sleep(3)
    finally:
        if conn is not None:
            conn.close()
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
