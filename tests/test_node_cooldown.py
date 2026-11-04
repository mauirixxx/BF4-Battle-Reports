import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from bf4br import node_cooldown

class NodeCooldownTests(unittest.TestCase):
    def test_429_blocks_following_request(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'gate.json'
            with patch.object(node_cooldown,'STATE',path):
                result=node_cooldown.guarded_request(lambda:(429,None,None),lambda r:r[0])
                self.assertEqual(result[0],429)
                data=json.loads(path.read_text())
                self.assertEqual(data['cooldown_seconds'],120)
                self.assertIsNone(data['retry_after'])
                with patch.object(node_cooldown.time,'time',return_value=data['until_epoch']+1):
                    self.assertEqual(node_cooldown.guarded_request(lambda:(200,),lambda r:r[0]),(200,))
    def test_retry_after_longer_than_default(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(node_cooldown,'STATE',Path(directory)/'gate.json'):
                node_cooldown.guarded_request(lambda:(429,'300'),lambda r:r[0],lambda r:r[1])
                self.assertEqual(json.loads(node_cooldown.STATE.read_text())['cooldown_seconds'],300)

class NodeCooldownConcurrencyTests(unittest.TestCase):
    def test_wait_and_lease_callback(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'gate.json'
            with patch.object(node_cooldown,'STATE',path):
                node_cooldown.guarded_request(lambda:(429,None),lambda r:r[0])
                state=json.loads(path.read_text())
                calls=[]
                def advance(seconds):
                    calls.append(seconds)
                    state['until_epoch']-=seconds
                    path.write_text(json.dumps(state))
                node_cooldown.wait_until_clear(sleeper=advance)
                self.assertGreaterEqual(len(calls),24)
                self.assertLessEqual(max(calls),5)
                with patch.object(node_cooldown.time,'time',return_value=state['until_epoch']+1):
                    self.assertEqual(node_cooldown.guarded_request(lambda:(200,),lambda r:r[0],on_wait=lambda:calls.append('renew')),(200,))
