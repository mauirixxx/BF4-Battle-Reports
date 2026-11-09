"""Read-only candidate discovery for the opt-in player-centric API.

No reservation is made here. The claim endpoint MUST atomically reserve all
returned jobs before exposing them to a worker; this module is not a claim API.
"""
from dataclasses import dataclass
from secrets import randbelow

MAX_REPORTS = 40


@dataclass(frozen=True)
class Candidate:
    platform: int
    persona_id: int
    report_ids: tuple[int, ...]


def eligible_reports(conn, player_id: int, *, limit: int = MAX_REPORTS) -> tuple[int, ...]:
    """Newest unenriched, unleased and retry-eligible reports for one player.

    Uses the normalized report_players membership index. The raw table is the
    authoritative durable duplicate marker, regardless of job-state drift.
    """
    if player_id <= 0 or not 1 <= limit <= MAX_REPORTS:
        raise ValueError('invalid player or limit')
    with conn.cursor() as cur:
        cur.execute('''
            SELECT r.battlelog_report_id
            FROM report_players rp
            JOIN battle_reports r ON r.id=rp.report_id
            JOIN players p ON p.id=rp.player_id AND p.platform=r.platform
            LEFT JOIN bf4br_player_report_raw raw
              ON raw.platform=r.platform
             AND raw.battlelog_report_id=r.battlelog_report_id
             AND raw.persona_id=p.persona_id
            LEFT JOIN bf4br_detail_players job
              ON job.platform=r.platform
             AND job.battlelog_report_id=r.battlelog_report_id
             AND job.persona_id=p.persona_id
            WHERE rp.player_id=%s
              AND raw.persona_id IS NULL
              AND (job.persona_id IS NULL OR
                   (job.state IN ('ready','retry') AND job.next_attempt_at<=now()) OR
                   (job.state='leased' AND job.lease_until<=now()))
            ORDER BY r.report_timestamp DESC,r.battlelog_report_id DESC
            LIMIT %s
        ''', (player_id, limit))
        return tuple(row[0] for row in cur.fetchall())


def random_candidate(conn, *, attempts: int = 24, limit: int = MAX_REPORTS) -> Candidate | None:
    """Bounded random ID seeks; never ORDER BY random() over the player table.

    A returned candidate is advisory, NOT reserved. A later transactional
    claim must recheck eligibility and fence each player/report job.
    """
    if not 1 <= attempts <= 128 or not 1 <= limit <= MAX_REPORTS:
        raise ValueError('invalid selection bounds')
    with conn.cursor() as cur:
        cur.execute('SELECT min(id),max(id) FROM players')
        low, high = cur.fetchone()
    if low is None:
        return None
    for _ in range(attempts):
        pivot = low + randbelow(high - low + 1)
        with conn.cursor() as cur:
            cur.execute('''SELECT id,platform,persona_id FROM players
                WHERE id >= %s ORDER BY id LIMIT 1''', (pivot,))
            row = cur.fetchone()
            if row is None:
                cur.execute('''SELECT id,platform,persona_id FROM players
                    ORDER BY id LIMIT 1''')
                row = cur.fetchone()
        if row is None:
            return None
        player_id, platform, persona_id = row
        reports = eligible_reports(conn, player_id, limit=limit)
        if reports:
            return Candidate(platform, persona_id, reports)
    return None

[executed on device: reports (d4380674-2627-4f06-a351-173869e82fbe)]