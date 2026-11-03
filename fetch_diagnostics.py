#!/usr/bin/env python3
"""Detailed HTTP/JSON diagnostics for BF4 battle report downloads."""
import json, subprocess, time
from datetime import datetime, timezone
from urllib.parse import urlsplit
def quote(v): return "'"+str(v).replace("'","''")+"'"
def record(sql,platform,rid,number,outcome,http,exit_code,elapsed,body,ctype,error):
    # Retain complete response text, including error HTML and JSON null; no silent truncation.
    size=len(body.encode('utf-8',errors='replace'))
    query=f"""INSERT INTO battle_report_fetch_log(platform,battlelog_report_id,attempt_number,outcome,http_status,curl_exit,elapsed_ms,response_bytes,content_type,error_message,response_body,response_truncated)
VALUES ({platform},{rid},{number},{quote(outcome)},{'NULL' if not http.isdigit() else int(http)},{exit_code},{elapsed},{size},{quote(ctype)},{quote(error)},{quote(body)},false);"""
    sql(query)
def fetch_diagnostic(sql,parse,platform,rid,number):
    url=f'https://battlelog.battlefield.com/bf4/battlereport/loadgeneralreport/{rid}/{platform}/0/'
    started=time.monotonic()
    try:
        p=subprocess.run(['curl','-sS','--connect-timeout','5','--max-time','20','-w','\\n%{http_code}\\n%{content_type}',url],capture_output=True,text=True,timeout=24,errors='replace')
        elapsed=round((time.monotonic()-started)*1000)
        body,sep,tail=p.stdout.rpartition('\n')
        body2,sep2,http=body.rpartition('\n')
        if sep and sep2: body=body2; ctype=tail.strip()
        else: http='';ctype='';body=p.stdout
        obj=None; outcome='ok';error=''
        if p.returncode:outcome='curl_error';error=f'curl exit {p.returncode}: {p.stderr[:500]}'
        elif http!='200':outcome='http_error';error=f'HTTP {http}'
        else:
            try:obj=json.loads(body)
            except (ValueError,TypeError) as e:outcome='invalid_json';error=str(e)
            else:
                try:parse(obj,platform,rid)
                except Exception as e:
                    outcome='json_null' if obj is None else 'invalid_report'
                    error=f'{type(e).__name__}: {e}'
        record(sql,platform,rid,number,outcome,http,p.returncode,elapsed,body,ctype,error)
        print('HTTP_DIAGNOSTIC',platform,rid,'attempt',number,'outcome',outcome,'http',http,'curl',p.returncode,'ms',elapsed,'bytes',len(body.encode('utf-8',errors='replace')),'content_type',ctype,'error',error[:160],flush=True)
        if outcome!='ok':raise ValueError(f'{outcome}: {error}')
        return obj
    except subprocess.TimeoutExpired as e:
        elapsed=round((time.monotonic()-started)*1000)
        record(sql,platform,rid,number,'process_timeout','',124,elapsed,'','',str(e))
        raise ValueError(f'process_timeout: {e}') from e