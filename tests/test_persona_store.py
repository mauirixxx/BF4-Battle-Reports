import os
import unittest
import uuid
import psycopg
from bf4br.queue import claim
from bf4br.persona_store import persist_page

DSN=os.environ.get("BF4BR_TEST_DSN")

@unittest.skipUnless(DSN,"isolated test database required")
class PersonaStoreIntegration(unittest.TestCase):
    def setUp(self):
        self.conn=psycopg.connect(DSN,autocommit=True)
        with self.conn.cursor() as c:
            c.execute("SELECT current_database()")
            self.assertEqual(c.fetchone()[0],"bf4br_integration")
            c.execute("""TRUNCATE history_discoveries,history_report_sources,
                history_pages,history_persona_refreshes,bf4br_persona_jobs,
                bf4br_report_jobs""")
            c.execute("""INSERT INTO bf4br_persona_jobs
                (platform,persona_id,cursor_epoch) VALUES (1,123,2000)""")
    def tearDown(self):
        self.conn.close()
    def test_resumes_and_completes_without_duplicate_reports(self):
        row,token=claim(self.conn,"persona","node-1",60)
        self.assertEqual(row,(1,123))
        page={"data":{"gameReports":[
            {"gameReportId":88,"createdAt":1900,"name":"test","map":"MP_001"},
            {"gameReportId":87,"createdAt":1800,"name":"test","map":"MP_002"}]}}
        result=persist_page(self.conn,1,123,token,2000,page)
        self.assertEqual(result["next_cursor"],1799)
        self.assertFalse(result["finished"])
        with self.conn.cursor() as c:
            c.execute("SELECT cursor_epoch FROM bf4br_persona_jobs")
            self.assertEqual(c.fetchone()[0],1799)
        with self.assertRaises(RuntimeError):
            persist_page(self.conn,1,123,uuid.uuid4(),1799,{"data":{"gameReports":[]}})
        result=persist_page(self.conn,1,123,token,1799,{"data":{"gameReports":[]}})
        self.assertTrue(result["finished"])
        with self.conn.cursor() as c:
            c.execute("SELECT state,boundary_epoch,cursor_epoch FROM bf4br_persona_jobs")
            self.assertEqual(c.fetchone(),("ready",1900,None))
            c.execute("SELECT count(*) FROM history_pages")
            self.assertEqual(c.fetchone()[0],2)
            c.execute("SELECT count(*) FROM bf4br_report_jobs")
            self.assertEqual(c.fetchone()[0],2)
            c.execute("SELECT count(*) FROM history_persona_refreshes")
            self.assertEqual(c.fetchone()[0],1)
    def test_malformed_page_does_not_advance(self):
        row,token=claim(self.conn,"persona","node-1",60)
        with self.assertRaises(ValueError):
            persist_page(self.conn,1,123,token,2000,
                         {"data":{"gameReports":[{"gameReportId":5}]}})
        with self.conn.cursor() as c:
            c.execute("SELECT cursor_epoch FROM bf4br_persona_jobs")
            self.assertEqual(c.fetchone()[0],2000)
            c.execute("SELECT count(*) FROM history_pages")
            self.assertEqual(c.fetchone()[0],0)
