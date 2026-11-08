"""Integration of opt-in burst scheduler with existing queue contracts."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from bf4br import detail_burst_worker as worker


class BurstWorkerTests(unittest.TestCase):
    def test_four_way_batch_saves_and_reserves_61_seconds(self):
        with tempfile.TemporaryDirectory() as d:
            state = Path(d)/'cooldown.json'
            claims = iter([((1, 10, i), f'token{i}') for i in range(1, 42)])
            saved=[]
            with patch.object(worker.node_cooldown, 'STATE', state), \
                 patch.object(worker.node_cooldown, 'policy_values', return_value=(10,180)), \
                 patch.object(worker, 'claim_player', side_effect=lambda *_: next(claims, None)), \
                 patch.object(worker, 'renew_player', return_value=True), \
                 patch.object(worker, 'save_player', side_effect=lambda c,j,t,p:saved.append(j)), \
                 patch.object(worker, 'retry_player', return_value=False):
                count, limited=worker.process_batch(object(), 'node',
                    fetcher=lambda p,r,i:(200, {'id':r,'platform':p},None,None))
            self.assertEqual((count,limited),(40,False))
            self.assertEqual(len(saved),40)
            self.assertGreaterEqual(json.loads(state.read_text())['until_epoch'], __import__('time').time()+59)


if __name__=='__main__':
    unittest.main()
