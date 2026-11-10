#!/usr/bin/env python3
"""Import BF4 probe player JSONs without interfering with live enrichment leases.

Defaults to read-only dry-run. --apply explicitly enables bounded writes.
The original /var/tmp/bf4br-probe-import.py remains untouched.
"""
import argparse
import collections
import json
import logging
from pathlib import Path

import psycopg

LOG = logging.getLogger('bf4br-probe-import')


def identity(path):
    try:
        platform, report = map(int, path.parent.name.split('_', 1))
        persona = int(path.stem.removeprefix('player_'))
        if path.stem != f'player_{persona}' or platform not in (1, 32, 64) or min(report, persona) <= 0:
            raise ValueError('invalid identity')
        return platform, report, persona
    except (ValueError, AttributeError) as exc:
        raise ValueError('invalid probe file path') from exc


def load_validated(path):
    job = identity(path)
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError('JSON is not an object')
    platform, report, persona = job
    roster, detail = payload.get('players'), payload.get('playerReport')
    if (str(payload.get('id')) != str(report)
        or str(payload.get('platform')) != str(platform)
        or not isinstance(roster, dict) or str(persona) not in roster
        or not isinstance(detail, dict) or not isinstance(detail.get('stats'), dict)
        or str(detail.get('personaId')) != str(persona)):
        raise ValueError('player report identity/statistics mismatch')
    return job, payload


def import_one(conn, job, payload, apply):
    platform, report, persona = job
    with conn.transaction():
        with conn.cursor() as cur:
            # Lock the parent first, matching the queue's parent-before-player order.
            cur.execute('''SELECT state FROM bf4br_detail_reports
                WHERE platform=%s AND battlelog_report_id=%s ''' + ('FOR UPDATE' if apply else ''), (platform, report))
            parent = cur.fetchone()
            if not parent:
                return 'unknown_report'
            if parent[0] == 'complete':
                return 'report_complete'
            # Only import players in the *normalized* report roster, not merely
            # those named in the downloaded payload.
            cur.execute('''SELECT 1 FROM battle_reports r
                JOIN report_players rp ON rp.report_id=r.id
                JOIN players p ON p.id=rp.player_id AND p.platform=r.platform
                WHERE r.platform=%s AND r.battlelog_report_id=%s
                  AND p.persona_id=%s''', job)
            if not cur.fetchone():
                return 'not_in_normalized_roster'
            cur.execute('''SELECT state FROM bf4br_detail_players
                WHERE platform=%s AND battlelog_report_id=%s AND persona_id=%s
                ''' + ('FOR UPDATE' if apply else ''), job)
            existing = cur.fetchone()
            if existing and existing[0] == 'leased':
                return 'leased_skip'
            cur.execute('''SELECT 1 FROM bf4br_player_report_raw
                WHERE platform=%s AND battlelog_report_id=%s AND persona_id=%s''', job)
            raw_exists = cur.fetchone() is not None
            if existing and existing[0] == 'done' and raw_exists:
                return 'already_done'
            if existing and existing[0] == 'done':
                return 'done_missing_raw_review'
            if raw_exists:
                # An inconsistent queue/raw pair is not repaired blindly.
                return 'raw_exists_review'
            if not apply:
                return 'would_import'
            if existing is None:
                cur.execute('''INSERT INTO bf4br_detail_players
                    (platform,battlelog_report_id,persona_id,state)
                    VALUES (%s,%s,%s,'done') ON CONFLICT DO NOTHING''', job)
                if cur.rowcount != 1:
                    raise RuntimeError('player queue insert conflict')
            else:
                cur.execute('''UPDATE bf4br_detail_players SET state='done',
                    lease_owner=NULL,lease_token=NULL,lease_until=NULL,
                    last_error=NULL,updated_at=now()
                    WHERE platform=%s AND battlelog_report_id=%s AND persona_id=%s
                    AND state IN ('ready','retry')''', job)
                if cur.rowcount != 1:
                    raise RuntimeError('player queue state changed')
            cur.execute('''INSERT INTO bf4br_player_report_raw
                (platform,battlelog_report_id,persona_id,raw_response)
                VALUES (%s,%s,%s,%s::jsonb) ON CONFLICT DO NOTHING''',
                (*job, json.dumps(payload)))
            if cur.rowcount != 1:
                raise RuntimeError('raw record insertion conflict')
            return 'imported'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('/var/tmp/bf4br-probe-staging'))
    parser.add_argument('--dsn', default='dbname=bf4_battle_reports user=postgres')
    parser.add_argument('--apply', action='store_true', help='Write validated data; default is dry-run')
    parser.add_argument('--limit', type=int, default=0, help='Limit files processed (0 = all)')
    parser.add_argument('--progress-every', type=int, default=1000)
    args = parser.parse_args()
    if not args.root.is_dir() or args.limit < 0 or args.progress_every < 1:
        parser.error('root must exist, limit must be nonnegative, progress-every must be positive')
    counts = collections.Counter()
    print(f'Mode: {"APPLY" if args.apply else "DRY RUN"}; root: {args.root}', flush=True)
    with psycopg.connect(args.dsn, autocommit=True) as conn:
        for index, path in enumerate(args.root.rglob('player_*.json'), 1):
            if args.limit and index > args.limit:
                break
            try:
                job, payload = load_validated(path)
                result = import_one(conn, job, payload, args.apply)
            except (OSError, ValueError, json.JSONDecodeError):
                result = 'invalid_file'
            except psycopg.Error:
                LOG.exception('Database error for %s; stopping', path)
                raise
            counts[result] += 1
            if index % args.progress_every == 0:
                print(f'Processed {index}: {dict(counts)}', flush=True)
    print(f'FINAL: {dict(counts)}', flush=True)


if __name__ == '__main__':
    main()