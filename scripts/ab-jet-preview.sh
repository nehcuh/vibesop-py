#!/usr/bin/env bash
# Start/stop the R5/R6 jet-engine teaching-lab preview servers.
# Usage: scripts/ab-jet-preview.sh start|stop|down|status|recover
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CACHE="$ROOT/.vibe/experiments/ab-jet-preview"
BIND="${AB_JET_BIND:-127.0.0.1}"
CONTAINERS=(vibesop-ab-treat vibesop-ab-ctrl vibesop-ab-base)

# R5 grok-4.6 treatment / control, R6 Qwen3.8-27B treatment
PORTS=(8801 8802 8803)
LABELS=(r5-treatment r5-control r6-treatment)

TREAT_SESSION="01a04be5-c146-7f63-bff2-577ab8191631"
CTRL_SESSION="01a04bf5-c7f9-7133-b04a-14db7d7ef85f"
TREAT_REWIND="/root/.grok/sessions/%2Fwork/${TREAT_SESSION}/rewind_points.jsonl"
CTRL_REWIND="/root/.grok/sessions/%2Fwork/${CTRL_SESSION}/rewind_points.jsonl"

need_cmd() { command -v "$1" >/dev/null || { echo "need $1" >&2; exit 1; }; }

port_pids() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN -t 2>/dev/null || true
}

is_up() {
  docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null | grep -q true
}

ensure_containers() {
  need_cmd docker
  local name
  for name in vibesop-ab-treat vibesop-ab-ctrl; do
    if ! docker inspect "$name" >/dev/null 2>&1; then
      echo "missing container $name (image vibesop-ab:base). do not docker rm these." >&2
      exit 1
    fi
    if ! is_up "$name"; then
      echo "starting $name"
      docker start "$name" >/dev/null
    fi
  done
}

extract_rewind() {
  local rewind_src="$1" dest="$2"
  python3 - "$rewind_src" "$dest" <<'PY'
import json, pathlib, sys
src, dest = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
obj = json.loads(src.read_text().splitlines()[0])
after = obj.get("after_snapshots") or {}
if not after:
    raise SystemExit(f"no after_snapshots in {src}")
dest.mkdir(parents=True, exist_ok=True)
n = 0
for rel, snap in after.items():
    content = snap.get("content")
    if content is None:
        raise SystemExit(f"snapshot {rel} has no content")
    path = dest / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    n += 1
print(f"extracted {n} files -> {dest}")
PY
}

copy_vendor() {
  local dest="$1"
  mkdir -p "$dest/vendor"
  docker cp vibesop-ab-treat:/tmp/ab-jet-seed/vendor/three.min.js "$dest/vendor/three.min.js"
}

cache_ok() {
  [[ -f "$CACHE/r5-treatment/index.html" && -f "$CACHE/r5-control/index.html" && -f "$CACHE/r6-treatment/index.html" ]]
}

recover() {
  ensure_containers
  mkdir -p "$CACHE/_source"
  rm -rf "$CACHE/r5-treatment" "$CACHE/r5-control" "$CACHE/r6-treatment"
  mkdir -p "$CACHE/r5-treatment" "$CACHE/r5-control" "$CACHE/r6-treatment"
  local tmp
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' RETURN
  docker cp "vibesop-ab-treat:${TREAT_REWIND}" "$tmp/r5-treat-rewind_points.jsonl"
  docker cp "vibesop-ab-ctrl:${CTRL_REWIND}" "$tmp/r5-ctrl-rewind_points.jsonl"
  cp "$tmp/r5-treat-rewind_points.jsonl" "$CACHE/_source/"
  cp "$tmp/r5-ctrl-rewind_points.jsonl" "$CACHE/_source/"
  extract_rewind "$CACHE/_source/r5-treat-rewind_points.jsonl" "$CACHE/r5-treatment"
  extract_rewind "$CACHE/_source/r5-ctrl-rewind_points.jsonl" "$CACHE/r5-control"
  copy_vendor "$CACHE/r5-treatment"
  copy_vendor "$CACHE/r5-control"
  docker cp vibesop-ab-treat:/work/index.html "$CACHE/r6-treatment/index.html"
  docker cp vibesop-ab-treat:/work/TASK.md "$CACHE/r6-treatment/TASK.md"
  docker cp vibesop-ab-treat:/work/css "$CACHE/r6-treatment/css"
  docker cp vibesop-ab-treat:/work/js "$CACHE/r6-treatment/js"
  docker cp vibesop-ab-treat:/work/test "$CACHE/r6-treatment/test"
  docker cp vibesop-ab-treat:/work/vendor "$CACHE/r6-treatment/vendor"
  echo "cache ready at $CACHE"
}

start_one() {
  local port="$1" dir="$2"
  local pids
  pids="$(port_pids "$port")"
  if [[ -n "$pids" ]]; then
    echo "port $port already listening (pid $pids)"
    return 0
  fi
  python3 -m http.server "$port" --bind "$BIND" -d "$dir" >/dev/null 2>&1 &
  echo "http://$BIND:$port/  <-  $dir  (pid $!)"
}

cmd_start() {
  need_cmd python3
  if ! cache_ok; then
    echo "cache missing; recovering from containers"
    recover
  fi
  start_one 8801 "$CACHE/r5-treatment"
  start_one 8802 "$CACHE/r5-control"
  start_one 8803 "$CACHE/r6-treatment"
  echo
  echo "R5 treatment (grok-4.6 + VibeSOP)  http://$BIND:8801/"
  echo "R5 control   (grok-4.6 bare)       http://$BIND:8802/"
  echo "R6 treatment (Qwen3.8-27B)         http://$BIND:8803/"
}

cmd_stop() {
  local port pids
  for port in "${PORTS[@]}"; do
    pids="$(port_pids "$port")"
    if [[ -n "$pids" ]]; then
      # shellcheck disable=SC2086
      kill $pids 2>/dev/null || true
      echo "stopped $port (pid $pids)"
    else
      echo "port $port idle"
    fi
  done
}

cmd_down() {
  cmd_stop
  need_cmd docker
  local name
  for name in "${CONTAINERS[@]}"; do
    if docker inspect "$name" >/dev/null 2>&1; then
      docker stop "$name" >/dev/null
      echo "stopped container $name"
    fi
  done
}

cmd_status() {
  local i port label pids
  echo "preview"
  for i in 0 1 2; do
    port="${PORTS[$i]}"
    label="${LABELS[$i]}"
    pids="$(port_pids "$port")"
    if [[ -n "$pids" ]]; then
      echo "  $label  http://$BIND:$port/  pid $pids"
    else
      echo "  $label  :$port idle"
    fi
  done
  echo "cache  $([[ -d $CACHE ]] && echo "$CACHE" || echo missing)"
  if cache_ok; then echo "  html present"; else echo "  html missing (run recover)"; fi
  if command -v docker >/dev/null; then
    echo "containers"
    docker ps -a --filter name=vibesop-ab --format '  {{.Names}}\t{{.Status}}'
  fi
}

usage() {
  cat <<EOF
usage: $0 start|stop|down|status|recover

  start    serve cached pages on 8801/8802/8803 (recover from docker if cache empty)
  stop     stop the three http.server processes
  down     stop preview + docker stop vibesop-ab-{treat,ctrl,base}
  status   ports, cache, containers
  recover  rebuild cache from container grok snapshots + /work

do not docker rm the ab containers — that is the last copy of R5 sessions and R6 /work.
EOF
}

case "${1:-}" in
  start) cmd_start ;;
  stop) cmd_stop ;;
  down) cmd_down ;;
  status) cmd_status ;;
  recover) recover ;;
  *) usage; exit 2 ;;
esac
