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
import subprocess
import sys
import time

ROOT = Path("/opt")
LIVE = ROOT / "bf4br"
RELEASES = ROOT / "bf4br-releases"
STATE = ROOT / "bf4br-release-state.json"
LOCK = Path("/run/lock/bf4br-release.lock")
SERVICE = "bf4br-supervisor.service"
VERSION = re.compile(r"v[0-9]+\.[0-9]+\.[0-9]+\Z")


def run(*args, timeout=90):
    return subprocess.run(args, check=True, text=True, capture_output=True, timeout=timeout)


def service_active():
    return subprocess.run(["systemctl", "is-active", "--quiet", SERVICE]).returncode == 0


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
    run(str(target / ".venv/bin/python"), "-c", "import psycopg, bf4br.supervisor", timeout=15)
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
        try:
            switch(target)
            run("systemctl", "start", SERVICE, timeout=45)
            for _ in range(12):
                time.sleep(2)
                if not service_active():
                    raise RuntimeError("supervisor failed health check")
            STATE.write_text(json.dumps({"version": version, "sha": sha,
                                         "previous": previous}) + "\n")
            print(json.dumps({"status": "deployed", "version": version,
                              "sha": sha, "previous": previous}))
        except Exception:
            restore(previous)
            run("systemctl", "restart", SERVICE, timeout=75)
            if not service_active():
                raise RuntimeError("ROLLBACK FAILED: supervisor not active")
            raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--deploy", required=True)
    parser.add_argument("--sha", required=True)
    args = parser.parse_args()
    deploy(args.deploy, args.sha)


if __name__ == "__main__":
    main()
