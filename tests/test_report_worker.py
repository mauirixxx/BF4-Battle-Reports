import os
import unittest
from unittest.mock import Mock
import psycopg
from bf4br.queue import claim
from bf4br.report_worker import process_one

DSN=os.environ.get("BF4BR_TEST_DSN")
PAYLOAD={"id":987,"platform":1,"createdAt":1900,
 "gameServer":{"guid":"00000000-0000-0000-0000-000000000001","name":"test"},
 "players":{"a":{"personaId":123,"persona":{"personaName":"soldier"}}}}

@unittest.skipUnless(DSN,"isolated PostgreSQL required")
class ReportWorkerIntegration(unittest.TestCase):
    def setUp(self):
        self.conn=psycopg.connect(DSN,autocommit=True)
        with self.conn.cursor() as cur:
            cur.execute("SELECT current_database()")
            self.assertEqual(cur.fetchone()[0],"bf4br_integration")
            cur.execute("""TRUNCATE battle_report_raw,battle_report_details,
              battle_reports,report_players,players,player_name_history,servers,
              bf4br_report_jobs""")
            cur.execute("INSERT INTO bf4br_report_jobs(platform,battlelog_report_id) VALUES (1,987)")
    def tearDown(self):
        self.conn.close()
    def test_503_timeout_success_archive_import(self):
        job,token=claim(self.conn,"report","worker",120)
        fetch=Mock(side_effect=[(503,None,"HTTP 503"),(0,None,"timeout"),(200,PAYLOAD,None)])
        self.assertEqual(process_one(self.conn,job,token,fetcher=fetch,sleeper=lambda _:None),"imported")
        self.assertEqual(fetch.call_count,3)
        with self.conn.cursor() as cur:
            cur.execute("SELECT imported_at IS NOT NULL FROM battle_report_raw")
            self.assertTrue(cur.fetchone()[0])
            cur.execute("SELECT count(*) FROM battle_reports")
            self.assertEqual(cur.fetchone()[0],1)
            cur.execute("SELECT state FROM bf4br_report_jobs")
            self.assertEqual(cur.fetchone()[0],"done")
    def test_import_failure_recovery_no_redownload(self):
        job,token=claim(self.conn,"report","worker",120)
        invalid={**PAYLOAD,"players":{"a":{"personaId":0,"persona":{"personaName":"x"}}}}
        fetch=Mock(return_value=(200,invalid,None))
        self.assertEqual(process_one(self.conn,job,token,fetcher=fetch,sleeper=lambda _:None),"import_retry")
        self.assertEqual(fetch.call_count,1)
        with self.conn.cursor() as cur:
            cur.execute("SELECT imported_at FROM battle_report_raw")
            self.assertIsNone(cur.fetchone()[0])
            cur.execute("""UPDATE battle_report_raw SET raw_response=%s::jsonb
              WHERE platform=1 AND battlelog_report_id=987""",
              (__import__("json").dumps(PAYLOAD),))
            cur.execute("UPDATE bf4br_report_jobs SET next_attempt_at=now() WHERE platform=1")
        job,token=claim(self.conn,"report","worker2",120)
        never_fetch=Mock(side_effect=AssertionError("unexpected network call"))
        self.assertEqual(process_one(self.conn,job,token,fetcher=never_fetch,sleeper=lambda _:None),"imported")
        never_fetch.assert_not_called()
