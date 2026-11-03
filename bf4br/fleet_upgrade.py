"""Single-node release coordinator; opt-in, release-only, fail-closed.

Runs on reports as root with its dedicated pinned-host-key SSH configuration.
No action is taken unless --deploy is supplied and a published stable GitHub
release matches the explicitly configured canary host.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from bf4br.release_coordinator import latest_release, tag_sha

HOST = "hnl-01"
LOCK = Path("/run/lock/bf4br-fleet-deploy.lock")
STATE = Path("/var/lib/bf4br-deployer/approved.json")
REPO = "/opt/bf4br"
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", HOST]


def run(args, **kwargs):
    return subprocess.run(args, check=True, timeout=180, **kwargs)


def release():
    info = latest_release()
    return info["tag_name"], tag_sha(info["tag_name"])


def stage(version, sha):
    # Refuse to overwrite an already-published version directory.
    # Reuse only an installation carrying the exact expected SHA marker.
    check = subprocess.run(
        SSH + ["test -f /opt/bf4br-releases/" + version +
               "/.bf4br-release-sha && grep -qx '" + sha + "' " +
               "/opt/bf4br-releases/" + version + "/.bf4br-release-sha"],
        capture_output=True, text=True, timeout=15)
    if check.returncode == 0:
        return
    exists = subprocess.run(SSH + [f"test -e /opt/bf4br-releases/{version}"],
                            timeout=15)
    if exists.returncode == 0:
        raise RuntimeError("release directory already exists without matching SHA; refusing overwrite")
    # git archive reads the verified commit object, never mutable main.
    run(["git", "-C", REPO, "fetch", "--no-tags", "origin", sha],
        stdout=subprocess.DEVNULL)
    actual = subprocess.check_output(["git", "-C", REPO, "rev-parse", sha],
                                     text=True).strip()
    if actual != sha:
        raise RuntimeError("archive commit mismatch")
    tar = subprocess.Popen(["git", "-C", REPO, "archive", "--format=tar", sha],
                           stdout=subprocess.PIPE)
    try:
        run(SSH + ["mkdir", "-p", f"/opt/bf4br-releases/{version}"])
        unpack = subprocess.Popen(SSH + ["tar", "-xf", "-", "-C",
                                         f"/opt/bf4br-releases/{version}"],
                                  stdin=tar.stdout)
        tar.stdout.close()
        if unpack.wait(timeout=120) != 0 or tar.wait(timeout=120) != 0:
            raise RuntimeError("release archive transfer failed")
    finally:
        if tar.poll() is None:
            tar.kill()
            tar.wait()
    # Marker only after successful extraction and dependency setup.
    remote = (
        f"set -e; cd /opt/bf4br-releases/{version}; "
        "test -f requirements.txt; "
        "test -f bf4br/supervisor.py; "
        "test -d .venv || python3 -m venv .venv; "
        ".venv/bin/pip install -q -r requirements.txt; "
        ".venv/bin/python -c 'import psycopg, bf4br.supervisor'; "
        f"printf '%s\\n' '{sha}' > .bf4br-release-sha"
    )
    run(SSH + [remote])


def control(action):
    """Use postgres peer auth on reports; never export database credentials."""
    if action not in ("pause", "resume"):
        raise ValueError("unsupported control action")
    return run(["runuser", "-u", "postgres", "--",
                "/opt/bf4br/.venv/bin/python", "-m", "bf4br.control",
                "--node", HOST, action], cwd=REPO,
               env={**os.environ, "BF4BR_DSN": "dbname=bf4_battle_reports user=postgres"})


def drain(timeout=100):
    """Require paused controls and no outstanding node-owned leases."""
    deadline = time.monotonic() + timeout
    script = (
        "import psycopg,sys; "
        "c=psycopg.connect('dbname=bf4_battle_reports user=postgres'); "
        "cur=c.cursor(); "
        "cur.execute('SELECT paused FROM bf4br_node_controls WHERE node_name=%s',('hnl-01',)); "
        "row=cur.fetchone(); "
        "cur.execute(\"SELECT (SELECT count(*) FROM bf4br_persona_jobs WHERE state='leased' AND lease_owner LIKE %s) + "
        "(SELECT count(*) FROM bf4br_report_jobs WHERE state='leased' AND lease_owner LIKE %s)\", "
        "('hnl-01-%','hnl-01-%')); "
        "n=cur.fetchone()[0]; "
        "print(int(bool(row and row[0])),n); "
        "sys.exit(0 if row and row[0] and n==0 else 1)"
    )
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["runuser", "-u", "postgres", "--",
             "/opt/bf4br/.venv/bin/python", "-c", script],
            cwd=REPO, capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            return
        time.sleep(3)
    raise TimeoutError("node did not drain database leases")


def deploy():
    if os.geteuid() != 0:
        raise PermissionError("coordinator must run as root")
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open("w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        version, sha = release()
        # Explicit host allowlist, no arbitrary remote execution targets.
        stage(version, sha)
        # Remote switcher is shipped from coordinator code, not from the
        # release archive, so the v1.0.0 baseline can be deployed.
        run(["scp", "-q", "-o", "BatchMode=yes", "-o",
             "StrictHostKeyChecking=yes",
             f"{REPO}/bf4br/release_switch.py",
             f"{HOST}:/root/bf4br-release-switch.py"])
        control("pause")
        try:
            drain()
            result = run(SSH + ["python3", "/root/bf4br-release-switch.py",
                                "--deploy", version, "--sha", sha],
                         capture_output=True, text=True)
            print(result.stdout)
        finally:
            control("resume")
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps({"host": HOST, "version": version,
                                     "sha": sha}) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--deploy", action="store_true")
    args = parser.parse_args()
    if args.check == args.deploy:
        parser.error("choose exactly one of --check or --deploy")
    if args.check:
        version, sha = release()
        print(json.dumps({"release": version, "sha": sha, "host": HOST,
                          "action": "none"}))
    else:
        deploy()


if __name__ == "__main__":
    main()
