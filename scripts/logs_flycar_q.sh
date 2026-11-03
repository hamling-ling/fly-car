#!/usr/bin/env bash
# Stream flycar_q logs to this terminal and to a file in logs/.
#
# Ctrl-C stops the stream. The file stays. Pass another destination when
# the board is not uno-q-1:
#
#   scripts/logs_flycar_q.sh
#   scripts/logs_flycar_q.sh arduino@other.local
#
# Run from anywhere. The default matches scripts/deploy_flycar_q.sh.

set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
host=${1:-arduino@uno-q-1.local}
remote=ArduinoApps/flycar_q
stamp=$(date +%Y%m%d-%H%M%S)
out=$root/logs/flycar_q-$stamp.log
mkdir -p "$root/logs"

frames=$root/logs/flycar_q-$stamp
echo "follow ${host}:~/${remote}"
echo "save ${out}"
echo "frames ${frames}/"
echo "Ctrl-C で切る。ログと、その行の img の JPEG が残る。"

ssh=(ssh -o BatchMode=yes -o ConnectTimeout=10)
pull() {
  mkdir -p "$frames"
  scp -o BatchMode=yes -o ConnectTimeout=10 \
    "$host:~/${remote}/frames/*.jpg" "$frames/" || true
}
trap pull EXIT
"${ssh[@]}" "$host" "arduino-app-cli app logs ~/${remote} --follow --tail 30" \
  | tee "$out"
