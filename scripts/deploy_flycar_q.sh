#!/usr/bin/env bash
# Stop flycar_q on the Uno Q, copy this tree, and start it again.
#
# The sketch cache on the board is left in place. Pass another destination
# when the board is not uno-q-1:
#
#   scripts/deploy_flycar_q.sh arduino@other.local
#
# Run from anywhere. The default matches research/camera_capture_q.

set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
host=${1:-arduino@uno-q-1.local}
remote=ArduinoApps/flycar_q
ssh=(ssh -o BatchMode=yes -o ConnectTimeout=10)

echo "stop ${host}:~/${remote}"
"${ssh[@]}" "$host" "arduino-app-cli app stop ~/${remote}" || true

echo "copy src/flycar_q"
tar -C "$root/src/flycar_q" \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.cache' \
  -cf - . \
  | "${ssh[@]}" "$host" "mkdir -p ~/${remote} && tar -C ~/${remote} -xf -"

echo "copy src/flycar"
"${ssh[@]}" "$host" "rm -rf ~/${remote}/python/flycar"
tar -C "$root/src" \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  -cf - flycar \
  | "${ssh[@]}" "$host" "tar -C ~/${remote}/python -xf -"

"${ssh[@]}" "$host" "find ~/${remote} -type d -name __pycache__ -prune -exec rm -rf {} +"

echo "start ${host}:~/${remote}"
"${ssh[@]}" "$host" "arduino-app-cli app start ~/${remote}"
