import os
import subprocess
import sys
import unittest
import psycopg

DSN=os.environ.get("BF4BR_TEST_DSN")

@unittest.skipUnless(DSN,"BF4BR_TEST_DSN not configured")
class ControlIntegration(unittest.TestCase):
    def run_cli(self,*args):
        env={**os.environ,"BF4BR_DSN":DSN}
        return subprocess.run([sys.executable,"-m","bf4br.control","--node",
                               "integration-node",*args],env=env,
                              capture_output=True,text=True,check=True).stdout

    def test_dynamic_node_settings(self):
        with psycopg.connect(DSN,autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT current_database()")
                self.assertEqual(cur.fetchone()[0],"bf4br_integration")
        self.run_cli("set","--persona-workers","3")
        self.assertIn("persona_workers=3",self.run_cli("show"))
        self.assertIn("persona_workers=7",self.run_cli("set","--persona-workers","7"))
        self.assertIn("report_workers=10",self.run_cli("set","--report-workers","10"))
        self.assertIn("paused=True",self.run_cli("pause"))
        self.assertIn("paused=False",self.run_cli("resume"))
        self.assertIn("request_interval_seconds=15",self.run_cli("set","--request-interval-seconds","15"))
        self.assertIn("http_429_cooldown_seconds=240",self.run_cli("set","--http-429-cooldown-seconds","240"))
        self.assertIn("request_interval_seconds=15",self.run_cli("show"))
        self.assertIn("http_429_cooldown_seconds=240",self.run_cli("show"))
