"""Newest-first, resumable incremental discovery for a specified persona."""
import datetime, json, random, subprocess, time

def run(sql, q, persona, platform, cooldown):
    # First targeted run scans all the way to the end, even if the bounded
    # discovery script previously saved some pages. Only a fully completed
    # targeted scan establishes a trusted incremental boundary.
    boundary = sql(f"SELECT extract(epoch FROM newest_report_at)::bigint FROM history_persona_refreshes WHERE platform={platform} AND persona_id={persona}")
    boundary = int(boundary) if boundary else None
    cursor = int(datetime.datetime.now(datetime.timezone.utc).timestamp()) + 86400
    pages = 0
    newest = boundary
    added = 0
    print('PERSONA_REFRESH',platform,persona,'previous_newest',boundary,flush=True)
    while True:
        if pages>=10000:raise RuntimeError('history safety ceiling reached; no success timestamp written')
        url=f'https://battlelog.battlefield.com/bf4/warsawbattlereportspopulatemore/{persona}/2048/{platform}/{cursor}/'
        for attempt in range(3):
            p=subprocess.run(['curl','-sS','--connect-timeout','5','--max-time','20','-w','\\n%{http_code}',url],capture_output=True,text=True,timeout=24)
            body,sep,http=p.stdout.rpartition('\n')
            try:
                payload=json.loads(body)
                reports=payload.get('data',{}).get('gameReports') if isinstance(payload,dict) else None
                valid=p.returncode==0 and bool(sep) and http=='200' and isinstance(reports,list)
            except (ValueError,AttributeError):valid=False
            if valid:break
            reason=('json_type='+type(payload).__name__+' data_type='+type(payload.get('data')).__name__ if isinstance(payload,dict) else 'json_type='+type(payload).__name__) if 'payload' in locals() else 'invalid_json'
            print('RETRY',platform,persona,'attempt',attempt+1,'http',http,'curl',p.returncode,'bytes',len(body),'reason',reason,'preview',repr(body[:100]),flush=True)
            if attempt<2:time.sleep(2**attempt+random.random())
        if not valid:
            print('STOP_ERROR',platform,persona,'no successful timestamp written',flush=True)
            return False
        if not reports:
            print('HISTORY_END',platform,persona,flush=True)
            break
        rows=[]
        for r in reports:
            if not isinstance(r,dict) or not r.get('gameReportId') or not r.get('createdAt'):
                raise ValueError('malformed history row; no success timestamp written')
            rows.append((int(r['gameReportId']),int(r['createdAt']),r.get('name'),r.get('map')))
        next_cursor=min(r[1] for r in rows)-1
        if next_cursor>=cursor:raise ValueError('nondecreasing history cursor')
        fresh=[r for r in rows if boundary is None or r[1]>boundary]
        statements=['BEGIN;']
        for rid,created,name,mapcode in fresh:
            stamp=datetime.datetime.fromtimestamp(created,datetime.timezone.utc).isoformat()
            statements.append(f"INSERT INTO history_discoveries(platform,battlelog_report_id,report_timestamp,server_name,map_code) VALUES ({platform},{rid},{q(stamp)},{'NULL' if name is None else q(name)},{'NULL' if mapcode is None else q(mapcode)}) ON CONFLICT(platform,battlelog_report_id) DO UPDATE SET last_seen_at=now();")
            statements.append(f"INSERT INTO history_report_sources(platform,persona_id,battlelog_report_id) VALUES ({platform},{persona},{rid}) ON CONFLICT DO NOTHING;")
        statements.append(f"INSERT INTO history_pages(platform,persona_id,cursor_used,raw_response,report_count,next_cursor) VALUES ({platform},{persona},{cursor},{q(json.dumps(payload))}::jsonb,{len(rows)},{next_cursor}) ON CONFLICT DO NOTHING;")
        statements.append('COMMIT;')
        sql('\n'.join(statements))
        pages+=1;added+=len(fresh)
        newest=max(newest or 0,max(r[1] for r in rows))
        print('SAVED',platform,persona,'page',pages,'newer_rows',len(fresh),flush=True)
        if boundary is not None and next_cursor<=boundary:
            print('REACHED_PREVIOUS_HISTORY',platform,persona,flush=True)
            break
        cursor=next_cursor
        time.sleep(4.0)
    newest_sql='NULL' if newest is None else q(datetime.datetime.fromtimestamp(newest,datetime.timezone.utc).isoformat())
    sql(f"INSERT INTO history_persona_refreshes(platform,persona_id,last_success_at,newest_report_at,last_pages) VALUES ({platform},{persona},now(),{newest_sql},{pages}) ON CONFLICT(platform,persona_id) DO UPDATE SET last_success_at=now(),newest_report_at=GREATEST(history_persona_refreshes.newest_report_at,excluded.newest_report_at),last_pages=excluded.last_pages;")
    print('SUCCESS',platform,persona,'pages',pages,'newer_rows',added,'newest',newest,flush=True)
    return True