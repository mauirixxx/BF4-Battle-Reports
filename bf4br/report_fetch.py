"""Report HTTP fetching, retaining legacy 5s connect / 20s total timeouts."""
import json
import subprocess

def fetch(platform,report_id):
    url=f"https://battlelog.battlefield.com/bf4/battlereport/loadgeneralreport/{report_id}/{platform}/0/"
    p=subprocess.run(["curl","-sS","--connect-timeout","5","--max-time","20",
                      "-w","\\n%{http_code}",url],capture_output=True,text=True,timeout=24)
    body,sep,status=p.stdout.rpartition("\n")
    code=int(status) if sep and status.isdigit() else 0
    if p.returncode or code!=200:
        return code,None,f"curl={p.returncode}"
    try:
        return code,json.loads(body),None
    except ValueError:
        return code,None,"invalid JSON"
