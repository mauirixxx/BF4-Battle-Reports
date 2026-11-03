import os
import unittest
from unittest.mock import Mock
import psycopg
from bf4br.queue import claim
from bf4br.report_store import archive,recover
from bf4br.report_worker import process_one

DSN=os.environ.get("BF4BR_TEST_DSN")
PAYLOAD={"id":"987","platform":"1","createdAt":1900,
 "gameServer":{"guid":"00000000-0000-0000-0000-000000000001","name":"test"},
 "players":{"a":{"personaId":123,"persona":{"personaName":"soldier"}}}}

@unittest.skipUnless(DSN,"isolated PostgreSQL required")
class ReportCrashRecovery(unittest.TestCase):
    def test_archive_then_expired_lease_recovery_without_refetch(self):
        with psycopg.connect(DSN,autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT current_database()")
                self.assertEqual(cur.fetchone()[0],"bf4br_integration")
                cur.execute("""TRUNCATE bf4br_report_jobs,battle_report_raw,
                    battle_report_details,battle_reports,report_players,
                    players,player_name_history,servers""")
                cur.execute("INSERT INTO bf4br_report_jobs(platform,battlelog_report_id) VALUES (1,987)")
            job,old_token=claim(conn,"report","crashed",120)
            archive(conn,1,987,old_token,PAYLOAD)
            with conn.cursor() as cur:
                cur.execute("""UPDATE bf4br_report_jobs SET lease_until=now()-interval '1 second'
                    WHERE platform=1 AND battlelog_report_id=987""")
            job,new_token=claim(conn,"report","replacement",120)
            self.assertNotEqual(old_token,new_token)
            with self.assertRaises(RuntimeError):
                archive(conn,1,987,old_token,PAYLOAD)
            no_network=Mock(side_effect=AssertionError("archive should be reused"))
            self.assertEqual(process_one(conn,job,new_token,fetcher=no_network,sleeper=lambda _:None),"imported")
            no_network.assert_not_called()
            self.assertIsNotNone(recover(conn,1,987)[1])
