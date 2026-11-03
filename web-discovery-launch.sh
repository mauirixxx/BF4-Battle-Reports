#!/bin/bash
set -euo pipefail
[[ $# -eq 2 && "$1" =~ ^[0-9]{1,19}$ && "$2" =~ ^(1|32|64)$ ]] || exit 2
umask 027
mkdir -p /var/log/bf4reports-web
exec /usr/bin/flock -n /run/lock/bf4reports-web-discovery.lock /bin/bash -c '
  echo "START $(date -u +%FT%TZ) persona=$1 platform=$2"
  /usr/bin/python3 -u /opt/bf4reports/player_discovery.py --personaid "$1" --platform "$2"
  result=$?
  echo "END $(date -u +%FT%TZ) exit=$result"
  exit "$result"
' bash "$1" "$2"