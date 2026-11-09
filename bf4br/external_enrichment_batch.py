"""Durable batch lifecycle primitives for the opt-in external enrichment API.

Requires migration 0009. Never call on production before migration rollout.
"""
from uuid import uuid4
from datetime import datetime, timezone


class BatchBusy(Exception):
    pass


class CooldownActive(Exception):
    pass


def start_batch(conn, worker, reserve):
    """Lock worker and reserve jobs in the same outer transaction.

    `reserve` is a callback taking the same connection; it must return a
    Reservation or None and must not commit independently.
    """
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute('''SELECT active_batch_id FROM bf4br_external_workers
                WHERE worker_id=%s AND enabled FOR UPDATE''', (worker,))
            row = cur.fetchone()
            if row is None:
                raise PermissionError('unknown or disabled worker')
            active_batch = row[0]
            if active_batch is not None:
                cur.execute('''SELECT state FROM bf4br_external_batches
                    WHERE batch_id=%s''', (active_batch,))
                state = cur.fetchone()
                if state and state[0] == 'active':
                    # Reclaim only when every outstanding token has expired.
                    cur.execute('''SELECT 1 FROM bf4br_external_batch_items item
                        JOIN bf4br_detail_players job USING(platform,battlelog_report_id,persona_id)
                        WHERE item.batch_id=%s AND job.state='leased'
                          AND job.lease_token=item.lease_token
                          AND job.lease_until>now() LIMIT 1''', (active_batch,))
                    if cur.fetchone():
                        raise BatchBusy('worker already owns an active batch')
                    cur.execute('''UPDATE bf4br_external_batches SET state='expired',updated_at=now()
                        WHERE batch_id=%s AND state='active' ''', (active_batch,))
                    cur.execute('''UPDATE bf4br_external_workers SET active_batch_id=NULL,
                        cooldown_until=GREATEST(cooldown_until,now()+interval '61 seconds'),
                        updated_at=now() WHERE worker_id=%s''', (worker,))
            cur.execute('''SELECT cooldown_until>now() FROM bf4br_external_workers
                WHERE worker_id=%s''', (worker,))
            if cur.fetchone()[0]:
                # Return sentinel so expired-batch cleanup commits; caller
                # reports cooldown after the transaction has completed.
                return ('cooldown', None)
            reservation = reserve(conn)
            if reservation is None:
                return None
            batch_id = uuid4()
            cur.execute('''INSERT INTO bf4br_external_batches
                (batch_id,worker_id,platform,persona_id) VALUES (%s,%s,%s,%s)''',
                (batch_id,worker,reservation.platform,reservation.persona_id))
            for rid,token in zip(reservation.report_ids,reservation.tokens):
                cur.execute('''INSERT INTO bf4br_external_batch_items
                    (batch_id,platform,battlelog_report_id,persona_id,lease_token)
                    VALUES (%s,%s,%s,%s,%s)''',
                    (batch_id,reservation.platform,rid,reservation.persona_id,token))
            cur.execute('''UPDATE bf4br_external_workers
                SET active_batch_id=%s,updated_at=now() WHERE worker_id=%s''',
                (batch_id,worker))
            return batch_id,reservation


def finish_batch(conn, worker, batch_id, *, cooldown_seconds=61):
    """Close a batch only when all items are settled, then set cooldown.

    Cooldown starts at completion acknowledgement; this is conservative
    relative to the worker's last Battlelog request, never shorter.
    """
    if cooldown_seconds < 61:
        raise ValueError('cooldown must be at least 61 seconds')
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute('''SELECT active_batch_id FROM bf4br_external_workers
                WHERE worker_id=%s AND enabled FOR UPDATE''', (worker,))
            row=cur.fetchone()
            if not row or row[0]!=batch_id:
                raise BatchBusy('batch not owned by worker')
            cur.execute('''SELECT 1 FROM bf4br_external_batch_items item
                JOIN bf4br_detail_players job USING(platform,battlelog_report_id,persona_id)
                WHERE item.batch_id=%s AND job.state='leased'
                  AND job.lease_token=item.lease_token
                  AND job.lease_until>now() LIMIT 1''', (batch_id,))
            if cur.fetchone():
                raise BatchBusy('batch has outstanding leased jobs')
            cur.execute('''UPDATE bf4br_external_batches SET state='completed',
                completed_at=now(),updated_at=now()
                WHERE batch_id=%s AND worker_id=%s AND state='active' ''', (batch_id,worker))
            if cur.rowcount!=1:
                raise BatchBusy('batch is not active')
            cur.execute('''UPDATE bf4br_external_workers
                SET active_batch_id=NULL,
                    cooldown_until=GREATEST(cooldown_until,
                       now()+(%s * interval '1 second')),
                    updated_at=now() WHERE worker_id=%s''', (cooldown_seconds,worker))


def batch_item_owned(conn, worker, batch_id, job, token):
    """Require the item to belong to the worker's active durable batch."""
    with conn.cursor() as cur:
        cur.execute('''SELECT 1 FROM bf4br_external_workers w
            JOIN bf4br_external_batches b ON b.batch_id=w.active_batch_id
            JOIN bf4br_external_batch_items i ON i.batch_id=b.batch_id
            WHERE w.worker_id=%s AND w.enabled AND b.worker_id=w.worker_id
              AND b.state='active' AND b.batch_id=%s
              AND i.platform=%s AND i.battlelog_report_id=%s
              AND i.persona_id=%s AND i.lease_token=%s''', (worker,batch_id,*job,token))
        return cur.fetchone() is not None

[executed on device: reports (d4380674-2627-4f06-a351-173869e82fbe)]