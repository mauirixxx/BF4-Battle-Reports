import os
import unittest
from datetime import date
import psycopg
from bf4br.queue import claim

@unittest.skipUnless(os.environ.get('BF4BR_TEST_DSN'),'isolated PostgreSQL required')
class PriorityIntegration(unittest.TestCase):
    def test_daily_report_claims_before_historical(self):
        with psycopg.connect(os.environ['BF4BR_TEST_DSN'],autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT current_database()')
                self.assertEqual(cur.fetchone()[0],'bf4br_integration')
                cur.execute('DELETE FROM bf4br_daily_report_jobs WHERE platform=1')
                cur.execute('DELETE FROM bf4br_report_jobs WHERE platform=1 AND battlelog_report_id IN (900000001,900000002)')
                cur.execute('INSERT INTO bf4br_report_jobs(platform,battlelog_report_id) VALUES (1,900000001),(1,900000002)')
                cur.execute('INSERT INTO bf4br_daily_report_jobs(day_utc,platform,battlelog_report_id) VALUES (%s,1,900000002)',(date(2026,11,2),))
            job=claim(conn,'report','priority-test',120,platform=1)
            self.assertEqual(job[0],(1,900000002))