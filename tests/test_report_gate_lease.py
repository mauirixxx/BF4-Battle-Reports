"""Report worker must retain its fenced lease during request-gate waits."""
import unittest
from unittest.mock import patch, MagicMock
from bf4br import report_worker

class ReportGateLeaseTests(unittest.TestCase):
    def test_wait_renews_before_fetch(self):
        conn=MagicMock()
        with patch.object(report_worker,'renew',return_value=True) as renew, \
             patch.object(report_worker,'recover',return_value=None), \
             patch.object(report_worker,'archive'), \
             patch.object(report_worker,'import_archived',return_value=True), \
             patch.object(report_worker,'release',return_value=True), \
             patch.object(report_worker,'guarded_request') as gate:
            def simulate_wait(fetch, status_of, retry_after_of, on_wait):
                on_wait();on_wait();on_wait()
                return 200,{'id':42},None,None
            gate.side_effect=simulate_wait
            result=report_worker.process_one(conn,(1,42),'token')
            self.assertEqual(result,'imported')
            self.assertGreaterEqual(renew.call_count,5)
    def test_wait_fails_closed_on_lost_lease(self):
        conn=MagicMock()
        with patch.object(report_worker,'renew',side_effect=[True,True,False]), \
             patch.object(report_worker,'recover',return_value=None), \
             patch.object(report_worker,'guarded_request') as gate, \
             patch.object(report_worker,'archive') as archive:
            def simulate_wait(fetch,status_of,retry_after_of,on_wait):
                on_wait()
            gate.side_effect=simulate_wait
            with self.assertRaisesRegex(RuntimeError,'lease lost'):
                report_worker.process_one(conn,(1,42),'token')
            archive.assert_not_called()

if __name__=='__main__':unittest.main()