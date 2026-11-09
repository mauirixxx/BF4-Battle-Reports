"""Explicit scratch-only PostgreSQL integration test. Run as postgres OS user.

Never point at production; uses only bf4br_external_api_test.
"""
import hashlib
from concurrent.futures import ThreadPoolExecutor
import psycopg
from bf4br.external_enrichment_claim import claim_player_batch
from bf4br.external_enrichment_batch import start_batch, finish_batch, BatchBusy
from bf4br.external_enrichment_ownership import save_owned, retry_owned, OwnershipLost

DSN='dbname=bf4br_external_api_test user=postgres'

def connect(): return psycopg.connect(DSN,autocommit=True)

def main():
    with connect() as conn, conn.transaction():
        with conn.cursor() as c:
            c.execute("TRUNCATE bf4br_external_batch_items,bf4br_external_workers,bf4br_external_batches,bf4br_player_report_raw,bf4br_detail_players,bf4br_detail_reports,report_players,player_name_history,battle_reports,players,servers CASCADE")
            c.execute("INSERT INTO servers(server_guid,current_name) VALUES ('00000000-0000-0000-0000-000000000001','test') RETURNING id")
            server=c.fetchone()[0]
            c.execute("""INSERT INTO players(platform,persona_id,current_name,current_name_observed_at,earliest_report_at,latest_report_at)
                 VALUES (32,987654321,'test',now(),now(),now()) RETURNING id""")
            player=c.fetchone()[0]
            for rid in range(1001,1046):
                c.execute("""INSERT INTO battle_reports(platform,battlelog_report_id,server_id,report_timestamp,collected_at)
                    VALUES (32,%s,%s,now()-(%s*interval '1 minute'),now()) RETURNING id""",(rid,server,1046-rid))
                report=c.fetchone()[0]
                c.execute("INSERT INTO report_players(report_id,player_id,player_name_observed) VALUES (%s,%s,'test')",(report,player))
            for worker in ('a','b'):
                c.execute("INSERT INTO bf4br_external_workers(worker_id,key_sha256) VALUES (%s,%s)", (worker,hashlib.sha256(worker.encode()).hexdigest()))
    def reserve(worker):
        with connect() as conn:
            return start_batch(conn,worker,lambda db: claim_player_batch(db,player,worker))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(reserve,('a','b')))
    successes=[(worker,result) for worker,result in zip(('a','b'),results) if result and result!=('cooldown',None)]
    assert len(successes)==1, results
    worker,(batch_id,reservation)=successes[0]
    assert len(reservation.report_ids)==40, reservation
    assert reservation.report_ids[0]==1045 and reservation.report_ids[-1]==1006
    with connect() as conn:
        job=(32,reservation.report_ids[0],987654321)
        try:
            save_owned(conn,job,reservation.tokens[0],'wrong-worker',{})
        except OwnershipLost: pass
        else: raise AssertionError('wrong worker accepted')
        payload={'id':job[1],'platform':32,'players':{'987654321':{}},'playerReport':{'personaId':987654321,'stats':{}}}
        save_owned(conn,job,reservation.tokens[0],worker,payload)
        try:
            finish_batch(conn,worker,batch_id)
        except BatchBusy: pass
        else: raise AssertionError('finished with live jobs')
        for rid,token in zip(reservation.report_ids[1:],reservation.tokens[1:]):
            retry_owned(conn,(32,rid,987654321),token,worker,'test retry',60)
        finish_batch(conn,worker,batch_id)
        with conn.cursor() as c:
            c.execute('SELECT cooldown_until>now(),active_batch_id IS NULL FROM bf4br_external_workers WHERE worker_id=%s',(worker,))
            assert c.fetchone()==(True,True)
            c.execute('SELECT count(*) FROM bf4br_player_report_raw')
            assert c.fetchone()[0]==1
    print('PASS: 40 newest, concurrent worker exclusion, owner fencing, upload, incomplete batch refusal, retry release, completion, cooldown')

if __name__=='__main__': main()

[executed on device: reports (d4380674-2627-4f06-a351-173869e82fbe)]