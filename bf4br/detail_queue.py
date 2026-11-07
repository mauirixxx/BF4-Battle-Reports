"""BF4BR v2 detail enrichment queue. Not enabled by existing supervisors.

All report activation and completion transitions serialize on the same transaction
advisory lock. Player claims are fenced by per-persona UUID lease tokens.
"""
import uuid

LOCK_KEY = 2040007


def seed_reports(conn, limit=500):
    """Seed newest imported generic reports; never mutate generic records."""
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO bf4br_detail_reports(platform,battlelog_report_id,report_timestamp)
                SELECT r.platform,r.battlelog_report_id,r.report_timestamp
                FROM battle_reports r
                WHERE NOT EXISTS (
                    SELECT 1 FROM bf4br_detail_reports d
                    WHERE d.platform=r.platform AND d.battlelog_report_id=r.battlelog_report_id)
                ORDER BY r.report_timestamp DESC,r.platform,r.battlelog_report_id DESC
                LIMIT %s ON CONFLICT DO NOTHING
            """, (limit,))
            return cur.rowcount


def activate(conn):
    """Globally select a report only after the prior active report is resolved."""
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_KEY,))
            cur.execute("""SELECT platform,battlelog_report_id FROM bf4br_detail_reports
                WHERE state='active' LIMIT 1""")
            active=cur.fetchone()
            if active:
                return active
            cur.execute("""SELECT platform,battlelog_report_id FROM bf4br_detail_reports
                WHERE state IN ('pending','deferred') AND retry_after<=now()
                ORDER BY report_timestamp DESC,platform,battlelog_report_id DESC
                FOR UPDATE SKIP LOCKED LIMIT 1""")
            report=cur.fetchone()
            if not report:
                return None
            platform,rid=report
            # Roster comes from normalized imported generic reports, not a
            # guessed participant list or a previous match.
            cur.execute("""INSERT INTO bf4br_detail_players(platform,battlelog_report_id,persona_id)
                SELECT r.platform,r.battlelog_report_id,p.persona_id
                FROM battle_reports r
                JOIN report_players rp ON rp.report_id=r.id
                JOIN players p ON p.id=rp.player_id AND p.platform=r.platform
                WHERE r.platform=%s AND r.battlelog_report_id=%s
                ON CONFLICT DO NOTHING""",(platform,rid))
            cur.execute("""SELECT count(*) FROM bf4br_detail_players
                WHERE platform=%s AND battlelog_report_id=%s""",(platform,rid))
            expected=cur.fetchone()[0]
            if expected==0:
                cur.execute("""UPDATE bf4br_detail_reports SET state='deferred',
                    retry_after=now()+interval '1 day',last_error='empty normalized roster',
                    updated_at=now() WHERE platform=%s AND battlelog_report_id=%s""",report)
                return None
            cur.execute("""UPDATE bf4br_detail_reports
                SET state='active',expected_players=%s,activated_at=now(),
                    last_error=NULL,updated_at=now()
                WHERE platform=%s AND battlelog_report_id=%s""",(expected,*report))
            return report


def claim_player(conn, worker, lease_seconds=120):
    token=uuid.uuid4()
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("""WITH candidate AS (
                SELECT p.platform,p.battlelog_report_id,p.persona_id
                FROM bf4br_detail_players p
                JOIN bf4br_detail_reports r USING(platform,battlelog_report_id)
                WHERE r.state='active'
                  AND ((p.state IN ('ready','retry') AND p.next_attempt_at<=now())
                    OR (p.state='leased' AND p.lease_until<now()))
                ORDER BY p.persona_id FOR UPDATE OF p SKIP LOCKED LIMIT 1
            ) UPDATE bf4br_detail_players p
              SET state='leased',lease_owner=%s,lease_token=%s,
                  lease_until=now()+(%s * interval '1 second'),updated_at=now()
              FROM candidate c
              WHERE p.platform=c.platform AND p.battlelog_report_id=c.battlelog_report_id
                AND p.persona_id=c.persona_id
              RETURNING p.platform,p.battlelog_report_id,p.persona_id
            """,(worker,token,lease_seconds))
            row=cur.fetchone()
            return (row,token) if row else None


def renew_player(conn,job,token,seconds=120):
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("""UPDATE bf4br_detail_players
                SET lease_until=now()+(%s * interval '1 second'),updated_at=now()
                WHERE platform=%s AND battlelog_report_id=%s AND persona_id=%s
                  AND state='leased' AND lease_token=%s AND lease_until>now()
            """,(seconds,*job,token))
            return cur.rowcount==1


def save_player(conn,job,token,payload):
    platform,rid,persona=job
    if not isinstance(payload,dict) or int(payload.get('id',0))!=rid or int(payload.get('platform',0))!=platform:
        raise ValueError('player report identity mismatch')
    if str(persona) not in payload.get('players',{}):
        raise ValueError('persona missing from report roster')
    detail=payload.get('playerReport')
    if not isinstance(detail,dict) or not isinstance(detail.get('stats'),dict):
        raise ValueError('missing playerReport.stats')
    import json
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("""SELECT 1 FROM bf4br_detail_players
                WHERE platform=%s AND battlelog_report_id=%s AND persona_id=%s
                  AND state='leased' AND lease_token=%s AND lease_until>now()
                FOR UPDATE""",(*job,token))
            if not cur.fetchone():
                raise RuntimeError('player lease lost')
            cur.execute("""INSERT INTO bf4br_player_report_raw
                (platform,battlelog_report_id,persona_id,raw_response)
                VALUES (%s,%s,%s,%s::jsonb)
                ON CONFLICT (platform,battlelog_report_id,persona_id) DO NOTHING
            """,(*job,json.dumps(payload)))
            cur.execute("""UPDATE bf4br_detail_players SET state='done',
                lease_owner=NULL,lease_token=NULL,lease_until=NULL,
                last_error=NULL,updated_at=now()
                WHERE platform=%s AND battlelog_report_id=%s AND persona_id=%s
                AND lease_token=%s""",(*job,token))
            if cur.rowcount!=1:
                raise RuntimeError('player lease lost at completion')


def retry_player(conn,job,token,error,delay_seconds=1200):
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("""UPDATE bf4br_detail_players SET state='retry',
                lease_owner=NULL,lease_token=NULL,lease_until=NULL,
                next_attempt_at=now()+(%s * interval '1 second'),
                failures=failures+1,last_error=%s,updated_at=now()
                WHERE platform=%s AND battlelog_report_id=%s AND persona_id=%s
                AND state='leased' AND lease_token=%s AND lease_until>now()
            """,(delay_seconds,str(error)[:500],*job,token))
            return cur.rowcount==1


def settle_report(conn, defer_seconds=1200):
    """Atomic complete-or-defer decision. A report is never partly complete."""
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s)",(LOCK_KEY,))
            cur.execute("""SELECT platform,battlelog_report_id,expected_players
                FROM bf4br_detail_reports WHERE state='active' FOR UPDATE""")
            report=cur.fetchone()
            if not report:
                return None
            platform,rid,expected=report
            cur.execute("""SELECT count(*) FILTER (WHERE p.state='done' AND a.persona_id IS NOT NULL),
                    count(*) FILTER (WHERE p.state='leased' AND p.lease_until>now()),
                    count(*) FILTER (WHERE p.state IN ('ready','retry') AND p.next_attempt_at<=now()
                                      OR p.state='leased' AND p.lease_until<=now()),
                    count(*)
                FROM bf4br_detail_players p
                LEFT JOIN bf4br_player_report_raw a
                  USING(platform,battlelog_report_id,persona_id)
                WHERE p.platform=%s AND p.battlelog_report_id=%s""",(platform,rid))
            done,inflight,eligible,total=cur.fetchone()
            if total!=expected:
                raise RuntimeError('roster changed during report enrichment')
            if done==expected:
                cur.execute("""UPDATE bf4br_detail_reports SET state='complete',
                    completed_at=now(),updated_at=now()
                    WHERE platform=%s AND battlelog_report_id=%s""",(platform,rid))
                return 'complete'
            if inflight or eligible:
                return 'working'
            cur.execute("""UPDATE bf4br_detail_reports SET state='deferred',
                retry_after=now()+(%s * interval '1 second'),
                last_error='player retries pending',updated_at=now()
                WHERE platform=%s AND battlelog_report_id=%s""",(defer_seconds,platform,rid))
            return 'deferred'
