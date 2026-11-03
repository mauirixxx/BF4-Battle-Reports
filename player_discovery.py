#!/usr/bin/env python3
"""Bounded manual discovery from imported player identities; no scheduler."""
import argparse, datetime, json, random, subprocess, time
DB='bf4_battle_reports'
def sql(s):
 p=subprocess.run(['runuser','-u','postgres','--','psql','-X','-v','ON_ERROR_STOP=1','-At','-d',DB],input=s,text=True,capture_output=True)
 if p.returncode: raise RuntimeError(p.stderr.strip())
 return p.stdout.strip()
def q(v): return "'"+str(v).replace("'","''")+"'"
def main():
 ap=argparse.ArgumentParser()
 ap.add_argument('--players',type=int,default=10)
 ap.add_argument('--personaid','--persona-id',type=int,default=None,help='refresh all newer history for one Persona ID')
 ap.add_argument('--platform',type=int,choices=[1,32,64],default=None,help='platform for --personaid; auto-detect if unique')
 ap.add_argument('--pages-per-player',type=int,default=1)
 ap.add_argument('--failure-cooldown-hours',type=int,default=24)
 args=ap.parse_args()
 if not 1<=args.players<=30 or not 1<=args.pages_per_player<=3 or not 1<=args.failure_cooldown_hours<=168: ap.error('players 1..30, pages 1..3, failure cooldown 1..168 hours')
 if args.personaid is not None:
  if args.personaid<=0:ap.error('--personaid must be positive')
  platforms=[int(v) for v in sql(f'SELECT DISTINCT platform FROM players WHERE persona_id={args.personaid} UNION SELECT DISTINCT platform FROM history_report_sources WHERE persona_id={args.personaid}').splitlines() if v]
  platform=args.platform or (platforms[0] if len(platforms)==1 else None)
  if platform is None:ap.error('specify --platform 1, 32, or 64 (persona not found or ambiguous)')
  from persona_refresh import run
  if not run(sql,q,args.personaid,platform,args.failure_cooldown_hours):raise SystemExit(1)
  return
 # Fair selection across platforms, avoiding any persona with an existing checkpoint.
 candidates=sql("""WITH ranked AS (
 SELECT p.platform,p.persona_id,row_number() OVER
 (PARTITION BY p.platform ORDER BY p.latest_report_at DESC,p.persona_id) AS turn
 FROM players p LEFT JOIN history_checkpoints c
 ON c.platform=p.platform AND c.persona_id=p.persona_id
 LEFT JOIN history_discovery_failures f
 ON f.platform=p.platform AND f.persona_id=p.persona_id
 WHERE c.persona_id IS NULL AND (f.retry_after IS NULL OR f.retry_after <= now())
 ) SELECT platform,persona_id FROM ranked
 ORDER BY turn,CASE platform WHEN 1 THEN 0 WHEN 32 THEN 1 WHEN 64 THEN 2 ELSE 3 END
 LIMIT """+str(args.players))
 selected=[tuple(map(int,line.split('|'))) for line in candidates.splitlines()]
 print('SELECTED',len(selected),'players',flush=True)
 totals={'players':0,'pages':0,'new_reports':0,'stopped':0}
 for platform,persona in selected:
  checkpoint=sql(f'SELECT next_cursor FROM history_checkpoints WHERE platform={platform} AND persona_id={persona}')
  cursor=int(checkpoint) if checkpoint else 1793264400
  label={1:'PC',32:'PlayStation',64:'Xbox'}.get(platform,str(platform))
  for page in range(args.pages_per_player):
   url=f'https://battlelog.battlefield.com/bf4/warsawbattlereportspopulatemore/{persona}/2048/{platform}/{cursor}/'
   good=False
   for attempt in range(1,4):
    p=subprocess.run(['curl','-sS','--connect-timeout','5','--max-time','20','-w','\\n%{http_code}',url],capture_output=True,text=True,timeout=24)
    body,sep,http=p.stdout.rpartition('\n')
    try:
     payload=json.loads(body)
     reports=payload.get('data',{}).get('gameReports') if isinstance(payload,dict) else None
     good=p.returncode==0 and bool(sep) and http=='200' and isinstance(reports,list) and bool(reports)
    except (ValueError,AttributeError):good=False
    if good:break
    print('RETRY',label,persona,'attempt',attempt,'http',http,'curl',p.returncode,flush=True)
    if attempt<3:time.sleep(2**attempt+random.random())
   if not good:
    print('STOP',label,persona,'no usable page; checkpoint unchanged',flush=True)
    sql(f"INSERT INTO history_discovery_failures(platform,persona_id,failures,last_failed_at,retry_after,last_reason) VALUES ({platform},{persona},1,now(),now()+interval '{args.failure_cooldown_hours} hours','no usable history after 3 attempts') ON CONFLICT(platform,persona_id) DO UPDATE SET failures=history_discovery_failures.failures+1,last_failed_at=now(),retry_after=now()+interval '{args.failure_cooldown_hours} hours',last_reason=excluded.last_reason;")
    print('COOLDOWN',label,persona,args.failure_cooldown_hours,'hours',flush=True)
    totals['stopped']+=1
    break
   rows=[]
   for r in reports:
    if not isinstance(r,dict) or not r.get('gameReportId') or not r.get('createdAt'):
     raise ValueError('malformed history row; no checkpoint saved')
    rows.append((int(r['gameReportId']),int(r['createdAt']),r.get('name'),r.get('map')))
   next_cursor=min(row[1] for row in rows)-1
   if next_cursor>=cursor:raise ValueError('nondecreasing cursor')
   before=int(sql('SELECT count(*) FROM history_discoveries'))
   statements=['BEGIN;']
   for rid,created,name,mapcode in rows:
    stamp=datetime.datetime.fromtimestamp(created,datetime.timezone.utc).isoformat()
    statements.append(f"INSERT INTO history_discoveries(platform,battlelog_report_id,report_timestamp,server_name,map_code) VALUES ({platform},{rid},{q(stamp)},{'NULL' if name is None else q(name)},{'NULL' if mapcode is None else q(mapcode)}) ON CONFLICT(platform,battlelog_report_id) DO UPDATE SET last_seen_at=now();")
    statements.append(f"INSERT INTO history_report_sources(platform,persona_id,battlelog_report_id) VALUES ({platform},{persona},{rid}) ON CONFLICT DO NOTHING;")
   statements.append(f"INSERT INTO history_pages(platform,persona_id,cursor_used,raw_response,report_count,next_cursor) VALUES ({platform},{persona},{cursor},{q(json.dumps(payload))}::jsonb,{len(rows)},{next_cursor}) ON CONFLICT(platform,persona_id,cursor_used) DO NOTHING;")
   statements.append(f"INSERT INTO history_checkpoints(platform,persona_id,next_cursor,pages_saved) VALUES ({platform},{persona},{next_cursor},1) ON CONFLICT(platform,persona_id) DO UPDATE SET next_cursor=EXCLUDED.next_cursor,pages_saved=history_checkpoints.pages_saved+1,updated_at=now() WHERE history_checkpoints.next_cursor={cursor};")
   statements.append(f'DELETE FROM history_discovery_failures WHERE platform={platform} AND persona_id={persona};')
   statements.append('COMMIT;')
   sql('\n'.join(statements))
   added=int(sql('SELECT count(*) FROM history_discoveries'))-before
   totals['new_reports']+=added;totals['pages']+=1
   print('SAVED',label,persona,'rows',len(rows),'new',added,flush=True)
   cursor=next_cursor
   time.sleep(1.5)
  totals['players']+=1
 print('SUMMARY',json.dumps(totals),flush=True)
 print('DISCOVERIES',sql('SELECT platform,count(*) FROM history_discoveries GROUP BY platform ORDER BY platform'),flush=True)
if __name__=='__main__':main()