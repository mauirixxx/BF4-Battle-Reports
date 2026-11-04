"""Remote host release switcher. Run as root on an explicitly approved BF4BR collector.

Never modifies database schema, credentials or other services.  Invoked by
the release coordinator only after release artifacts are staged and tested.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time

ROOT = Path("/opt")
LIVE = ROOT / "bf4br"
RELEASES = ROOT / "bf4br-releases"
STATE = ROOT / "bf4br-release-state.json"
LOCK = Path("/run/lock/bf4br-release.lock")
SERVICE = "bf4br-supervisor.service"
COORDINATED_DROPIN = Path("/etc/systemd/system/bf4br-supervisor.service.d/50-bf4br-coordinated.conf")
VERSION = re.compile(r"v[0-9]+\.[0-9]+\.[0-9]+\Z")


def run(*args, timeout=90, cwd=None):
    return subprocess.run(args, check=True, text=True, capture_output=True, timeout=timeout, cwd=cwd)


def service_active():
    return subprocess.run(["systemctl", "is-active", "--quiet", SERVICE]).returncode == 0



def healthy():
    """Check supervisor process, systemd state, and PostgreSQL connectivity."""
    if not service_active():
        return False
    result = run("systemctl", "show", SERVICE,
                 "--property=MainPID", "--value", timeout=10)
    pid = int(result.stdout.strip() or "0")
    if pid <= 1 or not Path(f"/proc/{pid}").exists():
        return False
    environment = run("systemctl", "show", SERVICE,
                      "--property=Environment", "--value", timeout=10).stdout
    variables = dict(item.split("=", 1) for item in shlex.split(environment)
                     if "=" in item)
    dsn = variables.get("BF4BR_DSN")
    if not dsn:
        return False
    # Probe through the active release virtualenv, not system Python.
    probe = subprocess.run(
        [str(LIVE / '.venv/bin/python'), '-c',
         "import os,psycopg; c=psycopg.connect(os.environ['BF4BR_DSN'],connect_timeout=5); "
         "cur=c.cursor(); cur.execute('SELECT 1'); assert cur.fetchone()==(1,); c.close()"],
        env={**os.environ, 'BF4BR_DSN': dsn},
        capture_output=True, text=True, timeout=12)
    return probe.returncode == 0


def installed():
    if LIVE.is_symlink():
        return str(LIVE.resolve())
    if LIVE.is_dir():
        return str(LIVE)
    raise RuntimeError("live application path missing")


def assert_staged(version, sha):
    if not VERSION.fullmatch(version) or not re.fullmatch(r"[a-f0-9]{40}", sha):
        raise ValueError("invalid version or SHA")
    target = RELEASES / version
    marker = target / ".bf4br-release-sha"
    if not target.is_dir() or target.is_symlink() or not marker.is_file():
        raise RuntimeError("release not staged or missing SHA marker")
    if marker.read_text().strip() != sha:
        raise RuntimeError("staged release SHA mismatch")
    if not (target / ".venv/bin/python").is_file():
        raise RuntimeError("staged virtualenv missing")
    run(str(target / ".venv/bin/python"), "-c", "import psycopg, bf4br.supervisor", timeout=15, cwd=target)
    return target


def switch(target):
    """Replace the live path only after the supervisor has stopped."""
    if not LIVE.is_symlink():
        legacy = RELEASES / "legacy-pre-v1"
        if legacy.exists():
            raise RuntimeError("legacy backup already exists")
        LIVE.rename(legacy)
    temp = ROOT / ".bf4br-next"
    if temp.exists() or temp.is_symlink():
        raise RuntimeError("temporary link already exists")
    temp.symlink_to(target, target_is_directory=True)
    os.replace(temp, LIVE)


def restore(previous):
    if previous == str(LIVE):
        legacy = RELEASES / "legacy-pre-v1"
        if not legacy.is_dir():
            raise RuntimeError("legacy backup missing")
        LIVE.unlink()
        legacy.rename(LIVE)
    else:
        temp = ROOT / ".bf4br-rollback"
        if temp.exists() or temp.is_symlink():
            raise RuntimeError("rollback link already exists")
        temp.symlink_to(previous, target_is_directory=True)
        os.replace(temp, LIVE)


def configure_coordinated(version):
    """Enable centralized assignments for v1.0.6+; preserve preexisting config."""
    major, minor, patch = (int(v) for v in version[1:].split('.'))
    if (major, minor, patch) < (1, 0, 6):
        return False
    if COORDINATED_DROPIN.exists():
        if COORDINATED_DROPIN.read_text() != '[Service]\nEnvironment=BF4BR_COORDINATED=1\n':
            raise RuntimeError('unexpected coordinated drop-in content')
        return False
    COORDINATED_DROPIN.parent.mkdir(parents=True, exist_ok=True)
    COORDINATED_DROPIN.write_text('[Service]\nEnvironment=BF4BR_COORDINATED=1\n')
    run('systemctl', 'daemon-reload')
    return True


def deploy(version, sha):
    if os.geteuid() != 0:
        raise PermissionError("root required")
    target = assert_staged(version, sha)
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        previous = installed()
        if previous == str(target):
            print(json.dumps({"status": "already_installed", "version": version}))
            return
        if not service_active():
            raise RuntimeError("supervisor is not active; refusing switch")
        # systemd TimeoutStopSec=55: supervisor drains children up to 45s.
        run("systemctl", "stop", SERVICE, timeout=75)
        if service_active():
            raise RuntimeError("supervisor did not stop")
        created_dropin = False
        try:
            switch(target)
            created_dropin = configure_coordinated(version)
            run("systemctl", "start", SERVICE, timeout=45)
            for _ in range(12):
                time.sleep(2)
                if not healthy():
                    raise RuntimeError("supervisor or database failed health check")
            STATE.write_text(json.dumps({"version": version, "sha": sha,
                                         "previous": previous}) + "\n")
            print(json.dumps({"status": "deployed", "version": version,
                              "sha": sha, "previous": previous}))
        except Exception:
            if created_dropin:
                COORDINATED_DROPIN.unlink(missing_ok=True)
                run('systemctl', 'daemon-reload')
            restore(previous)
            run("systemctl", "restart", SERVICE, timeout=75)
            if not healthy():
                raise RuntimeError("ROLLBACK FAILED: supervisor or database unhealthy")
            raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--deploy", required=True)
    parser.add_argument("--sha", required=True)
    args = parser.parse_args()
    deploy(args.deploy, args.sha)


if __name__ == "__main__":
    main()
