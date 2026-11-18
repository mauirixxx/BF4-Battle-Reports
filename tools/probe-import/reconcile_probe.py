#!/usr/bin/env python3
"""Reconcile only report IDs present in a validated probe archive."""
import argparse, json, sys, time
import psycopg

SQL = '''WITH expected AS (
 SELECT count(*) AS required,
        count(*) FILTER (WHERE dp.state='done' AND raw.persona_id IS NOT NULL) AS completed
 FROM battle_reports r
 JOIN report_players rp ON rp.report_id=r.id
 JOIN players p ON p.id=rp.player_id AND p.platform=r.platform
 LEFT JOIN bf4br_detail_players dp ON dp.platform=r.platform AND dp.battlelog_report_id=r.battlelog_report_id AND dp.persona_id=p.persona_id
 LEFT JOIN bf4br_player_report_raw raw ON raw.platform=r.platform AND raw.battlelog_report_id=r.battlelog_report_id AND raw.persona_id=p.persona_id
 WHERE r.platform=%s AND r.battlelog_report_id=%s
), updated AS (
 UPDATE bf4br_detail_reports d SET state='complete',expected_players=e.required,completed_at=now(),updated_at=now(),last_error=NULL
 FROM expected e WHERE d.platform=%s AND d.battlelog_report_id=%s AND d.state='pending'
 AND e.required>0 AND e.required=e.completed
 AND NOT EXISTS (SELECT 1 FROM bf4br_detail_players dp WHERE dp.platform=d.platform AND dp.battlelog_report_id=d.battlelog_report_id AND dp.state<>'done')
 RETURNING d.battlelog_report_id
) SELECT count(*) FROM updated'''

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--candidates',required=True);ap.add_argument('--dsn',default='dbname=bf4_battle_reports user=postgres');args=ap.parse_args()
 with open(args.candidates) as f:
  candidates={tuple(json.loads(line)) for line in f if line.strip()}
 if not candidates: print('RECONCILE no candidates');return
 started=time.monotonic();updated=0;timeouts=0
 with psycopg.connect(args.dsn,autocommit=True) as db:
  for platform,rid in sorted(candidates):
   for attempt in range(3):
    try:
     with db.transaction():
      with db.cursor() as cur:
       cur.execute("SET LOCAL lock_timeout='2s'");cur.execute("SET LOCAL statement_timeout='15s'")
       cur.execute(SQL,(platform,rid,platform,rid));updated+=cur.fetchone()[0]
     break
    except (psycopg.errors.LockNotAvailable,psycopg.errors.DeadlockDetected,psycopg.errors.QueryCanceled):
     if attempt==2:timeouts+=1
     else:time.sleep((1,3)[attempt])
 print('RECONCILE',json.dumps({'candidates':len(candidates),'completed':updated,'timeout_skipped':timeouts,'seconds':round(time.monotonic()-started,1)}),flush=True)
 if timeouts:sys.exit(2)
if __name__=='__main__':main()
