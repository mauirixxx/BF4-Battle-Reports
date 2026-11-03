import os
import unittest
import uuid
import psycopg
from bf4br.queue import claim
from bf4br.report_store import archive,recover

DSN=os.environ.get("BF4BR_TEST_DSN")

@unittest.skipUnless(DSN,"isolated test database required")
class ReportStoreIntegration(unittest.TestCase):
    def test_archive_survives_stale_lease_and_import_failure(self):
        payload={"id":987,"platform":1,"createdAt":1900,
                 "gameServer":{"guid":"00000000-0000-0000-0000-000000000001","name":"test"},
                 "players":{"a":{"personaId":1,"persona":{"personaName":"test"}}}}
        with psycopg.connect(DSN,autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT current_database()")
                self.assertEqual(cur.fetchone()[0],"bf4br_integration")
                cur.execute("TRUNCATE bf4br_report_jobs,battle_report_raw,battle_report_details")
                cur.execute("INSERT INTO bf4br_report_jobs(platform,battlelog_report_id) VALUES (1,987)")
            row,token=claim(conn,"report","test",60)
            with self.assertRaises(RuntimeError):
                archive(conn,1,987,uuid.uuid4(),payload)
            self.assertIsNone(recover(conn,1,987))
            self.assertTrue(archive(conn,1,987,token,payload))
            stored=recover(conn,1,987)
            self.assertEqual(stored[0],payload)
            self.assertIsNone(stored[1])
            self.assertTrue(archive(conn,1,987,token,payload))
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM battle_report_raw")
                self.assertEqual(cur.fetchone()[0],1)

[executed on device: reports (d4380674-2627-4f06-a351-173869e82fbe)]