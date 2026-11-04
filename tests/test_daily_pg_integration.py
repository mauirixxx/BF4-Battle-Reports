"""Isolated PostgreSQL test of daily lease, timestamp routing and historical isolation."""
import os
import unittest
from datetime import date, datetime, timezone
import psycopg
from bf4br.daily_queue import claim
from bf4br.daily_persona_worker import save_page

@unittest.skipUnless(os.environ.get('BF4BR_TEST_DSN'), 'isolated PostgreSQL required')
class DailyPostgresIntegration(unittest.TestCase):
    def test_daily_page_does_not_change_historical_persona_cursor(self):
        day=date(2026,11,2)
        with psycopg.connect(os.environ['BF4BR_TEST_DSN'],autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT current_database()')
                self.assertEqual(cur.fetchone()[0], 'bf4br_integration')
                cur.execute("DELETE FROM bf4br_daily_persona_jobs WHERE day_utc=%s AND platform=1 AND persona_id=987654321",(day,))
                cur.execute('INSERT INTO bf4br_daily_persona_jobs(day_utc,platform,persona_id) VALUES (%s,1,987654321) ON CONFLICT DO NOTHING',(day,))
            job=claim(conn,'persona',day,1,'test')
            self.assertIsNotNone(job)
            persona,token=job
            cursor=int(datetime(2026,11,4,tzinfo=timezone.utc).timestamp())
            stamp=int(datetime(2026,11,2,23,59,tzinfo=timezone.utc).timestamp())
            payload={'data':{'gameReports':[{'gameReportId':9876543210,'createdAt':stamp,'name':'test','map':'MP_001'}]}}
            finished,next_cursor=save_page(conn,day,1,persona,token,cursor,payload)
            self.assertFalse(finished)
            self.assertEqual(next_cursor,stamp-1)
            with conn.cursor() as cur:
                cur.execute('SELECT cursor_epoch FROM bf4br_daily_persona_jobs WHERE day_utc=%s AND platform=1 AND persona_id=%s',(day,persona))
                self.assertEqual(cur.fetchone()[0],stamp-1)
                cur.execute('SELECT count(*) FROM bf4br_report_jobs WHERE platform=1 AND battlelog_report_id=9876543210')
                self.assertEqual(cur.fetchone()[0],1)
                cur.execute('SELECT count(*) FROM bf4br_daily_report_jobs WHERE day_utc=%s AND platform=1 AND battlelog_report_id=9876543210',(day,))
                self.assertEqual(cur.fetchone()[0],1)
                cur.execute('SELECT count(*) FROM bf4br_persona_jobs WHERE persona_id=987654321')
                self.assertEqual(cur.fetchone()[0],0)