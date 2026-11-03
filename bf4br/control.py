"""BF4BR operator controls. Requires explicit BF4BR_DSN; no implicit DB."""
import argparse
import os
import sys
import psycopg

def main(argv=None):
    parser=argparse.ArgumentParser(description="BF4BR per-node desired concurrency")
    parser.add_argument("--node",required=True,help="worker node identifier")
    sub=parser.add_subparsers(dest="command",required=True)
    sub.add_parser("show")
    setcmd=sub.add_parser("set")
    setcmd.add_argument("--persona-workers",type=int)
    setcmd.add_argument("--report-workers",type=int)
    sub.add_parser("pause")
    sub.add_parser("resume")
    args=parser.parse_args(argv)
    dsn=os.environ.get("BF4BR_DSN")
    if not dsn:
        parser.error("BF4BR_DSN must be set explicitly")
    if args.command=="set":
        if args.persona_workers is None and args.report_workers is None:
            parser.error("set requires at least one worker count")
        for count in (args.persona_workers,args.report_workers):
            if count is not None and not 0 <= count <= 64:
                parser.error("worker count must be between 0 and 64")
    with psycopg.connect(dsn,autocommit=True) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO bf4br_node_controls(node_name)
                    VALUES (%s) ON CONFLICT(node_name) DO NOTHING""",(args.node,))
                if args.command=="set":
                    cur.execute("""UPDATE bf4br_node_controls SET
                        persona_workers=COALESCE(%s,persona_workers),
                        report_workers=COALESCE(%s,report_workers),
                        updated_at=now() WHERE node_name=%s""",
                        (args.persona_workers,args.report_workers,args.node))
                elif args.command in ("pause","resume"):
                    cur.execute("""UPDATE bf4br_node_controls
                        SET paused=%s,updated_at=now() WHERE node_name=%s""",
                        (args.command=="pause",args.node))
                cur.execute("""SELECT node_name,persona_workers,report_workers,paused,
                    updated_at FROM bf4br_node_controls WHERE node_name=%s""",(args.node,))
                row=cur.fetchone()
    print(f"node={row[0]} persona_workers={row[1]} report_workers={row[2]} paused={row[3]} updated_at={row[4]}")

if __name__=="__main__":
    main()
