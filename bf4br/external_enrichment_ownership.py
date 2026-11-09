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

[executed on device: reports (d4380674-2627-4f06-a351-173869e82fbe)]