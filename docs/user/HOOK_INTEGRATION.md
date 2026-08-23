# Hook Integration: How VibeSOP Connects to Your AI Agent

## Overview

VibeSOP does **not** execute skills. It **routes** queries to the right skill and
**injects** the skill's instructions (SKILL.md) into your AI Agent's context. The
actual execution — reading files, writing code, running tests — is done by your
AI Agent (Claude Code, OpenCode, Kimi Code CLI, Cursor, Pi Agent).

VibeSOP is a **Skill Operating System** (route + orchestrate + lifecycle); the
Agent is the **executor**. This split is intentional and keeps VibeSOP
agent-agnostic.

## Architecture

```
          ┌─────────────┐
          │   You (CLI) │
          └──────┬──────┘
                 │ vibe route "debug this error"
          ┌──────▼──────┐
          │  VibeSOP    │  ← Routes to systematic-debugging (95%)
          │  SkillOS    │  ← Loads SKILL.md content
          └──────┬──────┘
                 │ Returns: skill_id + SKILL.md content
          ┌──────▼──────┐
          │ Hook Layer  │  ← handle_query_for_hook() (agent_runtime.py)
          │ adapters/   │  ← Packages result, injects into Agent context
          └──────┬──────┘
                 │ additionalContext → Agent reads it
          ┌──────▼──────┐
          │  AI Agent   │  ← Claude Code / OpenCode / Kimi / Cursor / Pi
          │  (Executor) │  ← Reads SKILL.md, performs the actual work
          └─────────────┘
```

## How it works

1. You run `vibe route "your task"` (or your Agent's UserPromptSubmit hook calls
   VibeSOP automatically).
2. VibeSOP routes to the best-matching skill and loads the skill content.
3. The hook layer (`handle_query_for_hook()` in `agent_runtime.py`) packages the
   result as JSON and injects it into the Agent's context via the platform
   adapter (`adapters/*.py`).
4. Your AI Agent reads the injected `additionalContext` and executes the skill's
   steps (file edits, tool calls, etc.).

## Prerequisites

- One of the supported AI Agents must be installed and on your `PATH`.
- Run `vibe doctor` to check **Platform Availability** — it shows which Agent
  CLIs VibeSOP detected.
- Run `vibe build <platform>` once to install hooks/rules into the Agent's
  config directory, then restart the Agent.

## Supported platforms

| Platform      | Adapter             | CLI binary  | Detection          |
|---------------|---------------------|-------------|--------------------|
| Claude Code   | `claude_code.py`    | `claude`    | `adapter.detect()` |
| OpenCode      | `opencode.py`       | `opencode`  | `adapter.detect()` |
| Kimi Code CLI | `kimi_cli.py`       | `kimi`      | `adapter.detect()` |
| Grok Build    | `grok_build.py`     | `grok`      | `adapter.detect()` |
| Cursor        | `cursor.py`         | `cursor`    | `adapter.detect()` |
| Pi Agent      | `pi_coding_agent.py`| `pi`        | `adapter.detect()` |

Each adapter exposes `is_available()` (bool) and `detect()` (path or None) via
`PlatformAdapter` in `adapters/base.py`.

**Grok Build hooks（gate33）:** 配置写在 `~/.grok/hooks/`。
`UserPromptSubmit` 调 `vibe route --hook`（stdin 事件 JSON → 路由结果注入）；
`PostToolUse` 采集工具序列到 `vibesop-tool-seq.json`（候选发现的 trace 数据源）。

## Quick start

```bash
# 1. Check which AI Agents are installed
vibe doctor

# 2. Route a query
vibe route "帮我调试这个错误"

# 3a. Hand off to your Agent (it reads the injected skill and executes):
#     - If using Claude Code with VibeSOP hooks installed, just type the query
#       into Claude Code; the UserPromptSubmit hook routes + injects automatically.
#     - Or pipe explicitly:
claude -p "$(vibe route '帮我调试这个错误' --json | jq -r '.primary.skill_id')"

# 3b. Or use guided mode (a step-by-step checklist you confirm by hand):
vibe route "帮我调试这个错误" --guided
```

## Guided vs. hand-off

- `--guided` (`-x`): VibeSOP prints the plan as a checklist and waits for you to
  mark each step done. **You** (or your Agent, separately) do the actual work.
  Useful when you want to drive execution yourself.
- **Hand-off** (default): VibeSOP routes and injects; your Agent executes
  end-to-end. This is the production path via the hook integration.

## Troubleshooting

- **"No platform available" / all adapters `not found` in `vibe doctor`**: install
  Claude Code, OpenCode, or another supported Agent and ensure it's on `PATH`.
- **"Skill content not injected"**: run `vibe build <platform>` to install the
  hooks/rules, then restart your Agent.
- **Route succeeds but the Agent doesn't execute**: confirm your Agent's config
  includes the VibeSOP hooks (see `vibe build --help`). The hook must fire on
  `UserPromptSubmit` (Claude Code) or the equivalent prompt entry point.
