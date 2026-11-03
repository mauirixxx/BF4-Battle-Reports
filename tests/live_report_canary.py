"""Explicit one-report live canary against disposable PostgreSQL only."""
import os
import psycopg
from bf4br.queue import claim
from bf4br.report_worker import process_one

def main():
    dsn=os.environ["BF4BR_TEST_DSN"]
    with psycopg.connect(dsn,autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database()")
            if cur.fetchone()[0]!="bf4br_integration":
                raise SystemExit("REFUSED: not disposable integration database")
            cur.execute("""INSERT INTO bf4br_report_jobs(platform,battlelog_report_id)
                VALUES (64,2108797019914111296) ON CONFLICT DO NOTHING""")
        claimed=claim(conn,"report","live-canary",120)
        if not claimed:
            raise SystemExit("No canary job claimed")
        job,token=claimed
        result=process_one(conn,job,token)
        with conn.cursor() as cur:
            cur.execute("""SELECT r.imported_at IS NOT NULL,
                (SELECT count(*) FROM report_players rp JOIN battle_reports br
                 ON rp.report_id=br.id WHERE br.platform=64
                 AND br.battlelog_report_id=2108797019914111296)
                FROM battle_report_raw r WHERE r.platform=64
                AND r.battlelog_report_id=2108797019914111296""")
            print("CANARY",result,"archive_and_import",cur.fetchone(),flush=True)
        if result!="imported":
            raise SystemExit(1)

if __name__=="__main__":
    main()
