import unittest
from unittest.mock import Mock,patch
from bf4br.feeder import replenish

class FeederTests(unittest.TestCase):
    @patch('bf4br.feeder.seed_platform')
    @patch('bf4br.feeder.platform_depths')
    def test_each_platform_refilled_independently(self,depths,seed):
        depths.side_effect=[({1:500,32:0,64:0},{1:500,32:0,64:0}),
                            ({1:500,32:250,64:250},{1:500,32:250,64:250})]
        seed.return_value=(250,250)
        replenish(Mock())
        self.assertEqual([c.args[:3] for c in seed.call_args_list],
                         [(unittest.mock.ANY,32,250),(unittest.mock.ANY,64,250)])
        for c in seed.call_args_list:
            self.assertEqual(c.args[3],250)
