#!/usr/bin/env bash
# Stop flycar_q on the Uno Q, copy this tree, and start it again.
#
# Python and python/flycar are bind-mounted at /app, so a Python-only
# copy runs on the next start. app.yaml and sketch/ are hashed. When
# that hash matches ~/ArduinoApps/flycar_q/.sketch-hash the sketch
# cache stays, and start reuses the build and the venv. A different
# hash, a leftover .sketch-hash.pending from a wipe whose start did
# not finish, or --rebuild removes .cache so the next start compiles.
# The stamp is written only after app start succeeds. A missing stamp
# keeps the cache: the last deploy already compiled this sketch.
# app start refuses while a container for this app is still running,
# and app stop can report success after resetting the microcontroller
# with that container left up. Remove it before start.
#
#   scripts/deploy_flycar_q.sh
#   scripts/deploy_flycar_q.sh --rebuild
#   scripts/deploy_flycar_q.sh arduino@other.local
#   scripts/deploy_flycar_q.sh --rebuild arduino@other.local
#
# Run from anywhere. The default matches research/camera_capture_q.

set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
rebuild=0
host=arduino@uno-q-1.local
for arg in "$@"; do
  case "$arg" in
    --rebuild) rebuild=1 ;;
    -*)
      echo "unknown option: ${arg}" >&2
      exit 2
      ;;
    *) host=$arg ;;
  esac
done
remote=ArduinoApps/flycar_q
ssh=(ssh -o BatchMode=yes -o ConnectTimeout=10)

sketch_hash=$(
  tar -C "$root/src/flycar_q" \
    --sort=name \
    --mtime='@0' \
    --owner=0 \
    --group=0 \
    --numeric-owner \
    -cf - app.yaml sketch \
    | sha256sum \
    | awk '{print $1}'
)
if [[ ! "$sketch_hash" =~ ^[0-9a-f]{64}$ ]]; then
  echo "sketch hash failed" >&2
  exit 1
fi

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

echo "sketch cache ${host}:~/${remote}/.cache"
"${ssh[@]}" "$host" "sh -s -- ${sketch_hash} ${rebuild}" <<'EOF'
set -eu
want=$1
rebuild=$2
remote=$HOME/ArduinoApps/flycar_q
stamp=$remote/.sketch-hash
pending=$remote/.sketch-hash.pending
wipe=0
if [ "$rebuild" = 1 ]; then
  echo "rebuild: clear sketch cache"
  wipe=1
elif [ -f "$pending" ]; then
  echo "previous compile did not finish: clear sketch cache"
  wipe=1
elif [ -f "$stamp" ]; then
  got=$(tr -d '[:space:]' < "$stamp")
  if [ "$got" != "$want" ]; then
    echo "sketch changed: clear sketch cache"
    wipe=1
  else
    echo "sketch unchanged: keep cache"
  fi
else
  echo "sketch cache kept (no stamp yet)"
fi
if [ "$wipe" = 1 ]; then
  rm -rf "$remote/.cache"
  printf '%s\n' "$want" > "$pending"
fi
EOF

echo "remove leftover container ${host}:~/${remote}"
"${ssh[@]}" "$host" "{
  docker ps -aq --filter label=cc.arduino.app.path=\"\$HOME/${remote}\"
  docker ps -aq --filter name=flycar_q
  docker ps -aq --filter name=flycar-q
} | sort -u | xargs -r docker rm -f"

echo "start ${host}:~/${remote}"
"${ssh[@]}" "$host" "arduino-app-cli app start ~/${remote} && printf '%s\n' '${sketch_hash}' > ~/${remote}/.sketch-hash && rm -f ~/${remote}/.sketch-hash.pending"
