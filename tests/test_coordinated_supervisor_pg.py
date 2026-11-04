"""Real supervisor process handoff against disposable PostgreSQL only."""
import os
import subprocess
import sys
import time
import unittest
from uuid import uuid4
import psycopg
from bf4br.assignment_planner import Assignment
from bf4br.fleet_coordination import acquire_leadership, publish

DSN=os.environ.get('BF4BR_TEST_DSN')
NODE='coord-supervisor-test'

@unittest.skipUnless(DSN,'isolated PostgreSQL required')
class CoordinatedSupervisorPG(unittest.TestCase):
    def test_handoff_no_overlapping_children_and_pause(self):
        with psycopg.connect(DSN,autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT current_database()')
                self.assertEqual(cur.fetchone()[0],'bf4br_integration')
                cur.execute('''INSERT INTO bf4br_node_controls(node_name,persona_workers,report_workers,paused)
                    VALUES (%s,1,0,false) ON CONFLICT(node_name) DO UPDATE SET
                    persona_workers=1,report_workers=0,paused=false''',(NODE,))
                cur.execute("DELETE FROM bf4br_coordinator_leases WHERE name='scheduler'")
            owner=uuid4()
            generation=acquire_leadership(conn,owner)
            self.assertTrue(publish(conn,owner,generation,[Assignment(NODE,'historical',1)]))
            env={**os.environ,'BF4BR_DSN':DSN,'BF4BR_NODE':NODE,'BF4BR_COORDINATED':'1'}
            proc=subprocess.Popen([sys.executable,'-m','bf4br.supervisor'],env=env,
                                  stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            def children():
                try:
                    with open(f'/proc/{proc.pid}/task/{proc.pid}/children') as f:
                        return [int(x) for x in f.read().split()]
                except FileNotFoundError:
                    return []
            def await_new(excluded=None,timeout=18):
                end=time.monotonic()+timeout
                while time.monotonic()<end:
                    pids=children()
                    if len(pids)==1 and pids[0]!=excluded:
                        return pids[0]
                    self.assertLessEqual(len(pids),1,'overlapping persona workers')
                    time.sleep(.2)
                self.fail(f'new child did not appear; children={children()}')
            try:
                first=await_new()
                self.assertTrue(publish(conn,owner,generation,[Assignment(NODE,'historical',32)]))
                second=await_new(first)
                self.assertNotEqual(first,second)
                with conn.cursor() as cur:
                    cur.execute('UPDATE bf4br_node_controls SET paused=true WHERE node_name=%s',(NODE,))
                deadline=time.monotonic()+18
                while children() and time.monotonic()<deadline:
                    time.sleep(.2)
                self.assertEqual(children(),[])
            finally:
                proc.terminate()
                try:
                    _,logs=proc.communicate(timeout=12)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    _,logs=proc.communicate()
                with conn.cursor() as cur:
                    cur.execute('DELETE FROM bf4br_worker_assignments WHERE node_name=%s',(NODE,))
                    cur.execute("DELETE FROM bf4br_coordinator_leases WHERE name='scheduler'")
                    cur.execute('DELETE FROM bf4br_node_heartbeats WHERE node_name=%s',(NODE,))
                    cur.execute('DELETE FROM bf4br_node_controls WHERE node_name=%s',(NODE,))
            self.assertEqual(proc.returncode,0,logs.decode(errors='replace')[-2000:])
