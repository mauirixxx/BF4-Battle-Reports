"""Complete HTTP workflow against bf4br_external_api_test only.

Run after integration_external_enrichment_postgres.py seeds the scratch fixture.
No production database, listener or Battlelog traffic.
"""
from contextlib import contextmanager
import hashlib
from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient

from bf4br.external_enrichment_api import app
from bf4br.external_enrichment_selection import Candidate

DSN = 'dbname=bf4br_external_api_test user=postgres'

@contextmanager
def scratch_db():
    with psycopg.connect(DSN, autocommit=True) as conn:
        yield conn


def check(response, expected):
    assert response.status_code == expected, (response.status_code, response.text)
    return response.json()


def main():
    # Add a separate player so this tests a genuinely new batch, not a replay.
    with scratch_db() as conn, conn.transaction(), conn.cursor() as cur:
        cur.execute('''INSERT INTO players(platform,persona_id,current_name,
            current_name_observed_at,earliest_report_at,latest_report_at)
            VALUES (32,987654322,'http-test',now(),now(),now()) RETURNING id''')
        player_id = cur.fetchone()[0]
        cur.execute('INSERT INTO bf4br_external_workers(worker_id,key_sha256) VALUES (%s,%s)', ('http-worker',hashlib.sha256(b'http-secret').hexdigest()))
        cur.execute('SELECT id FROM servers LIMIT 1')
        server_id = cur.fetchone()[0]
        for report_id in (2001, 2002, 2003):
            cur.execute('''INSERT INTO battle_reports
                (platform,battlelog_report_id,server_id,report_timestamp,collected_at)
                VALUES (32,%s,%s,now(),now()) RETURNING id''', (report_id,server_id))
            cur.execute('''INSERT INTO report_players(report_id,player_id,player_name_observed)
                VALUES (%s,%s,'http-test')''', (cur.fetchone()[0],player_id))
    with patch('bf4br.external_enrichment_api.database', scratch_db), \
         patch('bf4br.external_enrichment_api.random_candidate',
               return_value=Candidate(32,987654322,(2003,2002,2001))):
        with TestClient(app) as client:
            headers = {'Authorization':'Bearer http-secret'}
            claimed = check(client.post('/api/v1/work/claim',headers=headers),200)
            assert claimed['platform']==32 and claimed['persona_id']==987654322,claimed
            assert len(claimed['reports'])==3,claimed
            batch_id = claimed['batch_id']
            items = claimed['reports']
            def action(item):
                return {'batch_id':batch_id,'platform':32,'persona_id':987654322,
                        'report_id':item['report_id'],'token':item['token']}
            first, second, third = items
            check(client.post('/api/v1/work/renew',json=action(first),headers=headers),200)
            payload={'id':first['report_id'],'platform':32,
                     'players':{'987654322':{}},
                     'playerReport':{'personaId':987654322,'stats':{}}}
            saved = check(client.post('/api/v1/enrichment',json={**action(first),'payload':payload},headers=headers),200)
            assert saved == {'stored':True,'already_stored':False},saved
            repeated = check(client.post('/api/v1/enrichment',json={**action(first),'payload':payload},headers=headers),200)
            assert repeated['already_stored'] is True
            check(client.post('/api/v1/work/complete',json={'batch_id':batch_id},headers=headers),409)
            failed = check(client.post('/api/v1/work/fail',json={**action(second),
                'reason':'synthetic Battlelog error','retry_seconds':60},headers=headers),200)
            assert failed['released'] is True
            check(client.post('/api/v1/work/renew',json=action(second),headers=headers),409)
            check(client.post('/api/v1/work/fail',json={**action(third),
                'reason':'synthetic retry','retry_seconds':60},headers=headers),200)
            finished = check(client.post('/api/v1/work/complete',json={'batch_id':batch_id},headers=headers),200)
            assert finished['completed'] is True
            repeated = check(client.post('/api/v1/enrichment',json={**action(first),'payload':payload},headers=headers),200)
            assert repeated['already_stored'] is True
            check(client.post('/api/v1/work/claim',headers=headers),429)
    with scratch_db() as conn, conn.cursor() as cur:
        cur.execute('''SELECT state FROM bf4br_external_batches WHERE batch_id=%s''',(batch_id,))
        assert cur.fetchone()[0]=='completed'
        cur.execute('''SELECT state,count(*) FROM bf4br_detail_players
            WHERE platform=32 AND persona_id=987654322 GROUP BY state''')
        assert dict(cur.fetchall())=={'done':1,'retry':2}
        cur.execute('''SELECT count(*) FROM bf4br_player_report_raw
            WHERE platform=32 AND persona_id=987654322''')
        assert cur.fetchone()[0]==1
    print('PASS: HTTP claim 3, renew, fresh upload, duplicate ACK, incomplete finish 409, fail/retry, lost lease 409, complete, post-complete ACK, cooldown 429, DB state')

if __name__=='__main__':
    main()

[executed on device: reports (d4380674-2627-4f06-a351-173869e82fbe)]