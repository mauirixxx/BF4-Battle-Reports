"""Coordinator fencing and health tests on disposable bf4br_integration only."""
import os
import unittest
from uuid import uuid4
import psycopg
from bf4br.fleet_coordination import (
    heartbeat, healthy_nodes, acquire_leadership, publish, plan_once,
)
from bf4br.assignment_planner import Assignment

DSN = os.environ.get('BF4BR_TEST_DSN')

@unittest.skipUnless(DSN, 'isolated PostgreSQL required')
class FleetCoordinationPostgres(unittest.TestCase):
    def setUp(self):
        self.conn = psycopg.connect(DSN, autocommit=True)
        with self.conn.cursor() as cur:
            cur.execute('SELECT current_database()')
            if cur.fetchone()[0] != 'bf4br_integration':
                raise RuntimeError('refusing non-isolated database')
            cur.execute('DELETE FROM bf4br_worker_assignments')
            cur.execute('DELETE FROM bf4br_node_heartbeats')
            cur.execute('DELETE FROM bf4br_coordinator_leases')
            cur.execute("DELETE FROM bf4br_node_controls WHERE node_name LIKE 'coord-test-%'")
            cur.executemany('INSERT INTO bf4br_node_controls(node_name,persona_workers) VALUES (%s,1)',
                            [(f'coord-test-{n}',) for n in range(4)])

    def tearDown(self):
        with self.conn.cursor() as cur:
            cur.execute('DELETE FROM bf4br_worker_assignments')
            cur.execute('DELETE FROM bf4br_node_heartbeats')
            cur.execute('DELETE FROM bf4br_coordinator_leases')
            cur.execute("DELETE FROM bf4br_node_controls WHERE node_name LIKE 'coord-test-%'")
        self.conn.close()

    def test_health_pause_expiry_and_progress(self):
        instance = uuid4()
        heartbeat(self.conn, 'coord-test-0', instance, 123, 1, 2)
        heartbeat(self.conn, 'coord-test-1', uuid4(), 456, 0, 1)
        with self.conn.cursor() as cur:
            cur.execute("UPDATE bf4br_node_controls SET paused=true WHERE node_name='coord-test-1'")
        self.assertEqual(healthy_nodes(self.conn), ['coord-test-0'])
        with self.conn.cursor() as cur:
            cur.execute("UPDATE bf4br_node_heartbeats SET seen_at=clock_timestamp()-interval '61 seconds' WHERE node_name='coord-test-0'")
        self.assertEqual(healthy_nodes(self.conn), [])

    def test_leader_exclusion_takeover_and_stale_publish(self):
        a, b = uuid4(), uuid4()
        generation = acquire_leadership(self.conn, a)
        self.assertEqual(generation, 1)
        self.assertEqual(acquire_leadership(self.conn, a), generation)
        self.assertIsNone(acquire_leadership(self.conn, b))
        assignment = [Assignment('coord-test-0', 'daily', 1)]
        self.assertTrue(publish(self.conn, a, generation, assignment))
        with self.conn.cursor() as cur:
            cur.execute("UPDATE bf4br_coordinator_leases SET lease_until=clock_timestamp()-interval '1 second' WHERE name='scheduler'")
        self.assertFalse(publish(self.conn, a, generation, []))
        self.assertEqual(acquire_leadership(self.conn, b), generation + 1)
        self.assertFalse(publish(self.conn, a, generation, []))
        self.assertTrue(publish(self.conn, b, generation + 1, []))
        with self.conn.cursor() as cur:
            cur.execute('SELECT count(*) FROM bf4br_worker_assignments')
            self.assertEqual(cur.fetchone()[0], 0)

    def test_planner_only_uses_live_nodes(self):
        owner = uuid4()
        heartbeat(self.conn, 'coord-test-0', uuid4(), 100, 1, 1)
        heartbeat(self.conn, 'coord-test-1', uuid4(), 101, 1, 1)
        assignments = plan_once(self.conn, owner)
        self.assertEqual([a.node for a in assignments], ['coord-test-0', 'coord-test-1'])
        with self.conn.cursor() as cur:
            cur.execute('SELECT node_name,role,platform FROM bf4br_worker_assignments ORDER BY node_name')
            self.assertEqual(cur.fetchall(), [('coord-test-0', 'daily', 1), ('coord-test-1', 'daily', 32)])

if __name__ == '__main__':
    unittest.main()
