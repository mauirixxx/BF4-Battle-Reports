import unittest
from bf4br.external_enrichment_claim import claim_player_batch


class Cursor:
    def __init__(self, rows, statements): self.rows,self.statements=rows,statements
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def execute(self,sql,args): self.statements.append((sql,args))
    def fetchone(self): return self.rows.pop(0)
    def fetchall(self): return self.rows.pop(0)


class Transaction:
    def __enter__(self): return self
    def __exit__(self,*args): return False


class Conn:
    def __init__(self,rows): self.rows,self.statements=rows,[]
    def transaction(self): return Transaction()
    def cursor(self): return Cursor(self.rows,self.statements)


class ClaimTests(unittest.TestCase):
    def test_claim_reserves_one_player_only(self):
        conn=Conn([(32,123),[(900,None),(800,None)],(900,),(800,)])
        result=claim_player_batch(conn,15,'worker-a')
        self.assertEqual((result.platform,result.persona_id,result.report_ids),(32,123,(900,800)))
        self.assertEqual(len(set(result.tokens)),2)
        sql=' '.join(s for s,_ in conn.statements)
        for fragment in ('FOR UPDATE SKIP LOCKED','bf4br_player_report_raw',"parent.state IN ('active','complete')",'ON CONFLICT DO NOTHING',"state='leased'",'lease_until<=now()'):
            self.assertIn(fragment,sql)
    def test_locked_player_returns_no_claim(self):
        conn=Conn([None])
        self.assertIsNone(claim_player_batch(conn,10,'worker-a'))
    def test_empty_reports(self):
        conn=Conn([(1,123),[]])
        self.assertIsNone(claim_player_batch(conn,10,'worker-a'))
    def test_limits(self):
        for n in (0,41):
            with self.assertRaises(ValueError): claim_player_batch(Conn([]),10,'worker',limit=n)
        with self.assertRaises(ValueError): claim_player_batch(Conn([]),10,'worker',lease_seconds=20)

if __name__=='__main__': unittest.main()

[executed on device: reports (d4380674-2627-4f06-a351-173869e82fbe)]