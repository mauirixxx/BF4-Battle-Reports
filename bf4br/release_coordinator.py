"""Release-only BF4BR deployment coordinator.

This module is deliberately fail-closed: no main-branch polling, no deployment
without a published, non-prerelease GitHub Release and an explicit SHA pin.
"""
import argparse
import json
import re
import subprocess
import urllib.request

REPO = "mauirixxx/BF4-Battle-Reports"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
VERSION = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+$")


def latest_release():
    req = urllib.request.Request(API, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "bf4br-release-coordinator/1.0",
    })
    with urllib.request.urlopen(req, timeout=15) as response:
        data = json.load(response)
    if data.get("draft") or data.get("prerelease"):
        raise ValueError("latest release is not approved for production")
    tag = data.get("tag_name", "")
    if not VERSION.fullmatch(tag):
        raise ValueError(f"invalid release version: {tag!r}")
    if not data.get("published_at"):
        raise ValueError("release has no publication timestamp")
    return data


def tag_sha(tag):
    result = subprocess.run(
        ["git", "-C", "/opt/bf4br", "ls-remote", "--tags",
         "https://github.com/" + REPO + ".git", "refs/tags/" + tag,
         "refs/tags/" + tag + "^{}"],
        check=True, capture_output=True, text=True, timeout=25,
    )
    rows = dict(line.split("\t", 1)[::-1] for line in result.stdout.splitlines())
    sha = rows.get("refs/tags/" + tag + "^{}") or rows.get("refs/tags/" + tag)
    if not sha or not re.fullmatch("[0-9a-f]{40}", sha):
        raise ValueError("release tag is missing or malformed")
    return sha


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="read-only release verification")
    args = parser.parse_args()
    if not args.check:
        parser.error("deployment disabled until the staged rollout is verified; use --check")
    release = latest_release()
    sha = tag_sha(release["tag_name"])
    print(json.dumps({"release": release["tag_name"], "sha": sha,
                      "published_at": release["published_at"],
                      "approved": True, "deployment": "disabled"}, indent=2))


if __name__ == "__main__":
    main()
