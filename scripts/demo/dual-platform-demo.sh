#!/usr/bin/env bash
# dual-platform-demo.sh — tmux layout for the block-2 aha GIF (gate46 §2).
#
# Two panes side by side: Claude Code (left) and Grok Build (right). The
# same intent is typed into both; both inject the same skill. This is the
# "install once, alive everywhere" evidence — record it with:
#
#  scripts/demo/dual-platform-demo.sh | recording per docs/demo-recording-guide.md
#
# Prereqs: tmux; Claude Code + Grok Build installed with VibeSOP hooks
# deployed (vibe build claude-code --output ~/.claude && vibe build
# grok-build --output ~/.grok), both agents restarted.

set -euo pipefail

QUERY="${1:-help me write a commit message}"
SESSION="vibesop-demo"

tmux kill-session -t "$SESSION" 2>/dev/null || true
tmux new-session -d -s "$SESSION" -n demo

# Split into two panes: left = Claude Code, right = Grok Build
tmux split-window -h -t "$SESSION:demo.0"

tmux send-keys -t "$SESSION:demo.0" "claude" Enter
tmux send-keys -t "$SESSION:demo.1" "grok" Enter

echo "两位 agent 启动中… 等 ~5s 后发送同一句意图"
sleep 5

# Same intent, both panes, visibly staggered for the recording.
tmux send-keys -t "$SESSION:demo.0" "$QUERY" Enter
sleep 1
tmux send-keys -t "$SESSION:demo.1" "$QUERY" Enter

cat <<EOF
tmux 会话 "$SESSION" 已就绪：
  左 pane  = Claude Code
  右 pane  = Grok Build
  同一句: "$QUERY"

观察点（录进 GIF 的核心证据）：
  1. 两边都出现 VibeSOP routed → 同一个 builtin 技能
  2. 两边都注入 [ACTIVE SKILL: ...] 上下文
  3. agent 按技能步骤行动（读 SKILL.md / 按 workflow 走）——证明行为变好，
     不只是注入发生

停止: tmux kill-session -t $SESSION
EOF
