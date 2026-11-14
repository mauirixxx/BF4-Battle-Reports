"""Generic-report requests get a turn between detail bursts."""
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from bf4br import node_cooldown

class ReportPriorityWindowTests(unittest.TestCase):
    def test_marker_is_visible_and_clearable(self):
        with tempfile.TemporaryDirectory() as d, patch.object(node_cooldown, 'STATE', Path(d)/'state.json'):
            self.assertFalse(node_cooldown.report_is_waiting())
            node_cooldown.mark_report_waiting()
            self.assertTrue(node_cooldown.report_is_waiting())
            node_cooldown.clear_report_waiting()
            self.assertFalse(node_cooldown.report_is_waiting())

    def test_stale_marker_cannot_block_bursts(self):
        with tempfile.TemporaryDirectory() as d, patch.object(node_cooldown, 'STATE', Path(d)/'state.json'):
            node_cooldown.mark_report_waiting()
            path=node_cooldown.report_wait_marker()
            import os
            os.utime(path,(time.time()-90,time.time()-90))
            self.assertFalse(node_cooldown.report_is_waiting())

if __name__=='__main__': unittest.main()

class BurstFairnessTests(unittest.TestCase):
    def test_burst_yields_until_generic_report_gets_turn(self):
        from bf4br import detail_burst_worker as burst
        with tempfile.TemporaryDirectory() as d, patch.object(node_cooldown, 'STATE', Path(d)/'state.json'):
            node_cooldown.mark_report_waiting()
            waits=[]
            def sleep(seconds):
                waits.append(seconds)
                node_cooldown.clear_report_waiting()
            with patch.object(burst, 'claim_player', return_value=None):
                count, limited=burst.process_batch(object(), 'test', sleeper=sleep)
            self.assertEqual((count,limited),(0,False))
            self.assertTrue(waits)