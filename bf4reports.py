#!/usr/bin/env python3
"""Manual bounded BF4 report downloader. Run only on reports as root."""
import argparse, datetime as dt, json, random, subprocess, sys, time
from pathlib import Path
from fetch_diagnostics import fetch_diagnostic

DB = 'bf4_battle_reports'
PLATFORM_NAMES = {1: 'PC', 32: 'PlayStation', 64: 'Xbox'}
def platform_name(platform): return PLATFORM_NAMES.get(platform, f'Unknown({platform})')
def sql(query):
    p=subprocess.run(['runuser','-u','postgres','--','psql','-X','-v','ON_ERROR_STOP=1','-d',DB,'-At'],input=query,text=True,capture_output=True)
    if p.returncode: raise RuntimeError(p.stderr.strip())
    return p.stdout.strip()
def q(v): return "'"+str(v).replace("'","''")+"'"
def timestamp(epoch): return q(dt.datetime.fromtimestamp(int(epoch),dt.timezone.utc).isoformat())
def parse(obj,platform,rid):
    if obj is None:
        raise ValueError('Battlelog returned JSON null (report temporarily unavailable)')
    if not isinstance(obj,dict):
        raise ValueError(f'Battlelog returned {type(obj).__name__}, expected report object')
    if obj.get('id') is None or obj.get('platform') is None:
        raise ValueError('report JSON missing id or platform')
    if int(obj['id'])!=rid or int(obj['platform'])!=platform:
        raise ValueError(f'report identity mismatch: requested {platform}/{rid}, received {obj["platform"]}/{obj["id"]}')
    server=obj.get('gameServer') or {}
    if not server.get('guid') or not server.get('name') or not obj.get('createdAt'):
        raise ValueError('missing server GUID/name or report timestamp')
    roster=obj.get('players')
    if not isinstance(roster,dict) or not roster: raise ValueError('missing player roster')
    people=[]
    for entry in roster.values():
        pid=int(entry['personaId'])
        name=entry['persona']['personaName']
        if pid<=0 or not isinstance(name,str) or not name: raise ValueError('invalid player identity')
        people.append((pid,name))
    if len({pid for pid,_ in people})!=len(people): raise ValueError('duplicate persona IDs')
    return server,people
def import_report(obj,platform,rid):
    server,people=parse(obj,platform,rid)
    # One PostgreSQL transaction: no half-imported reports, and archive state updated last.
    # Observations come from first successful archive time, not historical report date.
    lines=['BEGIN;', 'SELECT pg_advisory_xact_lock(41029, '+str(rid % 2147483647)+');']
    lines.append(f"INSERT INTO servers(server_guid,current_name) VALUES ({q(server['guid'])},{q(server['name'])}) ON CONFLICT(server_guid) DO NOTHING;")
    lines.append(f"INSERT INTO battle_reports(platform,battlelog_report_id,server_id,report_timestamp,collected_at) SELECT {platform},{rid},id,{timestamp(obj['createdAt'])},COALESCE((SELECT fetched_at FROM battle_report_raw WHERE platform={platform} AND battlelog_report_id={rid}),now()) FROM servers WHERE server_guid={q(server['guid'])} ON CONFLICT(platform,battlelog_report_id) DO NOTHING;")
    for pid,name in people:
        observed=f"(SELECT fetched_at FROM battle_report_raw WHERE platform={platform} AND battlelog_report_id={rid})"
        lines.append(f"INSERT INTO players(platform,persona_id,current_name,current_name_observed_at,earliest_report_at,latest_report_at) VALUES ({platform},{pid},{q(name)},{observed},{timestamp(obj['createdAt'])},{timestamp(obj['createdAt'])}) ON CONFLICT(platform,persona_id) DO UPDATE SET earliest_report_at=LEAST(players.earliest_report_at,excluded.earliest_report_at),latest_report_at=GREATEST(players.latest_report_at,excluded.latest_report_at),current_name=CASE WHEN excluded.current_name_observed_at>players.current_name_observed_at THEN excluded.current_name ELSE players.current_name END,current_name_observed_at=GREATEST(players.current_name_observed_at,excluded.current_name_observed_at);")
        lines.append(f"INSERT INTO report_players(report_id,player_id,player_name_observed) SELECT r.id,p.id,{q(name)} FROM battle_reports r JOIN players p ON p.platform={platform} AND p.persona_id={pid} WHERE r.platform={platform} AND r.battlelog_report_id={rid} ON CONFLICT DO NOTHING;")
        # Transition event, not a unique-name set. Replaying the same report is idempotent.
        # Only a newer observation than the latest event can create a transition.
        lines.append(f"""INSERT INTO player_name_history(player_id,player_name,observed_at,source_report_id)
SELECT p.id,{q(name)},{observed},r.id
FROM players p JOIN battle_reports r ON r.platform={platform} AND r.battlelog_report_id={rid}
WHERE p.platform={platform} AND p.persona_id={pid}
AND NOT EXISTS (SELECT 1 FROM player_name_history h WHERE h.player_id=p.id AND h.source_report_id=r.id)
AND (SELECT h.player_name FROM player_name_history h WHERE h.player_id=p.id ORDER BY h.observed_at DESC,h.id DESC LIMIT 1) IS DISTINCT FROM {q(name)}
AND COALESCE((SELECT max(h.observed_at) FROM player_name_history h WHERE h.player_id=p.id),'-infinity'::timestamptz) <= {observed};""")
    lines.append(f"UPDATE battle_report_raw SET imported_at=COALESCE(imported_at,now()) WHERE platform={platform} AND battlelog_report_id={rid};")
    lines.append('COMMIT;')
    sql('\n'.join(lines))
    return len(people)
def attempt(platform,rid,status):
    sql(f"INSERT INTO battle_report_download_attempts(platform,battlelog_report_id,attempts,last_attempt_at,last_result) VALUES ({platform},{rid},1,now(),{q(status)}) ON CONFLICT(platform,battlelog_report_id) DO UPDATE SET attempts=battle_report_download_attempts.attempts+1,last_attempt_at=now(),last_result=excluded.last_result;")
def fetch(platform,rid):
    url=f'https://battlelog.battlefield.com/bf4/battlereport/loadgeneralreport/{rid}/{platform}/0/'
    p=subprocess.run(['curl','-sS','--connect-timeout','5','--max-time','20','-w','\\n%{http_code}',url],capture_output=True,text=True,timeout=24)
    body,sep,status=p.stdout.rpartition('\n')
    if p.returncode or not sep or status!='200': raise ValueError(f'HTTP {status} curl={p.returncode}')
    try: obj=json.loads(body)
    except json.JSONDecodeError: raise ValueError(f'non-JSON body bytes={len(body)}')
    parse(obj,platform,rid)
    return obj
def main():
    parser=argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser._positionals.title='required argument (pick ONE)'
    parser.add_argument('action',choices=['download','dry-run'],help='download or dry-run (non functional at this time)')
    parser.add_argument('--limit',default='3',help='1..100 reports per run, or "all" for continuous mode')
    parser.add_argument('--attempts',type=int,default=3,help='Attempts per report')
    parser.add_argument('--delay',type=float,default=10.0,metavar='DELAY_IN_SECONDS',help='Delay between report IDs in seconds')
    parser.add_argument('--retry-cooldown-minutes', type=int, default=20,help='Wait before failed reports become eligible again (minutes)')
    args=parser.parse_args()
    if args.action=='dry-run':
        raise SystemExit('dry-run is not implemented yet; no reports were downloaded or changed')
    if not (1<=args.attempts<=8 and args.delay>=1 and 0<=args.retry_cooldown_minutes<=10080):
        parser.error('attempts 1..8, delay >=1, retry cooldown 0..10080 minutes')
    if args.limit.lower()=='all':
        from continuous_download import run
        raise SystemExit(run(args))
    try:args.limit=int(args.limit)
    except ValueError:parser.error('--limit must be 1..100 or all')
    if not 1<=args.limit<=100:parser.error('--limit must be 1..100 or all')
    # Exclusive session lock: avoids duplicate workers and shared rate budget.
    lock=Path('/run/lock/bf4reports-download.lock')
    import fcntl
    with lock.open('w') as handle:
        try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise SystemExit('another downloader is running')
        # Import existing archives before fetching anything new.
        archived=sql(f"SELECT platform,battlelog_report_id,raw_response::text FROM battle_report_raw WHERE imported_at IS NULL ORDER BY fetched_at LIMIT {args.limit};")
        results={'archived_imported':0,'new_imported':0,'failed':0}
        per_platform={p:{'imported':0,'failed':0} for p in PLATFORM_NAMES}
        for line in archived.splitlines():
            platform,rid,payload=line.split('|',2);platform=int(platform);rid=int(rid)
            try:
                n=import_report(json.loads(payload),platform,rid)
                results['archived_imported']+=1;per_platform[platform]['imported']+=1
                print('RECOVERED',platform_name(platform),rid,'players',n,flush=True)
            except Exception as e:results['failed']+=1;per_platform[platform]['failed']+=1;print('IMPORT FAILED archive retained',platform_name(platform),rid,str(e)[:250],flush=True)
        remaining=max(0,args.limit-len(archived.splitlines()))
        targets=sql(f"""WITH eligible AS (
SELECT d.platform,d.battlelog_report_id,d.report_timestamp,
       COALESCE(a.attempts,0) AS attempts
FROM history_discoveries d
LEFT JOIN battle_reports b ON b.platform=d.platform AND b.battlelog_report_id=d.battlelog_report_id
LEFT JOIN battle_report_raw r ON r.platform=d.platform AND r.battlelog_report_id=d.battlelog_report_id
LEFT JOIN battle_report_download_attempts a ON a.platform=d.platform AND a.battlelog_report_id=d.battlelog_report_id
WHERE b.id IS NULL AND r.battlelog_report_id IS NULL
AND (a.last_attempt_at IS NULL OR a.last_result = 'archived'
     OR a.last_attempt_at <= now() - make_interval(mins => {args.retry_cooldown_minutes}))
), ranked AS (
SELECT platform,battlelog_report_id,
       row_number() OVER (PARTITION BY platform ORDER BY attempts,report_timestamp DESC) AS turn
FROM eligible
)
SELECT platform,battlelog_report_id FROM ranked
ORDER BY turn,CASE platform WHEN 1 THEN 0 WHEN 32 THEN 1 WHEN 64 THEN 2 ELSE 3 END
LIMIT {remaining};""")
        for index,line in enumerate(targets.splitlines()):
            platform,rid=map(int,line.split('|'))
            if index:time.sleep(args.delay)
            print('FETCH',platform_name(platform),rid,flush=True)
            for i in range(args.attempts):
                try:
                    obj=fetch_diagnostic(sql,parse,platform,rid,i+1)
                    # Archive committed separately, before import.
                    sql(f"INSERT INTO battle_report_raw(platform,battlelog_report_id,raw_response) VALUES ({platform},{rid},{q(json.dumps(obj,ensure_ascii=True))}::jsonb) ON CONFLICT DO NOTHING;")
                    sql(f"INSERT INTO battle_report_details(platform,battlelog_report_id,report_json) VALUES ({platform},{rid},{q(json.dumps(obj,ensure_ascii=True))}::jsonb) ON CONFLICT(platform,battlelog_report_id) DO NOTHING;")
                    attempt(platform,rid,'archived')
                    print('ARCHIVED',platform_name(platform),rid,flush=True)
                    try:
                        n=import_report(obj,platform,rid)
                        results['new_imported']+=1;per_platform[platform]['imported']+=1
                        print('IMPORTED',platform_name(platform),rid,'players',n,flush=True)
                    except Exception as e:
                        results['failed']+=1;per_platform[platform]['failed']+=1
                        print('IMPORT FAILED archive retained',platform_name(platform),rid,str(e)[:250],flush=True)
                    break
                except Exception as e:
                    attempt(platform,rid,'retryable: '+str(e)[:120])
                    print('FAILURE_CLASS',type(e).__name__,'DETAIL',repr(str(e)),flush=True)
                    print('RETRYABLE',platform_name(platform),rid,'attempt',i+1,str(e)[:120],flush=True)
                    if i+1==args.attempts:results['failed']+=1;per_platform[platform]['failed']+=1
                    else:
                        base=min(60,2*(2**i))
                        pause=random.uniform(base*.5,base*1.5)
                        print('BACKOFF',round(pause,1),flush=True);time.sleep(pause)
        print('SUMMARY BY PLATFORM',flush=True)
        print(f"{'Platform':<14} {'Imported':>8} {'Failed':>8}",flush=True)
        for p in (1,32,64):
            counts=per_platform[p]
            print(f"{platform_name(p):<14} {counts['imported']:>8} {counts['failed']:>8}",flush=True)
        print('SUMMARY',json.dumps(results),flush=True)
if __name__=='__main__':main()