#!/usr/bin/env bash
# probe-inject.sh — dual-platform injection probe (gate46 §3).
#
# Headless equivalent of the dual-platform GIF: sends the same query through
# the real hook pipeline twice (claude-code / grok-build semantics) and
# asserts both produce the same [ACTIVE SKILL: builtin/...] injection.
# Exit 0 = both platforms inject identically; exit 1 = mismatch/failure.
#
# IMPORTANT: run with a CWD that has no core/skills checkout (e.g. /tmp) so
# the probe exercises the bundled-skill resolution a real user gets, not the
# dev repo's copy (gate46 v2 §3 wheel-replay requirement).

set -euo pipefail

QUERY="${1:-help me write a commit message}"
EXPECT_SKILL="${2:-builtin/commit-message}"
# Dev testing: VIBE_BIN="uv run --project /path/to/vibesop-py vibe" ./probe-inject.sh
VIBE_BIN="${VIBE_BIN:-vibe}"

probe() {
    local platform="$1"
    printf '{"prompt": "%s", "session_id": "probe-%s", "platform": "%s"}' \
        "$QUERY" "$platform" "$platform" \
        | $VIBE_BIN route --hook 2>/dev/null
}

echo "🔍 Query: $QUERY (expect: $EXPECT_SKILL)"
claude_out="$(probe claude-code)"
grok_out="$(probe grok-build)"

extract_marker() {
    # First [ACTIVE SKILL: ...] occurrence in additionalContext.
    printf '%s' "$1" | grep -o '\[ACTIVE SKILL: [^]]*\]' | head -1
}

claude_marker="$(extract_marker "$claude_out" || true)"
grok_marker="$(extract_marker "$grok_out" || true)"

fail=0
if [[ -z "$claude_marker" ]]; then
    echo "❌ claude-code lane: no [ACTIVE SKILL] marker in hook output"
    fail=1
else
    echo "✅ claude-code lane: $claude_marker"
fi
if [[ -z "$grok_marker" ]]; then
    echo "❌ grok-build lane: no [ACTIVE SKILL] marker in hook output"
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
