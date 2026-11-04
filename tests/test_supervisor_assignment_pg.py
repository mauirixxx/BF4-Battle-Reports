"""Verify coordinator lease expiry fences supervisor assignment reads."""
import os
import unittest
from uuid import uuid4
import psycopg
from bf4br.fleet_coordination import acquire_leadership,publish
from bf4br.assignment_planner import Assignment
from bf4br.supervisor_assignment import read_assignment

DSN=os.environ.get('BF4BR_TEST_DSN')

@unittest.skipUnless(DSN,'isolated PostgreSQL required')
class SupervisorAssignmentPG(unittest.TestCase):
    def test_valid_and_expired_coordinator(self):
        with psycopg.connect(DSN,autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT current_database()')
                self.assertEqual(cur.fetchone()[0],'bf4br_integration')
                cur.execute("INSERT INTO bf4br_node_controls(node_name,persona_workers) VALUES ('coord-read-test',1) ON CONFLICT(node_name) DO UPDATE SET persona_workers=1")
                cur.execute("DELETE FROM bf4br_coordinator_leases WHERE name='scheduler'")
            owner=uuid4()
            generation=acquire_leadership(conn,owner)
            self.assertTrue(publish(conn,owner,generation,[Assignment('coord-read-test','daily',64)]))
            self.assertEqual(read_assignment(conn,'coord-read-test'),('daily',64))
            with conn.cursor() as cur:
                cur.execute("UPDATE bf4br_coordinator_leases SET lease_until=clock_timestamp()-interval '1 second' WHERE name='scheduler'")
            self.assertIsNone(read_assignment(conn,'coord-read-test'))
            with conn.cursor() as cur:
                cur.execute("DELETE FROM bf4br_worker_assignments WHERE node_name='coord-read-test'")
                cur.execute("DELETE FROM bf4br_coordinator_leases WHERE name='scheduler'")
                cur.execute("DELETE FROM bf4br_node_controls WHERE node_name='coord-read-test'")
