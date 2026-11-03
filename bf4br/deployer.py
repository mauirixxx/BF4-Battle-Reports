"""BF4BR fleet coordinator: observation-only until deployment is explicitly configured."""
import argparse
import logging
import os
import subprocess
import time
from pathlib import Path

import psycopg

LOG = logging.getLogger("bf4br.deployer")
REPO = Path(os.environ.get("BF4BR_REPO", "/opt/bf4br"))
INTERVAL = max(60, int(os.environ.get("BF4BR_CHECK_INTERVAL", "300")))
DSN = os.environ.get("BF4BR_DSN", "dbname=bf4_battle_reports user=postgres")

def git(*args):
    result = subprocess.run(["git", "-c", f"safe.directory={REPO}", "-C", str(REPO), *args],
                            capture_output=True, text=True, timeout=25, check=True)
    return result.stdout.strip()

def inspect():
    local = git("rev-parse", "HEAD")
    remote_line = git("ls-remote", "--exit-code", "origin", "refs/heads/main")
    remote = remote_line.split()[0]
    with psycopg.connect(DSN, connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute("""SELECT node_name, persona_workers, report_workers, paused
                           FROM bf4br_node_controls ORDER BY node_name""")
            nodes = cur.fetchall()
    LOG.info("release local=%s remote_main=%s update_available=%s",
             local[:12], remote[:12], local != remote)
    for node, persona, report, paused in nodes:
        LOG.info("node=%s paused=%s persona_workers=%s report_workers=%s",
                 node, paused, persona, report)
    LOG.info("mode=observe_only no remote commands or upgrades performed")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="single read-only audit")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    while True:
        try:
            inspect()
        except (psycopg.Error, subprocess.SubprocessError, OSError, ValueError):
            LOG.exception("fleet audit failed")
            if args.once:
                raise
        if args.once:
            break
        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
