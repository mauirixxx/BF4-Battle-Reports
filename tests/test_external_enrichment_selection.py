import unittest
from unittest.mock import patch
from bf4br.external_enrichment_selection import MAX_REPORTS, eligible_reports, random_candidate


class Cursor:
    def __init__(self, rows, queries):
        self.rows, self.queries = rows, queries
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def execute(self, sql, args=None): self.queries.append((sql, args))
    def fetchone(self): return self.rows.pop(0)
    def fetchall(self): return self.rows.pop(0)


class Conn:
    def __init__(self, rows): self.rows, self.queries = rows, []
    def cursor(self): return Cursor(self.rows, self.queries)


class SelectionTests(unittest.TestCase):
    def test_limit_bounds(self):
        for limit in (0, 41, -1):
            with self.assertRaises(ValueError): eligible_reports(Conn([]), 1, limit=limit)
        with self.assertRaises(ValueError): eligible_reports(Conn([]), 0)
    def test_uses_player_membership_raw_dedupe_and_newest_order(self):
        conn=Conn([[(90,), (70,)]])
        self.assertEqual(eligible_reports(conn, 123), (90,70))
        sql, args=conn.queries[0]
        for phrase in ('report_players rp', 'bf4br_player_report_raw raw', 'raw.persona_id IS NULL',
                       'job.lease_until<=now()', 'r.report_timestamp DESC', 'LIMIT %s'):
            self.assertIn(phrase, sql)
        self.assertEqual(args,(123,40))
    @patch('bf4br.external_enrichment_selection.randbelow',return_value=3)
    def test_random_player_seek(self, random):
        conn=Conn([(1,100),(4,32,456),[(999,), (888,)]])
        result=random_candidate(conn)
        self.assertEqual((result.platform,result.persona_id,result.report_ids),(32,456,(999,888)))
        self.assertEqual(conn.queries[1][1],(4,))
    def test_empty_source(self):
        self.assertIsNone(random_candidate(Conn([(None,None)])))

if __name__=='__main__': unittest.main()

[executed on device: reports (d4380674-2627-4f06-a351-173869e82fbe)]