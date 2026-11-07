import unittest
from unittest.mock import patch
from bf4br.detail_coordinator import advance_if_leader


class FakeCursor:
    def __init__(self,row):
        self.row=row
        self.query=''
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def execute(self,sql,args):
        self.query=sql
    def fetchone(self): return self.row


class FakeTransaction:
    def __enter__(self): return self
    def __exit__(self,*args): pass


class FakeConnection:
    def __init__(self,row): self.row=row; self.cursor_obj=None
    def transaction(self): return FakeTransaction()
    def cursor(self):
        self.cursor_obj=FakeCursor(self.row)
        return self.cursor_obj


class DetailCoordinatorTests(unittest.TestCase):
    @patch('bf4br.detail_coordinator.activate')
    @patch('bf4br.detail_coordinator.settle_report')
    @patch('bf4br.detail_coordinator.seed_reports')
    def test_standby_cannot_advance(self,seed,settle,activate):
        conn=FakeConnection(None)
        self.assertIsNone(advance_if_leader(conn,'standby'))
        seed.assert_not_called()
        settle.assert_not_called()
        activate.assert_not_called()
        self.assertIn('FOR UPDATE',conn.cursor_obj.query)

    @patch('bf4br.detail_coordinator.activate',return_value=(1,123))
    @patch('bf4br.detail_coordinator.settle_report',return_value=[])
    @patch('bf4br.detail_coordinator.seed_reports',return_value=7)
    def test_leader_advances(self,seed,settle,activate):
        conn=FakeConnection((12,))
        result=advance_if_leader(conn,'leader')
        self.assertEqual(result,{'generation':12,'seeded':7,'settled':[],
                                 'activated':(1,123)})
        seed.assert_called_once_with(conn,limit=250)
        settle.assert_called_once_with(conn)
        activate.assert_called_once_with(conn)


if __name__=='__main__':
    unittest.main()
