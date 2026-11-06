"""Database-discovered sequential release coordinator; fail-closed.

Runs on the BF4BR database host as root with pinned-host-key SSH.
No action is taken unless --deploy is supplied and a published stable GitHub
release is published and eligible.
"""
import argparse
import re
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from bf4br.release_coordinator import latest_release, tag_sha

LOCK = Path("/run/lock/bf4br-fleet-deploy.lock")
STATE = Path("/var/lib/bf4br-deployer/approved.json")
REPO = "/opt/bf4br"
PAUSE_STATE = Path("/var/lib/bf4br-deployer/updater-pauses.json")


def run(args, **kwargs):
    return subprocess.run(args, check=True, timeout=180, **kwargs)


def release():
    info = latest_release()
    return info["tag_name"], tag_sha(info["tag_name"])


def registered_hosts():
    """Only registered collector nodes; never deploy to the database coordinator."""
    query = ("import psycopg,json; "
             "c=psycopg.connect('dbname=bf4_battle_reports user=postgres'); "
             "cur=c.cursor(); "
             "cur.execute(\"SELECT node_name FROM bf4br_node_controls "
             "WHERE node_name NOT IN ('reports','rnt-reports') "
             "AND (persona_workers > 0 OR report_workers > 0) "
             "ORDER BY node_name\"); "
             "print(json.dumps([r[0] for r in cur.fetchall()]))")
    output = subprocess.check_output(
        ['runuser','-u','postgres','--',REPO+'/.venv/bin/python','-c',query],
        text=True, timeout=15)
    hosts = json.loads(output)
    for host in hosts:
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,62}', host):
            raise ValueError(f'unsafe registered hostname: {host!r}')
    return hosts


def stage(version, sha, host):
    SSH = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", host]
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


def control(action, host):
    """Use postgres peer auth on reports; never export database credentials."""
    if action not in ("pause", "resume"):
        raise ValueError("unsupported control action")
    return run(["runuser", "-u", "postgres", "--",
                "/opt/bf4br/.venv/bin/python", "-m", "bf4br.control",
                "--node", host, action], cwd=REPO,
               env={**os.environ, "BF4BR_DSN": "dbname=bf4_battle_reports user=postgres"})


def drain(host, timeout=100):
    """Require paused controls and no outstanding node-owned leases."""
    deadline = time.monotonic() + timeout
    script = (
        "import psycopg,sys; "
        "c=psycopg.connect('dbname=bf4_battle_reports user=postgres'); "
        "cur=c.cursor(); "
        "cur.execute('SELECT paused FROM bf4br_node_controls WHERE node_name=%s',(" + repr(host) + ",)); "
        "row=cur.fetchone(); "
        "cur.execute(\"SELECT (SELECT count(*) FROM bf4br_persona_jobs WHERE state='leased' AND lease_owner LIKE %s) + "
        "(SELECT count(*) FROM bf4br_report_jobs WHERE state='leased' AND lease_owner LIKE %s) + "
        "(SELECT count(*) FROM bf4br_daily_persona_jobs WHERE state='leased' AND lease_owner LIKE %s) + "
        "(SELECT count(*) FROM bf4br_daily_report_jobs WHERE state='leased' AND lease_owner LIKE %s)\", "
        "(" + ",".join([repr(host + "-%")] * 4) + ")); "
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



def paused(host):
    query = ('import psycopg,sys; '
             'c=psycopg.connect("dbname=bf4_battle_reports user=postgres"); '
             'r=c.execute("SELECT paused FROM bf4br_node_controls WHERE node_name=%s",(sys.argv[1],)).fetchone(); '
             'print(int(bool(r and r[0])))')
    return subprocess.check_output(['runuser','-u','postgres','--',REPO+'/.venv/bin/python',
                                    '-c',query,host],text=True,timeout=15).strip() == '1'


def pause_records():
    if not PAUSE_STATE.exists():
        return {}
    data=json.loads(PAUSE_STATE.read_text())
    if not isinstance(data,dict):
        raise ValueError('invalid updater pause journal')
    return data


def record_pause(host,version,sha):
    data=pause_records()
    data[host]={'version':version,'sha':sha}
    PAUSE_STATE.parent.mkdir(parents=True,exist_ok=True)
    tmp=PAUSE_STATE.with_suffix('.tmp')
    tmp.write_text(json.dumps(data,sort_keys=True)+'\n')
    os.replace(tmp,PAUSE_STATE)


def clear_pause_record(host):
    data=pause_records()
    if host in data:
        del data[host]
        tmp=PAUSE_STATE.with_suffix('.tmp')
        tmp.write_text(json.dumps(data,sort_keys=True)+'\n')
        os.replace(tmp,PAUSE_STATE)


def recover_completed_pause(host,version,sha):
    entry=pause_records().get(host)
    if entry is None:
        return False
    if entry != {'version':version,'sha':sha}:
        raise RuntimeError(f'{host}: updater pause journal belongs to a different release')
    if paused(host):
        control('resume',host)
    clear_pause_record(host)
    return True


def deploy():
    if os.geteuid() != 0:
        raise PermissionError("coordinator must run as root")
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open("w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        version, sha = release()
        results = []
        hosts = registered_hosts()
        for host in hosts:
            ssh = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", host]
            current = subprocess.run(ssh + ["readlink -f /opt/bf4br"],
                capture_output=True, text=True, timeout=15, check=True).stdout.strip()
            if current == f"/opt/bf4br-releases/{version}":
                marker = subprocess.run(ssh + ["cat /opt/bf4br-release-state.json"],
                    capture_output=True, text=True, timeout=15)
                if marker.returncode == 0:
                    state = json.loads(marker.stdout)
                    if state.get("version") != version or state.get("sha") != sha:
                        raise RuntimeError(f"{host}: live release state differs from official tag")
                else:
                    # Pre-existing manually installed v1.0.1 node: verify immutable artifact marker.
                    run(ssh + [f"grep -qx '{sha}' /opt/bf4br-releases/{version}/.bf4br-release-sha"])
                recovered=recover_completed_pause(host,version,sha)
                results.append({"host": host, "status": "resumed_after_upgrade" if recovered else "already_current"})
                continue
            stage(version, sha, host)
            run(["scp", "-q", "-o", "BatchMode=yes", "-o",
                 "StrictHostKeyChecking=yes", f"{REPO}/bf4br/release_switch.py",
                 f"{host}:/root/bf4br-release-switch.py"])
            # Respect operator pauses that existed before the upgrade.
            was_paused = paused(host)
            if not was_paused:
                record_pause(host,version,sha)
                control("pause", host)
            try:
                drain(host)
                result = run(ssh + ["python3", "/root/bf4br-release-switch.py",
                                    "--deploy", version, "--sha", sha],
                             capture_output=True, text=True)
                results.append({"host": host, "result": json.loads(result.stdout)})
            finally:
                if not was_paused:
                    control("resume", host)
                    clear_pause_record(host)
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps({"hosts": hosts, "version": version,
                                     "sha": sha, "results": results}) + "\n")
        print(json.dumps({"version": version, "results": results}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--deploy", action="store_true")
    args = parser.parse_args()
    if args.check == args.deploy:
        parser.error("choose exactly one of --check or --deploy")
    if args.check:
        version, sha = release()
        hosts = registered_hosts()
        print(json.dumps({"release": version, "sha": sha, "hosts": hosts,
                          "action": "none"}))
    else:
        deploy()


if __name__ == "__main__":
    main()
