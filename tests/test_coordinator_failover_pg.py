"""Isolated PostgreSQL coordinator failure and fencing recovery."""
import os
import unittest
from uuid import uuid4
import psycopg
from bf4br.fleet_coordination import heartbeat, plan_once, acquire_leadership, publish
from bf4br.supervisor_assignment import read_assignment
from bf4br.assignment_planner import Assignment

DSN=os.environ.get('BF4BR_TEST_DSN')
PREFIX='failover-test-'

@unittest.skipUnless(DSN,'isolated PostgreSQL required')
class CoordinatorFailoverPG(unittest.TestCase):
    def test_failure_takeover_preserves_survivors_and_fences_old_leader(self):
        with psycopg.connect(DSN,autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT current_database()')
                self.assertEqual(cur.fetchone()[0],'bf4br_integration')
                cur.execute("DELETE FROM bf4br_worker_assignments")
                cur.execute("DELETE FROM bf4br_node_heartbeats")
                cur.execute("DELETE FROM bf4br_coordinator_leases")
                cur.executemany('''INSERT INTO bf4br_node_controls(node_name,persona_workers,paused)
                    VALUES (%s,1,false) ON CONFLICT(node_name) DO UPDATE SET persona_workers=1,paused=false''',
                    [(f'{PREFIX}{i}',) for i in range(10)])
            try:
                for i in range(10):
                    heartbeat(conn,f'{PREFIX}{i}',uuid4(),100+i,1,0)
                first_owner=uuid4()
                first=plan_once(conn,first_owner)
                self.assertEqual(len(first),10)
                original={a.node:a for a in first}
                lost=next(a.node for a in first if a.role=='historical')
                with conn.cursor() as cur:
                    cur.execute("UPDATE bf4br_node_heartbeats SET seen_at=clock_timestamp()-interval '61 seconds' WHERE node_name=%s",(lost,))
                    cur.execute("UPDATE bf4br_coordinator_leases SET lease_until=clock_timestamp()-interval '1 second' WHERE name='scheduler'")
                self.assertIsNone(read_assignment(conn,f'{PREFIX}0'))
                second_owner=uuid4()
                after=plan_once(conn,second_owner)
                self.assertEqual(len(after),9)
                self.assertTrue(all(a==original[a.node] for a in after))
                self.assertIsNone(read_assignment(conn,lost))
                with conn.cursor() as cur:
                    cur.execute("SELECT generation FROM bf4br_coordinator_leases WHERE name='scheduler'")
                    generation=cur.fetchone()[0]
                self.assertFalse(publish(conn,first_owner,generation-1,first))
                self.assertEqual(read_assignment(conn,after[0].node),(after[0].role,after[0].platform))
            finally:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM bf4br_worker_assignments")
                    cur.execute("DELETE FROM bf4br_node_heartbeats")
                    cur.execute("DELETE FROM bf4br_coordinator_leases")
                    cur.execute('DELETE FROM bf4br_node_controls WHERE node_name LIKE %s',(PREFIX+'%',))
