#!/usr/bin/env python3
"""Bounded, restartable 2018-only importer with disk guard and persistent log."""
import os,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
PY=sys.executable
def main():
 for batch in range(1,100000):
  disk=os.statvfs('/srv/database')
  free=disk.f_bavail*disk.f_frsize
  if free<150*1024**3:
   print('STOP: less than 150 GiB free on target database volume',flush=True);return 2
  for attempt in range(6):
   proc=subprocess.run([PY,str(HERE/'bf4cr_import_2018.py'),'--reports','100'],capture_output=True,text=True,timeout=1200)
   if proc.stdout:print(proc.stdout.strip(),flush=True)
   if proc.returncode==0:break
   detail=proc.stderr.strip()
   if ('LockNotAvailable' not in detail and 'lock timeout' not in detail.lower()) or attempt==5:
    print('STOP: import batch failed:',detail,flush=True);return proc.returncode
   delay=(5,10,20,30,60)[attempt]
   print('RETRY: transient lock timeout; batch rolled back; attempt',attempt+2,'of 6 in',delay,'seconds:',detail[:250],flush=True)
   time.sleep(delay)
  if '"done": true' in proc.stdout:
   print('YEAR 2018 COMPLETE; no other years started',flush=True);return 0
  if batch%25==0:
   print('PROGRESS batches_this_run',batch,'target_free_GiB',round(free/1024**3,1),flush=True)
 print('STOP: batch safety limit reached',flush=True);return 3
if __name__=='__main__':sys.exit(main())
