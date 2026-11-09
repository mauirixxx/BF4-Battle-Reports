"""Scratch-only HTTP retry acknowledgement test; run after base integration fixture."""
import psycopg
from bf4br.external_enrichment_ownership import acknowledge_saved, OwnershipLost
from bf4br.external_enrichment_batch import BatchBusy
DSN='dbname=bf4br_external_api_test user=postgres'

def main():
    with psycopg.connect(DSN,autocommit=True) as conn:
        with conn.cursor() as c:
            c.execute('''SELECT b.batch_id,b.worker_id,i.platform,i.battlelog_report_id,
                i.persona_id,i.lease_token,r.raw_response
                FROM bf4br_external_batches b
                JOIN bf4br_external_batch_items i ON i.batch_id=b.batch_id
                JOIN bf4br_player_report_raw r ON r.platform=i.platform AND r.battlelog_report_id=i.battlelog_report_id AND r.persona_id=i.persona_id
                WHERE b.state='completed' LIMIT 1''')
            batch,worker,platform,rid,persona,token,payload=c.fetchone()
        job=(platform,rid,persona)
        with conn.transaction():
            assert acknowledge_saved(conn,job,token,worker,batch,payload)
        altered={**payload,'new-field':'different'}
        with conn.transaction():
            assert not acknowledge_saved(conn,job,token,worker,batch,altered)
        with conn.transaction():
            try:
                assert not acknowledge_saved(conn,job,token,'wrong-worker',batch,payload)
            except OwnershipLost:
                pass
        with conn.cursor() as c:
            c.execute('SELECT count(*) FROM bf4br_player_report_raw')
            assert c.fetchone()[0]==1
    print('PASS: completed-batch duplicate ACK, changed-payload rejection, foreign-worker rejection, no duplicate raw rows')
if __name__=='__main__': main()

[executed on device: reports (d4380674-2627-4f06-a351-173869e82fbe)]