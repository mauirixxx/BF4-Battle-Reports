"""Idempotent report importer; raw archive remains durable on failure."""
from datetime import datetime,timezone
from uuid import UUID

def validate(payload,platform,rid):
    if not isinstance(payload,dict) or int(payload.get("id",0))!=rid or int(payload.get("platform",0))!=platform:
        raise ValueError("report identity mismatch")
    server=payload.get("gameServer")
    roster=payload.get("players")
    if not isinstance(server,dict) or not server.get("guid") or not server.get("name") or not payload.get("createdAt"):
        raise ValueError("missing server metadata")
    UUID(str(server["guid"]))
    if not isinstance(roster,dict) or not roster:
        raise ValueError("missing player roster")
    people=[]
    for item in roster.values():
        pid=int(item["personaId"])
        name=item["persona"]["personaName"]
        if pid<=0 or not isinstance(name,str) or not name:
            raise ValueError("invalid player identity")
        people.append((pid,name))
    if len({pid for pid,_ in people})!=len(people):
        raise ValueError("duplicate persona IDs")
    return server,people

def import_archived(conn,platform,rid,token):
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("""SELECT 1 FROM bf4br_report_jobs WHERE platform=%s
                AND battlelog_report_id=%s AND state='leased'
                AND lease_token=%s AND lease_until>now() FOR UPDATE""",(platform,rid,token))
            if not cur.fetchone():
                raise RuntimeError("report lease lost")
            cur.execute("""SELECT raw_response,fetched_at,imported_at
                FROM battle_report_raw WHERE platform=%s AND battlelog_report_id=%s
                FOR UPDATE""",(platform,rid))
            found=cur.fetchone()
            if not found:
                raise RuntimeError("report has not been archived")
            payload,observed,imported=found
            if imported is not None:
                return 0
            server,people=validate(payload,platform,rid)
            stamp=datetime.fromtimestamp(int(payload["createdAt"]),timezone.utc)
            cur.execute("""INSERT INTO servers(server_guid,current_name)
                VALUES (%s,%s) ON CONFLICT(server_guid) DO NOTHING""",
                (str(server["guid"]),server["name"]))
            cur.execute("""INSERT INTO battle_reports
                (platform,battlelog_report_id,server_id,report_timestamp,collected_at)
                SELECT %s,%s,id,%s,%s FROM servers WHERE server_guid=%s
                ON CONFLICT(platform,battlelog_report_id) DO NOTHING""",
                (platform,rid,stamp,observed,str(server["guid"])))
            cur.execute("""SELECT id FROM battle_reports
                WHERE platform=%s AND battlelog_report_id=%s""",(platform,rid))
            report_pk=cur.fetchone()[0]
            for pid,name in people:
                cur.execute("""INSERT INTO players
                    (platform,persona_id,current_name,current_name_observed_at,
                     earliest_report_at,latest_report_at)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(platform,persona_id) DO UPDATE
                    SET earliest_report_at=LEAST(players.earliest_report_at,excluded.earliest_report_at),
                        latest_report_at=GREATEST(players.latest_report_at,excluded.latest_report_at),
                        current_name=CASE WHEN excluded.current_name_observed_at>
                            players.current_name_observed_at THEN excluded.current_name
                            ELSE players.current_name END,
                        current_name_observed_at=GREATEST(
                            players.current_name_observed_at,excluded.current_name_observed_at)
                    RETURNING id""",(platform,pid,name,observed,stamp,stamp))
                player_pk=cur.fetchone()[0]
                cur.execute("""INSERT INTO report_players(report_id,player_id,player_name_observed)
                    VALUES (%s,%s,%s) ON CONFLICT DO NOTHING""",
                    (report_pk,player_pk,name))
                cur.execute("""INSERT INTO player_name_history
                    (player_id,player_name,observed_at,source_report_id)
                    SELECT %s,%s,%s,%s
                    WHERE NOT EXISTS (
                      SELECT 1 FROM player_name_history WHERE player_id=%s AND source_report_id=%s)
                    AND (SELECT player_name FROM player_name_history
                         WHERE player_id=%s ORDER BY observed_at DESC,id DESC LIMIT 1)
                         IS DISTINCT FROM %s
                    AND COALESCE((SELECT max(observed_at) FROM player_name_history
                                  WHERE player_id=%s),'-infinity'::timestamptz)<=%s""",
                    (player_pk,name,observed,report_pk,player_pk,report_pk,player_pk,name,player_pk,observed))
            cur.execute("""UPDATE battle_report_raw SET imported_at=COALESCE(imported_at,now())
                WHERE platform=%s AND battlelog_report_id=%s""",(platform,rid))
    return len(people)
