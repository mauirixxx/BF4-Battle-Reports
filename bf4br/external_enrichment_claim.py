"""Atomic player-centric reservations using the existing v2 fenced job rows.

Development only. No public API or production scheduling changes.
"""
from dataclasses import dataclass
from uuid import uuid4
from bf4br.external_enrichment_selection import MAX_REPORTS


@dataclass(frozen=True)
class Reservation:
    platform: int
    persona_id: int
    report_ids: tuple[int, ...]
    tokens: tuple[str, ...]


def claim_player_batch(conn, player_id: int, worker: str, *, limit: int = MAX_REPORTS,
                       lease_seconds: int = 900) -> Reservation | None:
    """Lock a player, reserve up to 40 eligible jobs, commit all or nothing.

    Row locks serialize concurrent API batches for the same player. Existing
    report-centric workers use the same detail-player rows and lease tokens.
    A later API layer must authenticate worker and enforce pacing/cooldowns.
    """
    if player_id <= 0 or not worker or len(worker) > 128 or not 1 <= limit <= MAX_REPORTS:
        raise ValueError('invalid claim arguments')
    if not 120 <= lease_seconds <= 3600:
        raise ValueError('invalid lease duration')
    claimed = []
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute('SELECT platform,persona_id FROM players WHERE id=%s FOR UPDATE SKIP LOCKED', (player_id,))
            player = cur.fetchone()
            if not player:
                return None
            platform, persona = player
            # Overfetch is intentionally absent: this scans backward through
            # membership until it has 40 eligible jobs, not 40 recent rows.
            cur.execute('''
                SELECT r.battlelog_report_id,r.report_timestamp
                FROM report_players rp
                JOIN battle_reports r ON r.id=rp.report_id AND r.platform=%s
                WHERE rp.player_id=%s
                  -- Do not add roster rows to active/complete report-centric jobs:
                  -- their expected_players invariant would otherwise change.
                  AND NOT EXISTS (
                    SELECT 1 FROM bf4br_detail_reports parent
                    WHERE parent.platform=r.platform
                      AND parent.battlelog_report_id=r.battlelog_report_id
                      AND parent.state IN ('active','complete'))
                  AND NOT EXISTS (
                    SELECT 1 FROM bf4br_player_report_raw raw
                    WHERE raw.platform=r.platform
                      AND raw.battlelog_report_id=r.battlelog_report_id
                      AND raw.persona_id=%s)
                  AND NOT EXISTS (
                    SELECT 1 FROM bf4br_detail_players job
                    WHERE job.platform=r.platform
                      AND job.battlelog_report_id=r.battlelog_report_id
                      AND job.persona_id=%s
                      AND (job.state='done' OR
                           (job.state='leased' AND job.lease_until>now()) OR
                           (job.state IN ('ready','retry') AND job.next_attempt_at>now())))
                ORDER BY r.report_timestamp DESC,r.battlelog_report_id DESC
                LIMIT %s
            ''', (platform, player_id, persona, persona, limit))
            reports = cur.fetchall()
            for rid, stamp in reports:
                # Required parent FK: do not activate report-centric jobs.
                cur.execute('''INSERT INTO bf4br_detail_reports
                    (platform,battlelog_report_id,report_timestamp)
                    VALUES (%s,%s,%s) ON CONFLICT DO NOTHING''', (platform,rid,stamp))
                cur.execute('''INSERT INTO bf4br_detail_players
                    (platform,battlelog_report_id,persona_id)
                    VALUES (%s,%s,%s) ON CONFLICT DO NOTHING''', (platform,rid,persona))
                token = uuid4()
                cur.execute('''UPDATE bf4br_detail_players job
                    SET state='leased',lease_owner=%s,lease_token=%s,
                        lease_until=now()+(%s * interval '1 second'),updated_at=now()
                    WHERE platform=%s AND battlelog_report_id=%s AND persona_id=%s
                      AND NOT EXISTS (
                        SELECT 1 FROM bf4br_player_report_raw raw
                        WHERE raw.platform=job.platform
                          AND raw.battlelog_report_id=job.battlelog_report_id
                          AND raw.persona_id=job.persona_id)
                      AND ((state IN ('ready','retry') AND next_attempt_at<=now())
                        OR (state='leased' AND lease_until<=now()))
                    RETURNING battlelog_report_id''',
                    (worker,token,lease_seconds,platform,rid,persona))
                if cur.fetchone():
                    claimed.append((rid,str(token)))
    if not claimed:
        return None
    return Reservation(platform,persona,tuple(x[0] for x in claimed),tuple(x[1] for x in claimed))

[executed on device: reports (d4380674-2627-4f06-a351-173869e82fbe)]