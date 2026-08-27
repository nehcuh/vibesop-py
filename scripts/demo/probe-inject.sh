#!/usr/bin/env bash
# probe-inject.sh — dual-platform injection probe (gate46 §3 / S51 M5).
#
# Claude lane: explicit --platform claude-code (CLI flag, not a JSON field).
# Grok lane: deployed command shape — no --platform, camelCase envelope
# without a platform key (the real Grok host does not send one).
#
# IMPORTANT: run with a CWD that has no core/skills checkout (e.g. /tmp) so
# the probe exercises the bundled-skill resolution a real user gets.

set -euo pipefail

QUERY="${1:-help me write a commit message}"
EXPECT_SKILL="${2:-builtin/commit-message}"
VIBE_BIN="${VIBE_BIN:-vibe}"

_py() {
    if command -v python3 >/dev/null 2>&1; then python3 "$@"
    elif command -v python >/dev/null 2>&1; then python "$@"
    else uv run --no-project python "$@"
    fi
}

json_envelope() {
    # argv, not string interpolation: Windows Git-Bash + quotes in QUERY.
    _py -c 'import json,sys; print(json.dumps({"userPrompt": sys.argv[1], "sessionId": sys.argv[2]}))' "$1" "$2"
}

echo "🔍 Query: $QUERY (expect: $EXPECT_SKILL)"
claude_out="$(json_envelope "$QUERY" "probe-claude" | $VIBE_BIN route --hook --platform claude-code)"
grok_out="$(json_envelope "$QUERY" "probe-grok" | $VIBE_BIN route --hook)"

extract_marker() {
    printf '%s' "$1" | grep -o '\[ACTIVE SKILL: [^]]*\]' | head -1
}

claude_marker="$(extract_marker "$claude_out" || true)"
grok_marker="$(extract_marker "$grok_out" || true)"

fail=0
if [[ -z "$claude_marker" ]]; then
    echo "❌ claude-code lane: no [ACTIVE SKILL] marker in hook output"
    echo "$claude_out" | tail -20
    fail=1
else
    echo "✅ claude-code lane: $claude_marker"
fi
if [[ -z "$grok_marker" ]]; then
    echo "❌ grok-build lane: no [ACTIVE SKILL] marker in hook output"
    echo "$grok_out" | tail -20
    fail=1
else
    echo "✅ grok-build lane: $grok_marker"
fi
if [[ "$claude_marker" != "$grok_marker" ]]; then
    echo "❌ marker mismatch between platforms"
    fail=1
fi
if [[ "$claude_marker" != "[ACTIVE SKILL: $EXPECT_SKILL]" ]]; then
    echo "⚠️  routed skill differs from expectation (got: $claude_marker)"
    fail=1
fi

if [[ "$fail" -ne 0 ]]; then
    echo "PROBE FAILED"
    exit 1
fi
echo "PROBE PASSED — both platforms inject the same skill"
