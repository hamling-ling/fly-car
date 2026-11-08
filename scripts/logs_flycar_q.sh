#!/usr/bin/env bash
# Stream flycar_q logs to this terminal and to a file in logs/.
#
# Ctrl-C stops the stream. The file stays. JPEGs in the board's frames/
# are copied into logs/, and each file whose local size matches is removed
# on the board. A short copy stays there. Pass another destination when
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
echo "Ctrl-C で切る。ログと JPEG が残る。コピーし終えた JPEG はボードから消す。"

ssh=(ssh -o BatchMode=yes -o ConnectTimeout=10)
pull() {
  mkdir -p "$frames"
  local listing size name local_size quoted i left
  local -a names=() sizes=() sources=() copied=()
  listing=$("${ssh[@]}" "$host" "cd ~/${remote}/frames && stat -c '%s %n' *.jpg" 2>/dev/null || true)
  if [[ -z "${listing}" ]]; then
    echo "frames: コピーする JPEG は無い。"
    return 0
  fi
  while IFS= read -r line; do
    [[ -n "$line" ]] || continue
    size=${line%% *}
    name=${line#* }
    names+=("$name")
    sizes+=("$size")
  done <<< "$listing"
  for name in "${names[@]}"; do
    sources+=("${host}:~/${remote}/frames/${name}")
  done
  scp -o BatchMode=yes -o ConnectTimeout=10 "${sources[@]}" "$frames/" || true
  for i in "${!names[@]}"; do
    name=${names[$i]}
    [[ -f "$frames/$name" ]] || continue
    local_size=$(stat -c '%s' "$frames/$name" 2>/dev/null || true)
    if [[ "$local_size" == "${sizes[$i]}" ]]; then
      copied+=("$name")
    fi
  done
  if ((${#copied[@]} == 0)); then
    echo "frames: コピーできた JPEG は無い。ボードの JPEG は残した。"
    return 0
  fi
  quoted=$(printf '%q ' "${copied[@]}")
  if "${ssh[@]}" "$host" "cd ~/${remote}/frames && rm -f -- ${quoted}"; then
    echo "frames: ${#copied[@]} 枚をコピーして、ボードから消した。"
  else
    echo "frames: ${#copied[@]} 枚はコピーした。ボードからの削除に失敗した。"
  fi
  left=$((${#names[@]} - ${#copied[@]}))
  if ((left > 0)); then
    echo "frames: ${left} 枚はコピーが揃わなかったのでボードに残した。"
  fi
}
trap pull EXIT
"${ssh[@]}" "$host" "arduino-app-cli app logs ~/${remote} --follow --tail 30" \
  | tee "$out"
