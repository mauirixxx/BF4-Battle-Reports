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
                self.assertEqual(data['cooldown_seconds'],180)
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
                state["last_request_epoch"] = 0
                path.write_text(json.dumps(state))
                calls=[]
                def advance(seconds):
                    calls.append(seconds)
                    state['until_epoch']-=seconds
                    path.write_text(json.dumps(state))
                node_cooldown.wait_until_clear(sleeper=advance)
                self.assertGreaterEqual(len(calls),36)
                self.assertLessEqual(max(calls),5)
                with patch.object(node_cooldown.time,'time',return_value=state['until_epoch']+1):
                    self.assertEqual(node_cooldown.guarded_request(lambda:(200,),lambda r:r[0],on_wait=lambda:calls.append('renew')),(200,))

class NodePacingTests(unittest.TestCase):
    def test_cross_worker_spacing(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(node_cooldown,'STATE',Path(directory)/'gate.json'):
                clock=[1000.0]
                waits=[]
                def sleep(n):
                    waits.append(n)
                    clock[0]+=n
                with patch.object(node_cooldown.time,'time',side_effect=lambda:clock[0]):
                    node_cooldown.guarded_request(lambda:(200,'persona'),lambda r:r[0],sleeper=sleep)
                    node_cooldown.guarded_request(lambda:(200,'report'),lambda r:r[0],sleeper=sleep)
                self.assertGreaterEqual(sum(waits),10)
                self.assertEqual(json.loads(node_cooldown.STATE.read_text())['last_request_epoch'],1010.0)
    def test_429_retains_last_request(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(node_cooldown,'STATE',Path(directory)/'gate.json'):
                node_cooldown.guarded_request(lambda:(429,None),lambda r:r[0])
                self.assertIn('last_request_epoch',json.loads(node_cooldown.STATE.read_text()))

class LivePolicyTests(unittest.TestCase):
    def test_valid_policy_and_invalid_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'policy.json'
            with patch.object(node_cooldown,'POLICY',path):
                self.assertEqual(node_cooldown.policy_values(),(10,180))
                path.write_text(json.dumps({'request_interval_seconds':15,'http_429_cooldown_seconds':240}))
                self.assertEqual(node_cooldown.policy_values(),(15,240))
                path.write_text('{bad json')
                self.assertEqual(node_cooldown.policy_values(),(10,180))
    def test_live_policy_change_affects_next_request(self):
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory)/'state.json'
            policy=Path(directory)/'policy.json'
            policy.write_text(json.dumps({'request_interval_seconds':10,'http_429_cooldown_seconds':180}))
            now=[1000.0]
            with patch.object(node_cooldown,'STATE',state), patch.object(node_cooldown,'POLICY',policy):
                with patch.object(node_cooldown.time,'time',side_effect=lambda:now[0]):
                    node_cooldown.guarded_request(lambda:(200,),lambda r:r[0])
                    policy.write_text(json.dumps({'request_interval_seconds':20,'http_429_cooldown_seconds':240}))
                    node_cooldown.guarded_request(lambda:(200,),lambda r:r[0],sleeper=lambda seconds:now.__setitem__(0,now[0]+seconds))
                self.assertEqual(now[0],1020.0)
