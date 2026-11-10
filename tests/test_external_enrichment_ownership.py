import unittest
from unittest.mock import patch
from bf4br.external_enrichment_ownership import OwnershipLost, save_owned, renew_owned, retry_owned, acknowledge_saved


class Cursor:
    def __init__(self, row): self.row=row; self.queries=[]
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def execute(self,sql,args): self.queries.append((sql,args))
    def fetchone(self): return self.row


class Conn:
    def __init__(self,row): self.cur=Cursor(row)
    def cursor(self): return self.cur
    def transaction(self): return self
    def __enter__(self): return self
    def __exit__(self,*args): return False


class OwnershipTests(unittest.TestCase):
    def test_reject_wrong_worker(self):
        conn=Conn(None)
        with self.assertRaises(OwnershipLost):
            save_owned(conn,(1,20,30),'token','wrong-worker',{})
        self.assertIn('lease_owner=%s',conn.cur.queries[0][0])
        self.assertEqual(conn.cur.queries[0][1][-1],'wrong-worker')
    @patch('bf4br.external_enrichment_ownership.save_player')
    def test_save_after_fenced_owner_check(self, save):
        conn=Conn((1,))
        save_owned(conn,(1,20,30),'token','worker',{'id':20})
        save.assert_called_once_with(conn,(1,20,30),'token',{'id':20})
    @patch('bf4br.external_enrichment_ownership.renew_player',return_value=True)
    def test_renew(self, renew):
        renew_owned(Conn((1,)),(1,20,30),'token','worker')
        renew.assert_called_once()
    def test_ack_accepts_battlelog_string_report_id(self):
        conn=Conn((1,))
        payload={'id':'1792536478803219968','platform':1,
                 'players':{'994365084':{}},
                 'playerReport':{'personaId':'994365084','stats':{}}}
        self.assertTrue(acknowledge_saved(conn,(1,1792536478803219968,994365084),
                                          'token','worker','batch',payload))

    def test_ack_rejects_wrong_report_id(self):
        conn=Conn((1,))
        payload={'id':'1792536478803219969','platform':1,
                 'players':{'994365084':{}},
                 'playerReport':{'personaId':'994365084','stats':{}}}
        with self.assertRaisesRegex(ValueError,'identity mismatch'):
            acknowledge_saved(conn,(1,1792536478803219968,994365084),
                              'token','worker','batch',payload)

    @patch('bf4br.external_enrichment_ownership.retry_player',return_value=True)
    def test_retry(self, retry):
        retry_owned(Conn((1,)),(1,20,30),'token','worker','failed',1200)
        retry.assert_called_once()
