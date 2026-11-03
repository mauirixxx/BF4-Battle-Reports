"""Real PostgreSQL coordination tests; run only against disposable test DB."""
import concurrent.futures
import os
import time
import unittest
import uuid
import psycopg
from bf4br.queue import claim, renew, release

DSN = os.environ["BF4BR_TEST_DSN"]

def connection():
    return psycopg.connect(DSN, autocommit=True)

class QueueIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admin = connection()
        with cls.admin.cursor() as cur:
            cur.execute("SELECT current_database()")
            if cur.fetchone()[0] != "bf4br_integration":
                raise RuntimeError("Refusing to run destructive tests outside bf4br_integration")

    @classmethod
    def tearDownClass(cls):
        cls.admin.close()

    def setUp(self):
        with self.admin.cursor() as cur:
            cur.execute("TRUNCATE bf4br_persona_jobs,bf4br_report_jobs,bf4br_node_controls")

    def insert(self, kind, count):
        table, key = ("bf4br_persona_jobs","persona_id") if kind == "persona" else ("bf4br_report_jobs","battlelog_report_id")
        with self.admin.cursor() as cur:
            cur.executemany(f"INSERT INTO {table}(platform,{key}) VALUES (%s,%s)",
                            [(1,i+1000) for i in range(count)])

    def test_parallel_claims_unique_for_both_queues(self):
        for kind in ("persona","report"):
            self.insert(kind, 120)
            def worker(i):
                c = connection()
                got = []
                try:
                    while True:
                        item = claim(c,kind,f"worker-{i}",60)
                        if not item:
                            return got
                        row,token=item
                        got.append(row)
                        self.assertTrue(release(c,kind,*row,token,done=True))
                finally:
                    c.close()
            with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
                results=list(pool.map(worker,range(12)))
            all_rows=[row for group in results for row in group]
            self.assertEqual(len(all_rows),120)
            self.assertEqual(len(set(all_rows)),120)
            with self.admin.cursor() as cur:
                table="bf4br_persona_jobs" if kind=="persona" else "bf4br_report_jobs"
                cur.execute(f"SELECT count(*) FROM {table} WHERE state='done'")
                self.assertEqual(cur.fetchone()[0],120)

    def test_lease_expiry_and_stale_fencing(self):
        self.insert("persona",1)
        first=claim(self.admin,"persona","dead-worker",1)
        self.assertIsNotNone(first)
        row,token=first
        self.assertIsNone(claim(self.admin,"persona","another-worker",1))
        time.sleep(1.2)
        second=claim(self.admin,"persona","new-worker",30)
        self.assertIsNotNone(second)
        row2,newtoken=second
        self.assertEqual(row,row2)
        self.assertNotEqual(token,newtoken)
        self.assertFalse(release(self.admin,"persona",*row,token,done=True))
        self.assertFalse(renew(self.admin,"persona",*row,token))
        self.assertTrue(renew(self.admin,"persona",*row,newtoken))
        self.assertTrue(release(self.admin,"persona",*row,newtoken,done=True))

    def test_retry_and_node_control(self):
        self.insert("report",1)
        row,token=claim(self.admin,"report","worker",30)
        self.assertTrue(release(self.admin,"report",*row,token,delay_seconds=30,error="HTTP 503"))
        self.assertIsNone(claim(self.admin,"report","worker2",30))
        with self.admin.cursor() as cur:
            cur.execute("SELECT state,failures,last_error FROM bf4br_report_jobs")
            self.assertEqual(cur.fetchone(),("ready",1,"HTTP 503"))
            cur.execute("INSERT INTO bf4br_node_controls(node_name) VALUES ('test-node')")
            cur.execute("UPDATE bf4br_node_controls SET persona_workers=5,report_workers=2,paused=true WHERE node_name='test-node'")
            cur.execute("SELECT persona_workers,report_workers,paused FROM bf4br_node_controls WHERE node_name='test-node'")
            self.assertEqual(cur.fetchone(),(5,2,True))

if __name__ == "__main__":
    unittest.main()
