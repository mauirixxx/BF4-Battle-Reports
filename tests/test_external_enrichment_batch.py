import unittest
from unittest.mock import patch
from uuid import UUID
from bf4br.external_enrichment_batch import (start_batch, finish_batch, BatchBusy, CooldownActive)
from bf4br.external_enrichment_claim import Reservation


class Cursor:
    def __init__(self, conn): self.conn=conn; self.rowcount=1
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def execute(self,sql,args): self.conn.statements.append((sql,args))
    def fetchone(self): return self.conn.rows.pop(0)


class Conn:
    def __init__(self, rows): self.rows=rows; self.statements=[]
    def transaction(self): return self
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def cursor(self): return Cursor(self)


class BatchTests(unittest.TestCase):
    def test_start_records_every_reserved_item(self):
        conn=Conn([(None,),(False,)])
        reservation=Reservation(32,123,(90,80),('token1','token2'))
        batch,result=start_batch(conn,'worker',lambda c: reservation)
        self.assertIsInstance(batch,UUID)
        self.assertEqual(result,reservation)
        inserts=[s for s,a in conn.statements if 'INSERT INTO bf4br_external_batch_items' in s]
        self.assertEqual(len(inserts),2)
    def test_existing_active_batch_blocks_claim(self):
        conn=Conn([('old',),('active',),(1,)])
        with self.assertRaises(BatchBusy): start_batch(conn,'worker',lambda c: self.fail('reserved'))
    def test_expired_batch_sets_cooldown(self):
        conn=Conn([('old',),('active',),None,(True,)])
        self.assertEqual(start_batch(conn,'worker',lambda c: self.fail('reserved')),('cooldown',None))
        self.assertTrue(any("state='expired'" in sql for sql,_ in conn.statements))
    def test_cooldown_blocks_claim(self):
        conn=Conn([(None,),(True,)])
        self.assertEqual(start_batch(conn,'worker',lambda c: self.fail('reserved')),('cooldown',None))
    def test_finish_requires_settled_items(self):
        conn=Conn([('batch',),(1,)])
        with self.assertRaises(BatchBusy): finish_batch(conn,'worker','batch')
    def test_finish_sets_61_second_floor(self):
        conn=Conn([('batch',),None])
        finish_batch(conn,'worker','batch')
        self.assertTrue(any('cooldown_until=GREATEST' in s and a[0]==61 for s,a in conn.statements))
        with self.assertRaises(ValueError): finish_batch(conn,'worker','batch',cooldown_seconds=60)

if __name__=='__main__': unittest.main()

[executed on device: reports (d4380674-2627-4f06-a351-173869e82fbe)]