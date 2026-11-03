"""Durable, token-fenced persona page persistence.

A successful page and its next cursor commit in the same transaction.
The original history tables are used unchanged.
"""
import json
from datetime import datetime, timezone

def persist_page(conn, platform, persona, token, cursor, payload):
    if not isinstance(payload, dict):
        raise ValueError("history payload must be an object")
    data = payload.get("data")
    reports = data.get("gameReports") if isinstance(data,dict) else None
    if not isinstance(reports,list):
        raise ValueError("history payload missing gameReports list")
    rows=[]
    for item in reports:
        if not isinstance(item,dict) or not item.get("gameReportId") or not item.get("createdAt"):
            raise ValueError("malformed history row")
        rid=int(item["gameReportId"])
        stamp=int(item["createdAt"])
        if rid<=0 or stamp<=0 or stamp>cursor:
            raise ValueError("invalid report id or timestamp")
        rows.append((rid,stamp,item.get("name"),item.get("map")))
    next_cursor=min(x[1] for x in rows)-1 if rows else None
    if next_cursor is not None and next_cursor>=cursor:
        raise ValueError("history cursor did not decrease")
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("""SELECT cursor_epoch,boundary_epoch,newest_epoch
                FROM bf4br_persona_jobs WHERE platform=%s AND persona_id=%s
                AND state='leased' AND lease_token=%s AND lease_until>now()
                FOR UPDATE""",(platform,persona,token))
            job=cur.fetchone()
            if not job:
                raise RuntimeError("lease lost; refusing page write")
            saved_cursor,boundary,newest=job
            if saved_cursor is not None and saved_cursor!=cursor:
                raise RuntimeError("stale page cursor")
            fresh=[r for r in rows if boundary is None or r[1]>boundary]
            for rid,stamp,name,mapcode in fresh:
                dt=datetime.fromtimestamp(stamp,timezone.utc)
                cur.execute("""INSERT INTO history_discoveries
                    (platform,battlelog_report_id,report_timestamp,server_name,map_code)
                    VALUES (%s,%s,%s,%s,%s)
                    ON CONFLICT(platform,battlelog_report_id)
                    DO UPDATE SET last_seen_at=now()""",(platform,rid,dt,name,mapcode))
                cur.execute("""INSERT INTO history_report_sources
                    (platform,persona_id,battlelog_report_id)
                    VALUES (%s,%s,%s) ON CONFLICT DO NOTHING""",
                    (platform,persona,rid))
                cur.execute("""INSERT INTO bf4br_report_jobs(platform,battlelog_report_id)
                    VALUES (%s,%s) ON CONFLICT DO NOTHING""",(platform,rid))
            cur.execute("""INSERT INTO history_pages
                (platform,persona_id,cursor_used,raw_response,report_count,next_cursor)
                VALUES (%s,%s,%s,%s::jsonb,%s,%s)
                ON CONFLICT DO NOTHING""",
                (platform,persona,cursor,json.dumps(payload),len(rows),next_cursor))
            new_newest=max([newest or 0]+[r[1] for r in rows]) or None
            finished=(not rows or (boundary is not None and next_cursor<=boundary))
            if finished:
                cur.execute("""INSERT INTO history_persona_refreshes
                    (platform,persona_id,last_success_at,newest_report_at,last_pages)
                    VALUES (%s,%s,now(),to_timestamp(%s),1)
                    ON CONFLICT(platform,persona_id) DO UPDATE
                    SET last_success_at=now(),
                        newest_report_at=GREATEST(
                            history_persona_refreshes.newest_report_at,
                            EXCLUDED.newest_report_at),
                        last_pages=history_persona_refreshes.last_pages+1""",
                    (platform,persona,new_newest))
            cur.execute("""UPDATE bf4br_persona_jobs SET
                cursor_epoch=%s,newest_epoch=%s,\n                boundary_epoch=CASE WHEN %s THEN %s ELSE boundary_epoch END,
                state=CASE WHEN %s THEN 'ready' ELSE 'leased' END,
                next_attempt_at=CASE WHEN %s THEN now()+interval '24 hours'
                                     ELSE next_attempt_at END,
                last_completed_at=CASE WHEN %s THEN now() ELSE last_completed_at END,
                lease_owner=CASE WHEN %s THEN NULL ELSE lease_owner END,
                lease_token=CASE WHEN %s THEN NULL ELSE lease_token END,
                lease_until=CASE WHEN %s THEN NULL ELSE lease_until END,
                updated_at=now()
                WHERE platform=%s AND persona_id=%s AND lease_token=%s
                  AND state='leased' AND lease_until>now()""",
                (None if finished else next_cursor,new_newest,
                 finished,finished,finished,finished,finished,finished,finished,finished,
                 platform,persona,token))
            if cur.rowcount!=1:
                raise RuntimeError("lease expired during page transaction")
    return {"saved":len(fresh),"finished":finished,"next_cursor":next_cursor}
