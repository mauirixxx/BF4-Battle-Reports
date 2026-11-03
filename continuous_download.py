"""Continuous bounded batches, with cumulative summaries even on Ctrl+C."""
import subprocess,sys,time,signal,json
from collections import defaultdict

PLATFORMS=('PC','PlayStation','Xbox')

def next_wait(cooldown):
    from bf4reports import sql
    result=sql(f"""SELECT count(*),COALESCE(ceil(extract(epoch FROM min(a.last_attempt_at + make_interval(mins => {cooldown}) - now())))::bigint,0) FROM history_discoveries d LEFT JOIN battle_reports b ON b.platform=d.platform AND b.battlelog_report_id=d.battlelog_report_id LEFT JOIN battle_report_raw r ON r.platform=d.platform AND r.battlelog_report_id=d.battlelog_report_id LEFT JOIN battle_report_download_attempts a ON a.platform=d.platform AND a.battlelog_report_id=d.battlelog_report_id WHERE b.id IS NULL AND r.battlelog_report_id IS NULL AND a.last_attempt_at>now()-make_interval(mins => {cooldown}) AND a.last_result <> 'archived';""")
    count,seconds=map(int,result.split('|'))
    return count,max(1,seconds+1)

def run(args):
    batches=0
    previous_batch=None
    totals={p:{'imported':0,'failed':0} for p in PLATFORMS}
    archived=0
    current_child=None
    interrupted=False
    def summary(reason):
        print('\nCONTINUOUS SUMMARY BY PLATFORM',flush=True)
        print(f"{'Platform':<14} {'Imported':>8} {'Failed':>8}",flush=True)
        for platform in PLATFORMS:
            c=totals[platform]
            print(f"{platform:<14} {c['imported']:>8} {c['failed']:>8}",flush=True)
        print('CONTINUOUS SUMMARY',json.dumps({'new_imported':sum(x['imported'] for x in totals.values())-archived,'archived_imported':archived,'failed':sum(x['failed'] for x in totals.values()),'batches':batches,'reason':reason}),flush=True)
    def handle_interrupt(signum,frame):
        nonlocal interrupted
        interrupted=True
        raise KeyboardInterrupt
    old_handler=signal.signal(signal.SIGINT,handle_interrupt)
    print('CONTINUOUS MODE: Ctrl+C to stop with cumulative summary',flush=True)
    reason='stopped'
    result=1
    try:
        while True:
            cmd=[sys.executable,__file__.replace('continuous_download.py','bf4reports.py'),'download','--limit','100','--attempts',str(args.attempts),'--delay',str(args.delay),'--retry-cooldown-minutes',str(args.retry_cooldown_minutes)]
            work=0
            batch_items=[]
            stop_http=False
            with subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1,start_new_session=True) as child:
                current_child=child
                for line in child.stdout:
                    print(line,end='',flush=True)
                    parts=line.split()
                    if line.startswith(('FETCH ','RECOVERED ')):
                        work+=1
                        batch_items.append(line.strip())
                    if len(parts)>=3 and parts[1] in totals:
                        if parts[0] in ('IMPORTED','RECOVERED'):
                            totals[parts[1]]['imported']+=1
                            if parts[0]=='RECOVERED':archived+=1
                    if parts[:2]==['IMPORT','FAILED'] and len(parts)>2 and parts[2] in totals:
                        totals[parts[2]]['failed']+=1
                    if parts and parts[0]=='RETRYABLE' and len(parts)>=6 and parts[1] in totals:
                        try:
                            if int(parts[4])==args.attempts:totals[parts[1]]['failed']+=1
                        except ValueError:pass
                    if line.startswith('HTTP_DIAGNOSTIC ') and 'outcome http_error ' in line:
                        stop_http=True
                        child.terminate()
                        break
                try:code=child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill();code=child.wait()
            current_child=None
            batches+=1
            if stop_http:
                reason='non-200 HTTP response';result=1;break
            if code:
                reason=f'downloader exited {code}';result=code;break
            if work==0:
                waiting,seconds=next_wait(args.retry_cooldown_minutes)
                if not waiting:
                    reason='all known report IDs processed';result=0;break
                print('CONTINUOUS IDLE:',waiting,'reports cooling down; sleeping',seconds,'seconds',flush=True)
                time.sleep(seconds)
                continue
            if batch_items==previous_batch:
                waiting,seconds=next_wait(args.retry_cooldown_minutes)
                if waiting:
                    print('CONTINUOUS IDLE: repeated batch, sleeping',seconds,'seconds',flush=True)
                    time.sleep(seconds)
                    continue
                reason='repeated batch without progress';result=1;break
            previous_batch=batch_items
            print('CONTINUOUS BATCH COMPLETE',batches,'items',work,flush=True)
    except KeyboardInterrupt:
        reason='Ctrl+C';result=130
        if current_child is not None and current_child.poll() is None:
            current_child.terminate()
            try:current_child.wait(timeout=3)
            except subprocess.TimeoutExpired:current_child.kill();current_child.wait()
        print('\nCONTINUOUS STOP: Ctrl+C',flush=True)
    finally:
        signal.signal(signal.SIGINT,old_handler)
        summary(reason)
    return result