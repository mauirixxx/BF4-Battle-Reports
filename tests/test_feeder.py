import unittest
from unittest.mock import Mock, patch
from bf4br.feeder import replenish

class FeederTests(unittest.TestCase):
    @patch('bf4br.feeder.seed')
    @patch('bf4br.feeder.queue_depths')
    def test_refill_both_bounded(self, depths, seed):
        depths.side_effect = [(10, 20), (260, 270)]
        seed.return_value = (250, 250)
        self.assertEqual(replenish(Mock()), ((250, 250), (260, 270)))
        seed.assert_called_once_with(unittest.mock.ANY, persona_limit=250, report_limit=250)

    @patch('bf4br.feeder.seed')
    @patch('bf4br.feeder.queue_depths')
    def test_refill_only_low_queue(self, depths, seed):
        depths.side_effect = [(600, 5), (600, 255)]
        seed.return_value = (0, 250)
        replenish(Mock())
        seed.assert_called_once_with(unittest.mock.ANY, persona_limit=0, report_limit=250)

    @patch('bf4br.feeder.seed')
    @patch('bf4br.feeder.queue_depths')
    def test_no_refill_when_healthy(self, depths, seed):
        depths.side_effect = [(300, 300), (300, 300)]
        replenish(Mock())
        seed.assert_not_called()
