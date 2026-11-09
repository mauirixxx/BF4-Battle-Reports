"""Scratch-only lease-expiry/recovery and report-coordinator compatibility tests."""
import psycopg
from bf4br.external_enrichment_batch import start_batch, finish_batch, BatchBusy
from bf4br.external_enrichment_claim import claim_player_batch
from bf4br.detail_queue import activate, claim_player

DSN='dbname=bf4br_external_api_test user=postgres'

def connect(): return psycopg.connect(DSN,autocommit=True)

def main():
    # Requires the seeded fixture from integration_external_enrichment_postgres.py.
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE bf4br_external_workers SET cooldown_until=now()-interval '1 second' WHERE worker_id='a'")
            cur.execute("UPDATE bf4br_external_workers SET cooldown_until=now()-interval '1 second' WHERE worker_id='b'")
            cur.execute("SELECT id FROM players WHERE platform=32 AND persona_id=987654321")
            player=cur.fetchone()[0]
        # Mark an already-created report active through the real coordinator.
        activated=activate(conn,max_active=2)
        if activated:
            with conn.cursor() as cur:
                cur.execute("SELECT expected_players FROM bf4br_detail_reports WHERE platform=%s AND battlelog_report_id=%s",activated)
                expected=cur.fetchone()[0]
                cur.execute("SELECT count(*) FROM bf4br_detail_players WHERE platform=%s AND battlelog_report_id=%s",activated)
                assert cur.fetchone()[0]==expected
        result=start_batch(conn,'b',lambda db: claim_player_batch(db,player,'b'))
        assert result and result!=('cooldown',None),result
        batch,reservation=result
        assert activated is None or activated[1] not in reservation.report_ids
        # Simulate a worker dying: all of its leases expire without renewal.
        with conn.cursor() as cur:
            cur.execute("UPDATE bf4br_detail_players SET lease_until=now()-interval '1 second' WHERE lease_owner='b' AND state='leased'")
        # First recovery request expires the batch and starts a 61s cooldown.
        response=start_batch(conn,'b',lambda db: (_ for _ in ()).throw(AssertionError('claimed too early')))
        assert response==('cooldown',None),response
        with conn.cursor() as cur:
            cur.execute('SELECT state FROM bf4br_external_batches WHERE batch_id=%s',(batch,))
            assert cur.fetchone()[0]=='expired'
            cur.execute('SELECT cooldown_until>now(),active_batch_id IS NULL FROM bf4br_external_workers WHERE worker_id=%s',('b',))
            assert cur.fetchone()==(True,True)
            cur.execute("UPDATE bf4br_external_workers SET cooldown_until=now()-interval '1 second' WHERE worker_id='b'")
        replacement=start_batch(conn,'b',lambda db: claim_player_batch(db,player,'b'))
        assert replacement and replacement!=('cooldown',None)
        assert replacement[0]!=batch
        assert set(replacement[1].report_ids).intersection(reservation.report_ids)
    print('PASS: coordinator active-roster invariant, expired lease crash recovery, durable cooldown, and reclaimed work')

if __name__=='__main__': main()

[executed on device: reports (d4380674-2627-4f06-a351-173869e82fbe)]