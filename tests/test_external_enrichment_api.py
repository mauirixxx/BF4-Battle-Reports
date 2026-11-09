import hashlib
import unittest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from fastapi.testclient import TestClient
from bf4br.external_enrichment_api import authenticate, health, app, MAX_REQUEST_BYTES


class ApiTests(unittest.TestCase):
    def test_authentication(self):
        key='example-test-only-key'
        digest=hashlib.sha256(key.encode()).hexdigest()
        conn=MagicMock()
        conn.cursor.return_value.__enter__.return_value.fetchone.return_value=('worker-1',digest)
        from contextlib import contextmanager
        @contextmanager
        def fake_db(): yield conn
        with patch('bf4br.external_enrichment_api.database',fake_db):
            self.assertEqual(authenticate('Bearer '+key),'worker-1')
            for header in (None, 'Basic '+key):
                with self.assertRaises(HTTPException) as ctx: authenticate(header)
                self.assertEqual(ctx.exception.status_code,401)
            conn.cursor.return_value.__enter__.return_value.fetchone.return_value=None
            with self.assertRaises(HTTPException): authenticate('Bearer invalid')
    def test_health(self):
        self.assertEqual(health()['status'],'ready')
    def test_request_size_limit(self):
        client=TestClient(app)
        self.assertEqual(client.post('/api/v1/work/claim',data=b'x'*(MAX_REQUEST_BYTES+1)).status_code,413)
        with patch('bf4br.external_enrichment_api.authenticate',side_effect=HTTPException(status_code=401)):
            self.assertEqual(client.post('/api/v1/work/claim',headers={'Authorization':'Bearer nope'},json={}).status_code,401)

[executed on device: reports (d4380674-2627-4f06-a351-173869e82fbe)]