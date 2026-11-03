"""Archive fetched reports before import; protect writes with queue lease."""
import json

def archive(conn, platform, report_id, token, payload):
    if not isinstance(payload, dict) or int(payload.get("id",0)) != report_id or int(payload.get("platform",0)) != platform:
        raise ValueError("report identity mismatch")
    server = payload.get("gameServer")
    players = payload.get("players")
    if not isinstance(server, dict) or not server.get("guid") or not server.get("name") or not payload.get("createdAt") or not isinstance(players, dict) or not players:
        raise ValueError("incomplete report")
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM bf4br_report_jobs WHERE platform=%s AND battlelog_report_id=%s AND state='leased' AND lease_token=%s AND lease_until>now() FOR UPDATE", (platform, report_id, token))
            if not cur.fetchone():
                raise RuntimeError("lease lost")
            cur.execute("INSERT INTO battle_report_raw(platform,battlelog_report_id,raw_response) VALUES (%s,%s,%s::jsonb) ON CONFLICT DO NOTHING", (platform,report_id,json.dumps(payload)))
            cur.execute("INSERT INTO battle_report_details(platform,battlelog_report_id,report_json) VALUES (%s,%s,%s::jsonb) ON CONFLICT DO NOTHING", (platform,report_id,json.dumps(payload)))
    return True

def recover(conn,platform,report_id):
    with conn.cursor() as cur:
        cur.execute("SELECT raw_response,imported_at FROM battle_report_raw WHERE platform=%s AND battlelog_report_id=%s",(platform,report_id))
        return cur.fetchone()
