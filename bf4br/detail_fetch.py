"""Persona-specific Battlelog fetch. Shares the existing node-wide 429 gate."""
import json
import subprocess
import tempfile
from pathlib import Path


def fetch_detail(platform, report_id, persona_id):
    if platform not in (1,32,64) or report_id <= 0 or persona_id <= 0:
        raise ValueError('invalid report or persona identity')
    url=(f'https://battlelog.battlefield.com/bf4/battlereport/loadgeneralreport/'
         f'{report_id}/{platform}/{persona_id}/')
    with tempfile.TemporaryDirectory(prefix='bf4br-detail-') as tmp:
        headers=Path(tmp)/'headers'
        proc=subprocess.run(
            ['curl','-sS','--connect-timeout','5','--max-time','20',
             '-D',str(headers),'-w','\n%{http_code}',url],
            capture_output=True,text=True,timeout=24)
        body,sep,status=proc.stdout.rpartition('\n')
        code=int(status) if sep and status.isdigit() else 0
        retry_after=None
        if headers.exists():
            for line in headers.read_text(errors='replace').splitlines():
                if line.lower().startswith('retry-after:'):
                    retry_after=line.partition(':')[2].strip()
        if proc.returncode or code!=200:
            return code,None,f'curl={proc.returncode}',retry_after
        try:
            payload=json.loads(body)
        except ValueError:
            return code,None,'invalid JSON',retry_after
        return code,payload,None,retry_after
