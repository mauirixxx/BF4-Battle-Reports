"""Scratch-only persistent 429 test, run after integration_external_enrichment_recovery."""
import psycopg
from bf4br.external_enrichment_batch import record_rate_limit, start_batch, BatchBusy
DSN='dbname=bf4br_external_api_test user=postgres'

def main():
    with psycopg.connect(DSN,autocommit=True) as conn:
        with conn.cursor() as c:
            c.execute("SELECT active_batch_id FROM bf4br_external_workers WHERE worker_id='b'")
            batch=c.fetchone()[0]
        assert batch is not None
        record_rate_limit(conn,'b',batch,retry_after_seconds=300)
        with conn.cursor() as c:
            c.execute("SELECT cooldown_until>now()+interval '290 seconds' FROM bf4br_external_workers WHERE worker_id='b'")
            assert c.fetchone()[0]
        try:
            record_rate_limit(conn,'a',batch,retry_after_seconds=300)
        except BatchBusy: pass
        else: raise AssertionError('foreign worker accepted')
        with conn.cursor() as c:
            c.execute("UPDATE bf4br_detail_players SET lease_until=now()-interval '1 second' WHERE lease_owner='b' AND state='leased'")
        result=start_batch(conn,'b',lambda db: (_ for _ in ()).throw(AssertionError('bypassed cooldown')))
        assert result==('cooldown',None)
        with conn.cursor() as c:
            c.execute("SELECT cooldown_until>now()+interval '280 seconds' FROM bf4br_external_workers WHERE worker_id='b'")
            assert c.fetchone()[0], 'crash recovery shortened 429 cooldown'
    print('PASS: durable 300s 429, foreign-worker rejection, crash recovery preserves longer cooldown')
if __name__=='__main__': main()

[executed on device: reports (d4380674-2627-4f06-a351-173869e82fbe)]