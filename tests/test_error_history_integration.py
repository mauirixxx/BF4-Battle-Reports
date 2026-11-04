"""Append-only attribution tests; requires isolated bf4br_integration DB."""
import os
import unittest
from datetime import date
import psycopg
from bf4br.queue import claim,release
from bf4br.daily_queue import claim as daily_claim,release as daily_release

DSN=os.environ.get('BF4BR_TEST_DSN')
@unittest.skipUnless(DSN,'BF4BR_TEST_DSN not configured')
class ErrorHistoryIntegration(unittest.TestCase):
    def test_attribution_survives_lease_clear_and_stale_release(self):
        with psycopg.connect(DSN,autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT current_database()')
                if cur.fetchone()[0]!='bf4br_integration':
                    raise RuntimeError('Refusing to modify non-integration database')
                cur.execute('TRUNCATE bf4br_collector_error_history,bf4br_persona_jobs,bf4br_daily_persona_jobs')
                cur.execute('INSERT INTO bf4br_persona_jobs(platform,persona_id) VALUES (1,987654321)')
                cur.execute("INSERT INTO bf4br_daily_persona_jobs(day_utc,platform,persona_id) VALUES ('2026-11-04',32,987654321)")
            row,token=claim(conn,'persona','mak-02-persona-17',120,platform=1)
            self.assertTrue(release(conn,'persona',*row,token,error='HTTP 429'))
            self.assertFalse(release(conn,'persona',*row,token,error='HTTP 429'))
            item,tok=daily_claim(conn,'persona',date(2026,11,4),32,'hnl-01-persona-3',120)
            self.assertTrue(daily_release(conn,'persona',date(2026,11,4),32,item,tok,error='HTTP 503'))
            with conn.cursor() as cur:
                cur.execute('SELECT node_name,worker_id,job_kind,error_message FROM bf4br_collector_error_history ORDER BY id')
                self.assertEqual(cur.fetchall(),[('mak-02','mak-02-persona-17','historical_persona','HTTP 429'),('hnl-01','hnl-01-persona-3','daily_persona','HTTP 503')])
                cur.execute('SELECT lease_owner FROM bf4br_persona_jobs WHERE platform=1 AND persona_id=987654321')
                self.assertIsNone(cur.fetchone()[0])
