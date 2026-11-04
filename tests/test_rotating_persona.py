import os
import unittest
from unittest.mock import patch
from bf4br import persona_worker

class RotatingPersonaTests(unittest.TestCase):
    def test_platform_advances_only_after_job(self):
        platforms=[]
        def claim(conn,kind,worker,lease,platform=None):
            platforms.append(platform)
            if len(platforms)==4:
                persona_worker.STOP=True
                return None
            return ((platform,123), 'token')
        class Conn:
            def __enter__(self): return self
            def __exit__(self,*args): pass
        try:
            persona_worker.STOP=False
            with patch.dict(os.environ,{'BF4BR_DSN':'unused','BF4BR_ROTATING':'1'},clear=True), \
                 patch.object(persona_worker.psycopg,'connect',return_value=Conn()), \
                 patch.object(persona_worker,'claim',side_effect=claim), \
                 patch.object(persona_worker,'process_one'), \
                 patch.object(persona_worker.time,'sleep'):
                persona_worker.main()
            self.assertEqual(platforms,[1,32,64,1])
        finally:
            persona_worker.STOP=False

    def test_reject_fixed_platform_for_rotator(self):
        with patch.dict(os.environ,{'BF4BR_DSN':'unused','BF4BR_ROTATING':'1','BF4BR_PLATFORM':'32'},clear=True):
            with self.assertRaises(ValueError):
                persona_worker.main()
