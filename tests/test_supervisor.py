import os
import signal
import subprocess
import sys
import time
import unittest
import psycopg

DSN=os.environ.get("BF4BR_TEST_DSN")

@unittest.skipUnless(DSN,"isolated PostgreSQL test required")
class SupervisorIntegration(unittest.TestCase):
    def test_live_resize_pause_and_shutdown(self):
        with psycopg.connect(DSN,autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT current_database()")
                self.assertEqual(cur.fetchone()[0],"bf4br_integration")
                cur.execute("""INSERT INTO bf4br_node_controls
                    (node_name,persona_workers,report_workers,paused)
                    VALUES ('supervisor-test',0,0,false)
                    ON CONFLICT(node_name) DO UPDATE
                    SET persona_workers=0,report_workers=0,paused=false""")
            env={**os.environ,"BF4BR_DSN":DSN,"BF4BR_NODE":"supervisor-test"}
            proc=subprocess.Popen([sys.executable,"-m","bf4br.supervisor"],
                                  env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            def children():
                try:
                    with open(f"/proc/{proc.pid}/task/{proc.pid}/children") as f:
                        return [int(v) for v in f.read().split()]
                except FileNotFoundError:
                    return []
            def await_count(target,timeout=18):
                until=time.monotonic()+timeout
                while time.monotonic()<until:
                    if len(children())==target:
                        return
                    time.sleep(.3)
                self.assertEqual(len(children()),target,
                                 f"expected {target} child processes, saw {children()}")
            try:
                await_count(0)
                with conn.cursor() as cur:
                    cur.execute("""UPDATE bf4br_node_controls
                        SET persona_workers=2,report_workers=1 WHERE node_name='supervisor-test'""")
                await_count(3)
                with conn.cursor() as cur:
                    cur.execute("""UPDATE bf4br_node_controls
                        SET paused=true WHERE node_name='supervisor-test'""")
                await_count(0)
            finally:
                proc.terminate()
                try:
                    proc.communicate(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.communicate()
            self.assertEqual(proc.returncode,0)
