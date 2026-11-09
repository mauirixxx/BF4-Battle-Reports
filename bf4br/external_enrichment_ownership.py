"""Worker-owned fenced mutations for the opt-in external API."""
from bf4br.detail_queue import save_player, renew_player, retry_player


class OwnershipLost(Exception):
    pass


def owned_job(conn, job, token, worker):
    """Lock and verify the exact leased job before invoking existing operations.

    Caller must hold a transaction through the subsequent mutation. The row
    lock prevents reassignment between ownership check and persistence.
    """
    with conn.cursor() as cur:
        cur.execute('''SELECT 1 FROM bf4br_detail_players
            WHERE platform=%s AND battlelog_report_id=%s AND persona_id=%s
              AND lease_token=%s AND lease_owner=%s AND state='leased'
              AND lease_until>now() FOR UPDATE''', (*job, token, worker))
        if not cur.fetchone():
            raise OwnershipLost('lease expired or worker ownership changed')


def renew_owned(conn, job, token, worker, seconds=900):
    with conn.transaction():
        owned_job(conn, job, token, worker)
        if not renew_player(conn, job, token, seconds):
            raise OwnershipLost('lease lost during renewal')


def save_owned(conn, job, token, worker, payload):
    with conn.transaction():
        owned_job(conn, job, token, worker)
        save_player(conn, job, token, payload)


def retry_owned(conn, job, token, worker, reason, delay):
    with conn.transaction():
        owned_job(conn, job, token, worker)
        if not retry_player(conn, job, token, reason, delay):
            raise OwnershipLost('lease lost during release')


def acknowledge_saved(conn, job, token, worker, batch_id, payload):
    """Acknowledge an identical persisted response after a lost HTTP ACK.

    The batch may be completed, but never expired. The exact historical
    batch token must match, the job must still be done, and the stored JSON
    must equal the resubmitted JSON. Caller holds a transaction.
    """
    import json
    platform, rid, persona = job
    if not isinstance(payload, dict) or payload.get('id') != rid or payload.get('platform') != platform:
        raise ValueError('player report identity mismatch')
    if not isinstance(payload.get('players'), dict) or str(persona) not in payload['players']:
        raise ValueError('persona missing from report roster')
    detail = payload.get('playerReport')
    if not isinstance(detail, dict) or not isinstance(detail.get('stats'), dict) or str(detail.get('personaId')) != str(persona):
        raise ValueError('invalid playerReport identity or stats')
    with conn.cursor() as cur:
        # Same lock order as batch lifecycle operations.
        cur.execute('''SELECT 1 FROM bf4br_external_workers
            WHERE worker_id=%s AND enabled FOR UPDATE''', (worker,))
        if not cur.fetchone():
            raise OwnershipLost('unknown or disabled worker')
        cur.execute('''SELECT 1 FROM bf4br_external_batches b
            JOIN bf4br_external_batch_items i ON i.batch_id=b.batch_id
            JOIN bf4br_detail_players p ON p.platform=i.platform AND p.battlelog_report_id=i.battlelog_report_id AND p.persona_id=i.persona_id
            JOIN bf4br_player_report_raw r ON r.platform=i.platform AND r.battlelog_report_id=i.battlelog_report_id AND r.persona_id=i.persona_id
            WHERE b.batch_id=%s AND b.worker_id=%s
              AND b.state IN ('active','completed')
              AND i.platform=%s AND i.battlelog_report_id=%s AND i.persona_id=%s
              AND i.lease_token=%s AND p.state='done'
              AND r.raw_response=%s::jsonb
            FOR UPDATE OF p''', (batch_id,worker,*job,token,json.dumps(payload)))
        return cur.fetchone() is not None

[executed on device: reports (d4380674-2627-4f06-a351-173869e82fbe)]