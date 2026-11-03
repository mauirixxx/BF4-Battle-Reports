import os
import unittest
from unittest.mock import patch
import psycopg
from bf4br.queue import claim
from bf4br.persona_worker import process_one

DSN=os.environ.get("BF4BR_TEST_DSN")

@unittest.skipUnless(DSN,"isolated PostgreSQL test DSN required")
class PersonaWorkerIntegration(unittest.TestCase):
    def test_mock_battlelog_two_page_scan(self):
        with psycopg.connect(DSN,autocommit=True) as conn:
            with conn.cursor() as c:
                c.execute("SELECT current_database()")
                self.assertEqual(c.fetchone()[0],"bf4br_integration")
                c.execute("""TRUNCATE bf4br_persona_jobs,bf4br_report_jobs,
                    history_pages,history_discoveries,history_report_sources,
                    history_persona_refreshes""")
                c.execute("""INSERT INTO bf4br_persona_jobs
                    (platform,persona_id,cursor_epoch) VALUES (1,999,2000)""")
            job,token=claim(conn,"persona","mock-node",120)
            responses=[
                (200,{"data":{"gameReports":[
                    {"gameReportId":765,"createdAt":1900,"name":"server","map":"MP_001"}]}},None),
                (200,{"data":{"gameReports":[]}},None)]
            with patch("bf4br.persona_worker.get_page",side_effect=responses) as fetch,patch("bf4br.persona_worker.time.sleep"):
                process_one(conn,job,token)
            self.assertEqual(fetch.call_count,2)
            self.assertEqual(fetch.call_args_list[0].args[-1],2000)
            self.assertEqual(fetch.call_args_list[1].args[-1],1899)
            with conn.cursor() as c:
                c.execute("SELECT boundary_epoch,state FROM bf4br_persona_jobs")
                self.assertEqual(c.fetchone(),(1900,"ready"))
                c.execute("SELECT count(*) FROM bf4br_report_jobs")
                self.assertEqual(c.fetchone()[0],1)
