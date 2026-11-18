#!/usr/bin/env python3
"""One authenticated-by-private-IP, read-only 2018 batch. SHA-256 stream footer."""
import base64,gzip,hashlib,http.server,json,subprocess,urllib.parse
HOST='192.168.200.71'; ALLOW='192.168.200.49'
LO='1514764800'; HI='1546300800'
class Handler(http.server.BaseHTTPRequestHandler):
 def do_GET(self):
  if self.client_address[0]!=ALLOW:self.send_error(403);return
  q=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
  try:
   ts=q.get('ts',[LO])[0];rid=q.get('rid',['0'])[0];n=int(q.get('reports',['50'])[0])
   if not(ts.isascii() and ts.isdigit() and len(ts)==10 and LO<=ts<HI and rid.isascii() and rid.isdigit() and len(rid)<=19 and 1<=n<=200):raise ValueError()
  except ValueError:self.send_error(400);return
  # Index-assisted ordered distinct key selection; include ALL players at cutoff key.
  sql=("COPY (WITH boundary AS MATERIALIZED (SELECT DISTINCT created_at_raw,report_id FROM public.raw_reports "
       "WHERE created_at_raw >= '%s' AND created_at_raw < '%s' AND (created_at_raw,report_id)>('%s','%s') "
       "ORDER BY created_at_raw,report_id LIMIT %d), cutoff AS "
       "(SELECT created_at_raw AS ts,report_id AS rid FROM boundary ORDER BY created_at_raw DESC,report_id DESC LIMIT 1) "
       "SELECT r.created_at_raw,r.report_id,r.payload_base64_gzip FROM public.raw_reports r,cutoff "
       "WHERE r.created_at_raw >= '%s' AND r.created_at_raw < '%s' "
       "AND (r.created_at_raw,r.report_id)>('%s','%s') "
       "AND (r.created_at_raw,r.report_id)<=(cutoff.ts,cutoff.rid) "
       "ORDER BY r.created_at_raw,r.report_id) TO STDOUT" %(LO,HI,ts,rid,n,LO,HI,ts,rid))
  proc=subprocess.Popen(['runuser','-u','postgres','--','psql','-X','-v','ON_ERROR_STOP=1','-d','bf4cr_reports','-c',sql],stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=1024*1024)
  self.send_response(200);self.send_header('Content-Type','application/x-ndjson');self.send_header('Cache-Control','no-store');self.end_headers()
  h=hashlib.sha256();count=bad=0;last=(ts,rid)
  try:
   for line in proc.stdout:
    try:
     stamp,report_id,encoded=line.rstrip(b'\n').split(b'\t',2)
     stamp=stamp.decode('ascii');report_id=report_id.decode('ascii')
     obj=json.loads(gzip.decompress(base64.b64decode(encoded,validate=True)))
     if str(obj['reportId'])!=report_id or str(obj['createdAt'])!=stamp:raise ValueError('payload key mismatch')
     data=(json.dumps({'kind':'row','ts':stamp,'report_id':report_id,'payload':obj},separators=(',',':'))+'\n').encode()
     self.wfile.write(data);h.update(data);count+=1;last=(stamp,report_id)
    except (BrokenPipeError,ConnectionResetError):
     proc.kill();proc.wait();self.server.done=True;return
    except (ValueError,KeyError,TypeError,OSError,EOFError) as e:
     bad+=1;print('SOURCE_BAD',str(e)[:150],flush=True)
   proc.wait()
   if proc.returncode:bad+=1
   footer={'kind':'end','count':count,'errors':bad,'sha256':h.hexdigest(),'last_ts':last[0],'last_rid':last[1],'after_ts':ts,'after_rid':rid,'complete':proc.returncode==0 and bad==0}
   self.wfile.write((json.dumps(footer,separators=(',',':'))+'\n').encode());self.wfile.flush()
   print('BATCH_2018',ts,rid,'last',last,'rows',count,'errors',bad,'exit',proc.returncode,flush=True)
  except (BrokenPipeError,ConnectionResetError):
   proc.kill();proc.wait()
  self.server.done=True
 def log_message(self,*a):pass
server=http.server.HTTPServer((HOST,18721),Handler);server.timeout=15;server.done=False
while True:server.handle_request()