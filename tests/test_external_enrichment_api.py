import hashlib
import os
import unittest
from unittest.mock import patch

try:
    from fastapi import HTTPException
    from bf4br.external_enrichment_api import authenticate, health
except ImportError:
    HTTPException = None


@unittest.skipIf(HTTPException is None, 'FastAPI optional dependency not installed')
class ApiTests(unittest.TestCase):
    def test_authentication(self):
        key='example-test-only-key'
        with patch.dict(os.environ, {'BF4BR_API_KEY_SHA256':hashlib.sha256(key.encode()).hexdigest(),
                                  'BF4BR_API_WORKER_ID':'worker-1'}):
            self.assertEqual(authenticate('Bearer '+key), 'worker-1')
            for header in (None, 'Bearer invalid', 'Basic '+key):
                with self.assertRaises(HTTPException) as ctx:
                    authenticate(header)
                self.assertEqual(ctx.exception.status_code, 401)
    def test_health(self):
        self.assertEqual(health()['status'], 'ready')

[executed on device: reports (d4380674-2627-4f06-a351-173869e82fbe)]