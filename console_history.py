#!/usr/bin/env python3
"""Manual BF4 console history discovery. No scheduled execution."""
import argparse, datetime, json, subprocess, time, random
DB='bf4_battle_reports'
SEEDS={'ps4':(32,366599803),'xbox':(64,1977340393)}
def sql(s):
 p=subprocess.run(['runuser','-u','postgres','--','psql','-X','-v','ON_ERROR_STOP=1','-At','-d',DB],input=s,text=True,capture_output=True)
 if p.returncode: raise RuntimeError(p.stderr)
 return p.stdout.strip()
def q(s): return "'"+str(s).replace("'","''")+"'"
def main():
 ap=argparse.ArgumentParser()
 ap.add_argument('--pages',type=int,default=2)
 args=ap.parse_args()
 if not 1<=args.pages<=10: ap.error('pages must be 1..10')
 for label,(platform,persona) in SEEDS.items():
  checkpoint=sql(f'SELECT next_cursor FROM history_checkpoints WHERE platform={platform} AND persona_id={persona}')
  cursor=int(checkpoint) if checkpoint else 1793264400
  for page in range(args.pages):
   url=f'https://battlelog.battlefield.com/bf4/warsawbattlereportspopulatemore/{persona}/2048/{platform}/{cursor}/'
   good=False
   for attempt in range(3):
    p=subprocess.run(['curl','-sS','--connect-timeout','5','--max-time','20','-w','\\n%{http_code}',url],capture_output=True,text=True,timeout=24)
    body,sep,http=p.stdout.rpartition('\n')
    try:
     payload=json.loads(body)
     reports=payload.get('data',{}).get('gameReports') if isinstance(payload,dict) else None
     good=p.returncode==0 and sep and http=='200' and isinstance(reports,list) and len(reports)>0
    except (ValueError,AttributeError): good=False
    if good: break
    print('RETRY',label,page+1,attempt+1,'HTTP',http,'curl',p.returncode,flush=True)
    if attempt<2: time.sleep(2**attempt+random.random())
   if not good:
    print('STOP',label,'no usable history; checkpoint unchanged',flush=True)
    break
   rows=[]
   for r in reports:
    if not isinstance(r,dict) or not r.get('gameReportId') or not r.get('createdAt'): raise ValueError('malformed history row')
    rows.append((int(r['gameReportId']),int(r['createdAt']),r.get('name'),r.get('map')))
   next_cursor=min(row[1] for row in rows)-1
   if next_cursor>=cursor: raise ValueError('nondecreasing cursor')
   statements=['BEGIN;']
   for rid,created,name,mapcode in rows:
    stamp=datetime.datetime.fromtimestamp(created,datetime.timezone.utc).isoformat()
    statements.append(f"INSERT INTO history_discoveries(platform,battlelog_report_id,report_timestamp,server_name,map_code) VALUES ({platform},{rid},{q(stamp)},{'NULL' if name is None else q(name)},{'NULL' if mapcode is None else q(mapcode)}) ON CONFLICT(platform,battlelog_report_id) DO UPDATE SET last_seen_at=now();")
    statements.append(f"INSERT INTO history_report_sources(platform,persona_id,battlelog_report_id) VALUES ({platform},{persona},{rid}) ON CONFLICT DO NOTHING;")
   statements.append(f"INSERT INTO history_pages(platform,persona_id,cursor_used,raw_response,report_count,next_cursor) VALUES ({platform},{persona},{cursor},{q(json.dumps(payload))}::jsonb,{len(rows)},{next_cursor}) ON CONFLICT(platform,persona_id,cursor_used) DO NOTHING;")
   statements.append(f"INSERT INTO history_checkpoints(platform,persona_id,next_cursor,pages_saved) VALUES ({platform},{persona},{next_cursor},1) ON CONFLICT(platform,persona_id) DO UPDATE SET next_cursor=EXCLUDED.next_cursor,pages_saved=history_checkpoints.pages_saved+1,updated_at=now() WHERE history_checkpoints.next_cursor={cursor};")
   statements.append('COMMIT;')
   sql('\n'.join(statements))
   print('SAVED',label,'page',page+1,'reports',len(rows),'next',next_cursor,flush=True)
   cursor=next_cursor
   time.sleep(1.5)
 print('DISCOVERIES',sql('SELECT platform,count(*) FROM history_discoveries GROUP BY platform ORDER BY platform;'),flush=True)
if __name__=='__main__': main()