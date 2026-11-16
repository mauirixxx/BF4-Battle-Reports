#!/usr/bin/env python3
"""Conservative, resumable streaming import of BF4 probe player JSON into BF4BR.

Requires PostgreSQL peer auth as postgres. Reads existing parent records; never
creates new report/player identities or alters leased jobs. Generic JSON is
counted but not imported by this program.
"""
import argparse
import collections
import json
import re
import subprocess
import tarfile
import time
import psycopg

PATTERN = re.compile(r'^bf4_probe_downloads/(1|32|64)_(\d+)/player_(\d+)\.json$')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--archive', default='/opt/bf4br/imports/bf4_probe_downloads.tar.zst')
    ap.add_argument('--limit', type=int, default=100, help='Number of player files to consider; 0 = all')
    ap.add_argument('--execute', action='store_true', help='Enable database writes; default validates only')
    ap.add_argument('--dsn', default='dbname=bf4_battle_reports user=postgres')
    args = ap.parse_args()
    counts = collections.Counter()
    started = time.monotonic()
    conn = psycopg.connect(args.dsn, autocommit=True)
    stream = subprocess.Popen(['zstd', '-dc', args.archive], stdout=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=stream.stdout, mode='r|') as archive:
            for member in archive:
                if not member.isfile() or not member.name.endswith('.json'):
                    continue
                match = PATTERN.fullmatch(member.name)
                if match is None:
                    counts['generic_or_other'] += 1
                    continue
                if args.limit and counts['considered'] >= args.limit:
                    break
                counts['considered'] += 1
                platform, report_id, persona_id = map(int, match.groups())
                try:
                    payload = json.load(archive.extractfile(member))
                    detail = payload.get('playerReport') if isinstance(payload, dict) else None
                    roster = payload.get('players') if isinstance(payload, dict) else None
                    valid = (
                        isinstance(payload, dict)
                        and int(payload.get('id', 0)) == report_id
                        and int(payload.get('platform', 0)) == platform
                        and isinstance(roster, dict) and str(persona_id) in roster
                        and isinstance(detail, dict)
                        and str(detail.get('personaId')) == str(persona_id)
                        and isinstance(detail.get('stats'), dict)
                    )
                    if not valid:
                        counts['invalid_payload'] += 1
                        continue
                    if not args.execute:
                        counts['validated'] += 1
                        continue
                    # One transaction per file; any failure rolls back only that file.
                    with conn.transaction():
                        with conn.cursor() as cur:
                            cur.execute("SET LOCAL lock_timeout = '2s'")
                            cur.execute("SET LOCAL statement_timeout = '15s'")
                            cur.execute('SELECT report_timestamp FROM battle_reports WHERE platform=%s AND battlelog_report_id=%s', (platform, report_id))
                            parent = cur.fetchone()
                            if parent is None:
                                counts['missing_report'] += 1
                                continue
                            cur.execute('SELECT 1 FROM players WHERE platform=%s AND persona_id=%s', (platform, persona_id))
                            if cur.fetchone() is None:
                                counts['missing_player'] += 1
                                continue
                            cur.execute('SELECT 1 FROM bf4br_player_report_raw WHERE platform=%s AND battlelog_report_id=%s AND persona_id=%s', (platform, report_id, persona_id))
                            if cur.fetchone():
                                counts['already_imported'] += 1
                                continue
                            cur.execute('INSERT INTO bf4br_detail_reports(platform,battlelog_report_id,report_timestamp) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING', (platform, report_id, parent[0]))
                            cur.execute("INSERT INTO bf4br_detail_players(platform,battlelog_report_id,persona_id,state) VALUES (%s,%s,%s,'ready') ON CONFLICT DO NOTHING", (platform, report_id, persona_id))
                            cur.execute('SELECT state FROM bf4br_detail_players WHERE platform=%s AND battlelog_report_id=%s AND persona_id=%s FOR UPDATE', (platform, report_id, persona_id))
                            state = cur.fetchone()[0]
                            if state not in ('ready', 'retry'):
                                counts['busy_or_done'] += 1
                                continue
                            cur.execute('INSERT INTO bf4br_player_report_raw(platform,battlelog_report_id,persona_id,raw_response) VALUES (%s,%s,%s,%s::jsonb) ON CONFLICT DO NOTHING', (platform, report_id, persona_id, json.dumps(payload, separators=(',', ':'))))
                            if cur.rowcount == 0:
                                counts['already_imported'] += 1
                                continue
                            cur.execute("UPDATE bf4br_detail_players SET state='done',lease_owner=NULL,lease_token=NULL,lease_until=NULL,last_error=NULL,updated_at=now() WHERE platform=%s AND battlelog_report_id=%s AND persona_id=%s AND state IN ('ready','retry')", (platform, report_id, persona_id))
                            if cur.rowcount != 1:
                                raise RuntimeError('job state changed unexpectedly')
                            counts['imported'] += 1
                except (psycopg.errors.LockNotAvailable, psycopg.errors.DeadlockDetected, psycopg.errors.QueryCanceled):
                    conn.rollback()
                    counts['lock_or_timeout_skipped'] += 1
                except Exception as exc:
                    conn.rollback()
                    counts['errors'] += 1
                    if counts['errors'] <= 20:
                        print('ERROR', member.name, str(exc)[:250], flush=True)
                if counts['considered'] % 1000 == 0:
                    print('PROGRESS', dict(counts), 'seconds', round(time.monotonic()-started,1), flush=True)
    finally:
        stream.stdout.close()
        stream.terminate()
        stream.wait()
        conn.close()
    print('FINAL', dict(counts), 'seconds', round(time.monotonic()-started,1), flush=True)

if __name__ == '__main__':
    main()