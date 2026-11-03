#!/usr/bin/env python3
"""Find imported BF4 battle reports shared by two or more persona IDs."""
import argparse, subprocess, sys
PLATFORMS={'pc':1,'playstation':32,'ps4':32,'xbox':64,'xboxone':64}
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('platform',choices=sorted(PLATFORMS))
 p.add_argument('persona_ids',nargs='+',type=int)
 p.add_argument('--limit',type=int,default=100)
 args=p.parse_args()
 ids=list(dict.fromkeys(args.persona_ids))
 if len(ids)<2 or len(ids)>20 or any(i<=0 for i in ids) or not 1<=args.limit<=1000:
  p.error('provide 2..20 distinct positive persona IDs and limit 1..1000')
 platform=PLATFORMS[args.platform]
 wanted=','.join(str(i) for i in ids)
 query=f"""SELECT r.battlelog_report_id,
 to_char(r.report_timestamp AT TIME ZONE 'UTC','YYYY-MM-DD HH24:MI:SS') || ' UTC',
 s.current_name,
 string_agg(DISTINCT rp.player_name_observed || ' (' || pl.persona_id || ')', ', ')
 FROM battle_reports r
 JOIN servers s ON s.id=r.server_id
 JOIN report_players rp ON rp.report_id=r.id
 JOIN players pl ON pl.id=rp.player_id
 WHERE r.platform={platform} AND pl.platform={platform} AND pl.persona_id IN ({wanted})
 GROUP BY r.id,r.battlelog_report_id,r.report_timestamp,s.current_name
 HAVING count(DISTINCT pl.persona_id)={len(ids)}
 ORDER BY r.report_timestamp DESC,r.battlelog_report_id DESC
 LIMIT {args.limit};"""
 cmd=['runuser','-u','postgres','--','psql','-X','-v','ON_ERROR_STOP=1','-d','bf4_battle_reports','-F',' | ','-At','-c',query]
 result=subprocess.run(cmd,capture_output=True,text=True)
 if result.returncode:sys.exit(result.stderr.strip())
 if not result.stdout.strip():print('No shared imported battle reports found.');return
 print('REPORT ID | BATTLELOG CREATED AT (UTC) | SERVER | MATCHED PLAYERS')
 print(result.stdout,end='')
if __name__=='__main__':main()