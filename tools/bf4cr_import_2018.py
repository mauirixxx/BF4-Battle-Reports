#!/usr/bin/env python3
"""Year-specific BF4CR stream importer: atomic batch+cursor, checksum verified."""
import argparse,hashlib,json,sys,urllib.request
import psycopg
from bf4cr_bridge import run,transform
LO='1514764800';HI='1546300800';SOURCE='bf4cr-2018'
def main():
 p=argparse.ArgumentParser()
 p.add_argument('--reports',type=int,default=50);p.add_argument('--fail-after',type=int,default=0)
 p.add_argument('--url',default='http://192.168.200.71:18721/')
 p.add_argument('--dsn',default='dbname=bf4_battle_reports user=postgres')
 a=p.parse_args()
 if not 1<=a.reports<=200:raise SystemExit('reports must be 1..200')
 with psycopg.connect(a.dsn) as db:
  with db.transaction():
   with db.cursor() as c:
    c.execute("INSERT INTO bf4cr_year_checkpoint(source_name,year,last_ts,last_report_id) VALUES (%s,2018,%s,'0') ON CONFLICT DO NOTHING",(SOURCE,LO))
    c.execute("SELECT last_ts,last_report_id,rows_imported,batches_imported FROM bf4cr_year_checkpoint WHERE source_name=%s FOR UPDATE",(SOURCE,))
    ts,rid,previous,batches=c.fetchone()
   url=a.url+'?ts='+ts+'&rid='+rid+'&reports='+str(a.reports)
   digest=hashlib.sha256();count=rejected=0;last=(ts,rid);footer=None
   with urllib.request.urlopen(url,timeout=300) as response:
    if response.status!=200:raise RuntimeError('HTTP '+str(response.status))
    for line in response:
     item=json.loads(line)
     if item.get('kind')=='end':
      footer=item
      if response.read(1):raise RuntimeError('trailing bytes after footer')
      break
     if item.get('kind')!='row' or footer is not None:raise RuntimeError('unexpected record')
     key=(str(item['ts']),str(item['report_id']))
     if not(LO<=key[0]<HI) or key<last or key<=(ts,rid):raise RuntimeError('out-of-order or out-of-year record')
     if str(item['payload']['reportId'])!=key[1] or str(item['payload']['createdAt'])!=key[0]:raise RuntimeError('payload mismatch')
     try:transform(item['payload'])
     except (ValueError,TypeError,KeyError,OverflowError) as exc:
      with db.cursor() as c:
       c.execute('INSERT INTO bf4cr_import_rejected(source_name,report_id,persona_id,error,payload) VALUES (%s,%s,%s,%s,%s::jsonb) ON CONFLICT(source_name,report_id,persona_id) DO UPDATE SET error=EXCLUDED.error,payload=EXCLUDED.payload',(SOURCE,key[1],str(item['payload'].get('personaId','')),str(exc)[:500],json.dumps(item['payload'])))
      rejected+=1
     else:run(db,item['payload'])
     digest.update(line);count+=1;last=key
     if a.fail_after and count>=a.fail_after:raise RuntimeError('INJECTED_FAILURE')
   if footer is None:raise RuntimeError('TRUNCATED: no footer')
   if not footer.get('complete') or footer.get('errors')!=0:raise RuntimeError('source failure')
   if (footer.get('after_ts'),footer.get('after_rid'))!=(ts,rid) or footer.get('count')!=count or (footer.get('last_ts'),footer.get('last_rid'))!=last or footer.get('sha256')!=digest.hexdigest():raise RuntimeError('footer mismatch')
   if count:
    with db.cursor() as c:
     c.execute('UPDATE bf4cr_year_checkpoint SET last_ts=%s,last_report_id=%s,rows_imported=rows_imported+%s,batches_imported=batches_imported+1,updated_at=now() WHERE source_name=%s',(*last,count,SOURCE))
   print('COMMITTED',json.dumps({'previous':[ts,rid],'cursor':last,'batch_rows':count,'rejected':rejected,'prior_rows':previous,'prior_batches':batches,'done':count==0}),flush=True)
if __name__=='__main__':
 try:main()
 except Exception as e:print('ABORTED: rolled back:',repr(e),file=sys.stderr);sys.exit(1)
