#!/usr/bin/env python3
"""BF4CR flattened player rows -> native BF4BR report/player tables.

Input: newline-delimited BF4CR JSON on stdin. Transactions per row.
Synthetic generic rosters are marked bf4crImport; never overwrite Battlelog JSON.
Does not claim that a recovered player is a complete Battlelog detail.
"""
import argparse,sys,json,datetime,uuid,collections,time
import psycopg
def transform(o):
    rid=int(o["reportId"]); pid=int(o["personaId"]); epoch=int(o["createdAt"])
    name=o["personaName"]; guid=str(uuid.UUID(o["serverGUID"]))
    if rid<=0 or pid<=0 or not isinstance(name,str) or not name.strip() or not (1380000000<=epoch<=2000000000): raise ValueError("invalid identity or timestamp")
    if not isinstance(o.get("serverName"),str) or not o["serverName"]: raise ValueError("missing server name")
    stamp=datetime.datetime.fromtimestamp(epoch,datetime.timezone.utc)
    # BF4CR accuracy is stored in percentage points, unlike native Battlelog ratio.
    player={"personaId":pid,"persona":{"personaName":name},"team":int(o.get("team") or 0),
            "kills":int(o.get("kills") or 0),"deaths":int(o.get("deaths") or 0),
            "combatScore":int(o.get("combatScore") or 0),"revives":int(o.get("revives") or 0),
            "accuracy":float(o["accuracy"])/100 if o.get("accuracy") is not None else None,
            "bf4crSource":True,"bf4crRaw":o}
    return rid,pid,stamp,name,guid,player
def run(conn,o):
    rid,pid,stamp,name,guid,player=transform(o)
    payload={"id":rid,"platform":1,"createdAt":int(o["createdAt"]),"duration":int(o.get("duration") or 0),
             "gameMode":int(o.get("gameModeRaw") or 0),
             "gameServer":{"guid":guid,"name":o["serverName"],"map":o.get("map")},
             "players":{str(pid):player},"teams":{},"bf4crImport":{"partialRoster":True,"source":"BF4CR"}}
    with conn.transaction():
      with conn.cursor() as c:
        c.execute("SET LOCAL lock_timeout='2s'")
        c.execute("SET LOCAL statement_timeout='15s'")
        c.execute("INSERT INTO servers(server_guid,current_name) VALUES (%s,%s) ON CONFLICT(server_guid) DO NOTHING",(guid,o["serverName"]))
        c.execute("""INSERT INTO battle_reports(platform,battlelog_report_id,server_id,report_timestamp,collected_at)
          SELECT 1,%s,id,%s,now() FROM servers WHERE server_guid=%s
          ON CONFLICT(platform,battlelog_report_id) DO NOTHING""",(rid,stamp,guid))
        c.execute("SELECT id FROM battle_reports WHERE platform=1 AND battlelog_report_id=%s",(rid,))
        report_pk=c.fetchone()[0]
        c.execute("""INSERT INTO players(platform,persona_id,current_name,current_name_observed_at,earliest_report_at,latest_report_at)
          VALUES (1,%s,%s,%s,%s,%s) ON CONFLICT(platform,persona_id) DO UPDATE SET
          earliest_report_at=LEAST(players.earliest_report_at,EXCLUDED.earliest_report_at),
          latest_report_at=GREATEST(players.latest_report_at,EXCLUDED.latest_report_at)
          RETURNING id""",(pid,name,stamp,stamp,stamp))
        player_pk=c.fetchone()[0]
        c.execute("""INSERT INTO report_players(report_id,player_id,player_name_observed)
          VALUES (%s,%s,%s) ON CONFLICT DO NOTHING""",(report_pk,player_pk,name))
        c.execute("""INSERT INTO battle_report_details(platform,battlelog_report_id,report_json)
          VALUES (1,%s,%s::jsonb) ON CONFLICT DO NOTHING""",(rid,json.dumps(payload)))
        c.execute("""UPDATE battle_report_details SET report_json=jsonb_set(report_json,'{players}',
          COALESCE(report_json->'players','{}'::jsonb)||%s::jsonb,true)
          WHERE platform=1 AND battlelog_report_id=%s AND report_json ? 'bf4crImport'
          AND (NOT (COALESCE(report_json->'players','{}'::jsonb) ? %s) OR NOT (COALESCE(report_json->'players'->%s,'{}'::jsonb) ? 'bf4crRaw'))""",
          (json.dumps({str(pid):player}),rid,str(pid),str(pid)))
        # Existing Battlelog raw archive, its imported_at, and detail completion state remain untouched.
        return rid,pid
def main():
    ap=argparse.ArgumentParser();ap.add_argument("--execute",action="store_true")
    ap.add_argument("--limit",type=int,default=0);ap.add_argument("--dsn",default="dbname=bf4_battle_reports user=postgres")
    args=ap.parse_args();counter=collections.Counter();start=time.monotonic()
    conn=psycopg.connect(args.dsn) if args.execute else None
    try:
      for line in sys.stdin:
        if args.limit and counter["read"]>=args.limit:break
        counter["read"]+=1
        try:
          o=json.loads(line);rid,pid,stamp,name,guid,player=transform(o)
          if args.execute:run(conn,o);counter["processed"]+=1
          else:counter["validated"]+=1
        except Exception as e:
          counter["errors"]+=1
          if counter["errors"]<=15:print("ERROR",str(e)[:180],file=sys.stderr,flush=True)
        if counter["read"]%1000==0:print("PROGRESS",dict(counter),round(time.monotonic()-start,1),file=sys.stderr,flush=True)
    finally:
      if conn:conn.close()
    print("FINAL",dict(counter),"seconds",round(time.monotonic()-start,2),flush=True)
    if counter["errors"]:sys.exit(1)
if __name__=="__main__":main()
