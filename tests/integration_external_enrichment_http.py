"""End-to-end ASGI HTTP test against isolated scratch PostgreSQL only.
Run after integration_external_enrichment_postgres.py, as postgres OS user.
"""
import json
import psycopg
from fastapi.testclient import TestClient
from unittest.mock import patch
from contextlib import contextmanager
from bf4br.external_enrichment_api import app
DSN='dbname=bf4br_external_api_test user=postgres'

@contextmanager
def scratch_db():
    with psycopg.connect(DSN,autocommit=True) as conn:
        yield conn

def main():
    with scratch_db() as conn, conn.cursor() as c:
        c.execute('''SELECT b.batch_id,b.worker_id,i.platform,i.battlelog_report_id,
            i.persona_id,i.lease_token,r.raw_response
            FROM bf4br_external_batches b
            JOIN bf4br_external_batch_items i ON i.batch_id=b.batch_id
            JOIN bf4br_player_report_raw r ON r.platform=i.platform
              AND r.battlelog_report_id=i.battlelog_report_id AND r.persona_id=i.persona_id
            WHERE b.state='completed' LIMIT 1''')
        batch,worker,platform,rid,persona,token,payload=c.fetchone()
    body={'batch_id':str(batch),'platform':platform,'report_id':rid,
          'persona_id':persona,'token':str(token),'payload':payload}
    with patch('bf4br.external_enrichment_api.database',scratch_db):
        with TestClient(app) as client:
            headers={'Authorization':'Bearer '+worker}
            r=client.post('/api/v1/enrichment',json=body,headers=headers)
            assert r.status_code==200,(r.status_code,r.text)
            assert r.json()=={'stored':True,'already_stored':True},r.text
            r=client.post('/api/v1/enrichment',json={**body,'payload':{**payload,'tampered':True}},headers=headers)
            assert r.status_code==409,(r.status_code,r.text)
            r=client.post('/api/v1/enrichment',json=body,headers={'Authorization':'Bearer incorrect'})
            assert r.status_code==401,(r.status_code,r.text)
            r=client.post('/api/v1/enrichment',content=b'x'*(2*1024*1024+1),headers=headers)
            assert r.status_code==413,(r.status_code,r.text)
    print('PASS: HTTP duplicate ACK 200, altered payload 409, bad key 401, oversized body 413')
if __name__=='__main__':main()

[executed on device: reports (d4380674-2627-4f06-a351-173869e82fbe)]