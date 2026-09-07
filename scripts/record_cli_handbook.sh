#!/usr/bin/env bash
# Record curated vibe CLI transcripts for docs/user/COMMAND_HANDBOOK.md.
# Default: docker image vibesop-val-base:py3.12. HOST=1 to record on the host.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/docs/user/cli-recordings"
IMAGE="${VIBESOP_HANDBOOK_IMAGE:-vibesop-val-base:py3.12}"
mkdir -p "$OUT"

run_vibe() {
  local name="$1"; shift
  local file="$OUT/${name}.txt"
  if [[ "${HOST:-0}" == "1" ]]; then
    (cd "$ROOT" && HF_HUB_OFFLINE=1 NO_COLOR=1 COLUMNS=88 uv run vibe "$@") \
      >"$file" 2>&1 || true
  else
    docker run --rm \
      -v "$ROOT":/repo -w /repo \
      -e HF_HUB_OFFLINE=1 -e NO_COLOR=1 -e COLUMNS=88 \
      "$IMAGE" \
      uv run --frozen vibe "$@" \
      >"$file" 2>&1 || true
  fi
  # Drop uv install noise; keep from first box/Usage/VibeSOP line.
  python3 - "$file" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1])
text = p.read_text(encoding="utf-8", errors="replace")
for marker in ("╭", "Usage:", "VibeSOP", "Skill", "No matching"):
    i = text.find(marker)
    if i != -1:
        text = text[i:]
        break
p.write_text(text.rstrip() + "\n", encoding="utf-8")
print(f"recorded {p.name} ({p.stat().st_size} bytes)")
PY
}

run_vibe version version
run_vibe doctor doctor
run_vibe status status
run_vibe route-weather route "今天天气怎么样"
run_vibe route-wechat route "写公众号总结"
run_vibe route-explicit route "use builtin/session-end"
run_vibe skills-list skills list
run_vibe skills-info skills info builtin/session-end
run_vibe help-route help route
run_vibe man-route man route
run_vibe orchestrate-help orchestrate --help
run_vibe skills-help skills --help
echo "done -> $OUT"
