# VibeSOP CLI Reference

Complete reference for all VibeSOP CLI commands (v8.0.0+).

---

## Table of Contents

- [Core Commands](#core-commands)
  - [`vibe route`](#vibe-route)
  - [`vibe status`](#vibe-status-v530)
  - [`vibe dashboard`](#vibe-dashboard-v80)
  - [`vibe orchestrate`](#vibe-orchestrate)
  - [`vibe decompose`](#vibe-decompose)
  - [`vibe doctor`](#vibe-doctor)
  - [`vibe version`](#vibe-version)
  - [`vibe install`](#vibe-install)
  - [`vibe market`](#vibe-market)
  - [`vibe sequence`](#vibe-sequence)
  - [`vibe conversation`](#vibe-conversation)
  - [`vibe data purge`](#vibe-data-purge)
- [Skills Management](#skills-management)
  - [`vibe skills`](#vibe-skills)
  - [`vibe skills distill`](#vibe-skills-distill-suggestion-id)
  - [`vibe skill cleanup`](#vibe-skill-cleanup-v530)
  - [`vibe skill stale`](#vibe-skill-stale)
  - [`vibe skill end-check`](#vibe-skill-end-check-v510)
  - [`vibe skills suggestions`](#vibe-skills-suggestions-v510)
  - [`vibe skill scan-candidates`](#vibe-skill-scan-candidates-v810)
  - [`vibe skill candidates`](#vibe-skill-candidates-v810)
  - [`vibe skill discover`](#vibe-skill-discover-v810)
  - [`vibe skill discover dismiss`](#vibe-skill-discover-dismiss-v810)
  - [`vibe skill promote`](#vibe-skill-promote-v810)
  - [`vibe skill dismiss`](#vibe-skill-dismiss-v810)
- [Autonomous Loops](#autonomous-loops)
  - [`vibe loop`](#vibe-loop-v810)
  - [`vibe loop create`](#vibe-loop-create-v810)
  - [`vibe loop list`](#vibe-loop-list-v810)
  - [`vibe loop show`](#vibe-loop-show-v810)
  - [`vibe loop pause / resume / reset`](#vibe-loop-pause--resume--reset-v810)
  - [`vibe loop delete`](#vibe-loop-delete-v810)
  - [`vibe loop adopt`](#vibe-loop-adopt-v810)
  - [`vibe loop migrate-ownership`](#vibe-loop-migrate-ownership-v810)
  - [`vibe loop tick`](#vibe-loop-tick-v810)
  - [`vibe loop install-launchd`](#vibe-loop-install-launchd-v810)
  - [`vibe loop uninstall-launchd`](#vibe-loop-uninstall-launchd-v810)
- [Project Setup](#project-setup)
- [Platform & Utility Commands](#platform--utility-commands)
- [Analysis Commands](#analysis-commands)
- [Configuration](#configuration)
- [LLM Configuration](#llm-configuration)
- [Preference Learning](#preference-learning)
- [Experimental Commands](#experimental-commands)
- [Command Summary](#command-summary)
- [Environment Variables](#environment-variables)
- [Exit Codes](#exit-codes)

---

## Core Commands

### `vibe route`

Route a natural language query to the appropriate skill(s).

By default, VibeSOP will:
1. Detect if your query contains multiple intents
2. Decompose complex requests into sub-tasks
3. Build an execution plan with optimal skill selection
4. Show a summary for confirmation

> **Note**: VibeSOP routes queries and injects skill instructions only. Skill
> execution (code changes, file writes, tool calls) is performed by an external
> AI Agent (Claude Code, OpenCode, etc.). Use `--guided` for step-by-step
> guidance, or hand the plan off to your Agent. See
> [Hook Integration](HOOK_INTEGRATION.md).

```bash
vibe route <query> [options]
```

**Arguments:**
- `query` - Natural language query (required)

**Options:**
- `--min-confidence, -c` - Minimum confidence threshold (0.0-1.0)
- `--json, -j` - Output as JSON
- `--validate, -V` - Validate routing configuration
- `--explain, -e` - Explain full routing decision tree with per-layer diagnostics, multi-intent analysis, and execution flow
- `--no-session` - Disable session-state-aware routing for this query
- `--yes, -y` - Skip confirmation prompt
- `--guided, -x` - Interactive step-by-step guided execution mode (prints a plan checklist; you or your Agent perform the actual execution)
- `--strategy, -s` - Force execution strategy: auto, sequential, parallel, hybrid
- `--hook` - Hook mode: read the host agent's hook event JSON from stdin instead of a query argument (gate33; deployed as the Grok Build `UserPromptSubmit` JSON hook). Prints the hook response envelope and always exits 0

**Examples:**
```bash
# Basic routing (auto-detects single vs multi-intent)
vibe route "help me debug this error"

# Multi-intent orchestration
vibe route "analyze architecture and write tests"

# With confidence threshold
vibe route "review my code" --min-confidence 0.8

# JSON output
vibe route "test this" --json

# Skip confirmation
vibe route "deploy to production" --yes

# Explain routing decision
vibe route "debug" --explain

# Disable session awareness for one-off query
vibe route "debug" --no-session
```

**Single Intent Output:**
```
🔍 Routing Summary
─────────────────────────────
Selected     systematic-debugging
Confidence   95%
Layer        scenario
Duration     12.3ms

💡 Alternatives:
   • gstack/investigate (82%)
   • superpowers/debug (75%)
```

**Multi Intent Output:**
```
🔍 Routing Summary
─────────────────────────────
Mode         Orchestrated
Steps        2
Strategy     sequential

Plan:
  1. riper-workflow — architecture analysis
  2. superpowers/test — test generation

[✅ Confirm] [✏️ Edit] [🔀 Single skill] [📝 Skip]
```

---

### `vibe orchestrate`

Explicitly orchestrate a complex query into an execution plan.

This is the explicit entry point for multi-intent orchestration. For simple queries, `vibe route` is sufficient and will auto-detect orchestration needs.

```bash
vibe orchestrate <query> [options]
```

**Arguments:**
- `query` - Complex natural language query with multiple intents (required)

**Options:**
- `--json, -j` - Output as JSON
- `--verbose, -v` - Show full decomposition and planning details
- `--strategy, -s` - Force execution strategy: auto, sequential, parallel, hybrid
- `--conversation, -C` - Conversation ID for multi-turn context

**Examples:**
```bash
# Orchestrate a complex request
vibe orchestrate "analyze architecture, review code, and write tests"

# JSON output for scripting
vibe orchestrate "refactor and add documentation" --json

# Force sequential strategy
vibe orchestrate "design API then implement endpoints" --strategy sequential
```

---

### `vibe decompose`

Decompose a query into sub-tasks without routing to skills.

Shows detected intents and proposed sub-tasks, but does not match them to skills or build an execution plan. Useful for understanding how VibeSOP interprets complex queries.

```bash
vibe decompose <query> [options]
```

**Arguments:**
- `query` - Natural language query to decompose (required)

**Options:**
- `--json, -j` - Output as JSON

**Examples:**
```bash
# Decompose a query
vibe decompose "先分析架构，再写测试，最后部署"

# JSON output
vibe decompose "review code and fix bugs" --json
```

---

### `vibe doctor`

Check environment and configuration health.

```bash
vibe doctor
```

**Checks:**
- Python version (3.12+)
- Dependencies installed
- Configuration files
- LLM provider API keys
- Platform integrations
- Hook status

**Example:**
```bash
$ vibe doctor

🔍 Checking VibeSOP environment...

✅ Python version: 3.12.1
✅ Dependencies: All installed
✅ Configuration: Found at .vibe/
✅ LLM Provider: Anthropic (API key found)
⚠️  Platform Integrations: No integrations installed (0/5)
⚠️  Hook Status: claude-code: 0/2; kimi-cli: not installed; opencode: not installed

⚠️  Some checks failed. Please fix the issues above.
```

---

### `vibe version`

Show version information.

```bash
vibe version
```

---

### `vibe install`

Install skill packs from URLs or registries.

```bash
vibe install <source> [options]
```

**Arguments:**
- `source` - URL, path, or registry name (e.g., "gstack", "superpowers")

**Options:**
- `--force, -f` - Force reinstall if already installed
- `--upgrade` - Accept a pack whose commit or content changed since the last install (F-02)
- `--scope` - Install scope: `global` (default, `~/.config/skills/` + platform symlinks) or `project` (`.vibe/skills/` in the current project only; runs the same security chain, skips platform symlinks and the global index)
- `--skip-verify` - Skip post-install verification
- `--allow-unsafe-build` - Allow local (non-container) build-script execution after interactive confirmation (F-03)
- `--platform, -p` - Target platform for skill symlinks (`claude-code`, `kimi-cli`, `opencode`, `cursor`, `pi`, or `all`)
- `--list, -l` - List available skill packs
- `--auto, -a` - Auto-install recommended skill packs

**Examples:**
```bash
# Install from registry shorthand
vibe install gstack

# Install from URL
vibe install https://github.com/anthropics/gstack

# Force reinstall
vibe install gstack --force

# Accept a changed pack after reviewing the diff
vibe install gstack --upgrade

# Allow local build scripts after explicit interactive confirmation
vibe install gstack --allow-unsafe-build

# Install into the current project only (.vibe/skills/)
vibe install https://github.com/mattpocock/skills --scope project
```

### `vibe market`

Search and install skills from the **public GitHub skill ecosystem** (topics `agent-skills`, `claude-skills`, etc., stars-sorted) plus curated awesome lists. Results are tiered: official (built-in trusted packs) → curated (awesome lists) → unknown (clearly flagged, install requires confirmation).

```bash
vibe market <command> [options]
```

**Commands:**
- `search <query>` - Search the public ecosystem; results show trust tier, stars, and install command. `--json` for machine-readable output, `--page N` for paging
- `trending <category>` - Trending repos for a category (`agent` → agent-skills, `claude` → claude-skills, `claude-code` → claude-code-skills, `skill-md`; any other value is used as the topic directly)
- `install <owner/repo>` - Install from a GitHub repo (validates the repo contains SKILL.md files). Options: `--scope global|project`, `--yes`

**Examples:**
```bash
# Search for code review skills
vibe market search "code review"

# See what is trending in the agent-skills topic
vibe market trending agent

# Install into the current project only
vibe market install mattpocock/skills --scope project
```

> **Note**: unauthenticated GitHub API is rate-limited (10 req/min search); set `GITHUB_TOKEN` or `GH_TOKEN` for reliable use. Search results are cached for 24h (5 min on partial failure).

### `vibe sequence`

Manage captured tool-call sequences used by workflow-pattern learning (task distillation).

```bash
vibe sequence <command>
```

**Commands:**
- `record-tool` - Record one tool call from a host agent's `PostToolUse` hook (reads the hook JSON from stdin; stores only tool name + timestamp + session id — never `tool_input`). Wired by the Claude Code (`vibesop-tool-seq.sh`), Kimi CLI (same script), and Grok Build (`vibesop-tool-seq.json`, gate33) adapters
- `assemble` - Assemble recorded tool events into sequences (grouped by session, 30-min window fallback) and feed them to the instinct learner (`record_sequence`, application-only weight)

**Related:** the Claude Code / Kimi CLI adapters ship the `vibesop-tool-seq.sh` hook and the Grok Build adapter ships `vibesop-tool-seq.json` (installed when `sequences.enabled` is true) which pipe PostToolUse events to `vibe sequence record-tool`. Captured data lives in `.vibe/tool_sequences.jsonl` (rotated at 10MB) and can be removed with `vibe data purge --tool-sequences`.

### `vibe conversation`

Mirror Claude Code conversations into `.vibe/conversations/<id>.json` so they appear in the dashboard's Conversations tab. Two complementary paths:

```bash
vibe conversation <command>
```

**Commands:**
- `import-claude` - Batch-import one or more Claude Code transcript `.jsonl` files. Auto-discovers `~/.claude/projects/<escaped-cwd>/*.jsonl` when `--source` is empty. Idempotent (re-importing a growing session adds only new turns). Use `--all-sessions` to import every file in a directory as a separate conversation.
- `append-turn` - Real-time hook entry point (reads JSON from stdin). Dispatches `UserPromptSubmit` → user turn, `PostToolUse` → tool turn (only stores tool name + input keys, **never** `tool_input` values). Always exits 0 — hook contract. Fail-open on malformed input.

**Options (import-claude):**
- `--source <path>` - File or directory. Empty = auto-discover.
- `--conversation-id <id>` - Empty = `mirror-claude-<jsonl-stem>`.
- `--storage-dir <path>` - Default `.vibe/conversations`.
- `--all-sessions` - Import every `.jsonl` in directory as its own conversation.

**Related:** the Claude Code adapter ships two opt-in hooks (`vibesop-mirror-prompt.sh` + `vibesop-mirror-session-end.sh`) when `conversation_mirror.enabled = true` in `.vibe/config.toml`. **Default false** (opt-in, since mirror captures user prompts which may contain secrets). The SessionEnd hook triggers a full `import-claude` for the just-ended session — this is the only way to surface assistant responses (Claude Code has no real-time assistant hook). Mirror data is already covered by `.gitignore:122` (`.vibe/conversations/`).

### `vibe data purge`

Permanently delete VibeSOP-derived data, including analytics, traces, preferences, instincts, memory, sessions, feedback, and pack install locks (F-08 + F-02).

```bash
vibe data purge [options]
```

**Options:**
- `--all` - Purge ALL VibeSOP-derived data
- `--analytics` - Purge `.vibe/analytics.jsonl`
- `--traces` - Purge `.vibe/traces/*.json`
- `--preferences` - Purge learned preferences
- `--instincts` - Purge learned instincts
- `--memory` - Purge conversation memory
- `--sessions` - Purge `.vibe/session/*.json`
- `--feedback` - Purge feedback records
- `--pack-locks` - Purge pack install locks (`~/.config/skills/.pack-locks/`)
- `--miss-counter` - Purge the no-match query counter (`.vibe/miss_counter.json`; the salt is kept)
- `--tool-sequences` - Purge captured tool sequences (`.vibe/tool_sequences.jsonl` + cursor + rotation)
- `-y, --yes` - Skip the confirmation prompt
- `--project-root` - Project root (where `.vibe/` lives)

**Examples:**
```bash
# Purge everything
vibe data purge --all

# Purge only analytics and traces
vibe data purge --analytics --traces

# Reset pack install locks after a force-push review
vibe data purge --pack-locks --yes
```

---

## Skills Management

### `vibe skills`

Manage skills with subcommands.

#### `vibe skills available`

List all available skills from all sources.

```bash
vibe skills available [options]
```

**Options:**
- `--namespace, -n` - Filter by namespace
- `--verbose, -v` - Show detailed information

**Examples:**
```bash
# List all skills
vibe skills available

# Filter by namespace
vibe skills available --namespace gstack

# Show details
vibe skills available --verbose
```

#### `vibe skills list`

List installed skills from central storage.

```bash
vibe skills list [options]
```

**Options:**
- `--platform, -p` - Filter by platform
- `--all, -a` - Show detailed information

#### `vibe skills info <id>`

Show detailed information about a skill.

```bash
vibe skills info <skill-id>
```

**Example:**
```bash
vibe skills info systematic-debugging
vibe skills info gstack/review
```

#### `vibe skills distill [<suggestion-id>]`

Distill a mature workflow pattern (sequence suggestion) into a real SKILL.md via LLM. Flow: consent gate (shows which provider/model receives the redacted inputs) → full-text review (save / edit in `$EDITOR` / discard) → security audit of the exact final bytes (CRITICAL blocks; **any threat blocks `--yes`**; interactive second confirm otherwise) → writes to `.vibe/skills/custom/<name>/SKILL.md` (project scope) → marks the suggestion as created.

```bash
vibe skills distill [<suggestion-id>] [--yes] [--template]
```

**Options:**
- `--yes` - Skip all prompts (a fully clean security audit is still required)
- `--template` - Use the template generator instead of an LLM

**Example:**
```bash
# List suggestions, then distill one
vibe skills suggestions
vibe skills distill sug_f4fb99e5ab5a
```

#### `vibe skills install <id>`

Install a skill to central storage.

```bash
vibe skills install <skill-id> [options]
```

**Options:**
- `--source, -s` - Local path to skill directory
- `--url, -u` - Remote URL to download skill from
- `--force, -f` - Overwrite if already exists

#### `vibe skills link <id> <platform>`

Link a skill to a platform.

```bash
vibe skills link <skill-id> <platform> [options]
```

**Options:**
- `--force, -f` - Overwrite existing link

**Example:**
```bash
vibe skills link systematic-debugging claude-code
```

#### `vibe skills unlink <id> <platform>`

Unlink a skill from a platform.

```bash
vibe skills unlink <skill-id> <platform>
```

#### `vibe skills remove <id>`

Remove a skill from central storage.

```bash
vibe skills remove <skill-id>
```

#### `vibe skills sync <platform>`

Sync all project skills to a platform.

```bash
vibe skills sync <platform> [options]
```

**Options:**
- `--root, -r` - Project root directory
- `--force, -f` - Overwrite existing links

**Example:**
```bash
vibe skills sync claude-code
```

#### `vibe skills status`

Show skill storage status.

```bash
vibe skills status
```

---

#### `vibe skills health`

Check skill pack health status.

```bash
# Check all skill packs
vibe skills health

# Check specific pack
vibe skills health --pack gstack

# Show detailed information
vibe skills health --verbose
```

**Options**:
- `--pack`, `-p`: Check specific skill pack only
- `--verbose`, `-v`: Show detailed health information

**Health Status**:
- ✓ **healthy**: All checks passed
- ⚠ **warning**: Minor issues (e.g., fewer skills than expected)
- ✗ **critical**: Major issues (e.g., missing files, missing required fields)

**Checks Performed**:
- SKILL.md file presence
- Required fields (id, name, description, intent)
- File integrity (encoding, size)
- Version consistency

---

#### `vibe skills report`

Show skill quality report with grades and routing impact.

```bash
vibe skills report [options]
```

**Options:**
- `--grade, -g` - Filter by grade (A, B, C, D, F, ?)
- `--suggest-removal` - Show only skills recommended for removal (grade F)

**Examples:**
```bash
# Show all skills with grades
vibe skills report

# Show only skills needing attention
vibe skills report --grade D

# Show skills recommended for removal
vibe skills report --suggest-removal
```

**Output:**
```
┌─────────────────────┬───────┬───────┬────────┬─────────┬────────────┬────────────────┐
│ Skill               │ Grade │ Score │ Routes │ Success │ User Score │ Routing Impact │
├─────────────────────┼───────┼───────┼────────┼─────────┼────────────┼────────────────┤
│ gstack/review       │ ✅ A  │  0.92 │     45 │   91.1% │       4.5  │ +0.05 boost    │
│ systematic-debugging│ ✓ C   │  0.71 │     12 │   75.0% │       3.8  │ no change      │
│ old-deploy-skill    │ 🗑️ F  │  0.31 │      3 │   33.3% │       1.2  │ -0.05 demote   │
└─────────────────────┴───────┴───────┴────────┴─────────┴────────────┴────────────────┘
```

Grades affect routing confidence:
- **A** (+0.05 boost): High-quality skills get priority
- **B** (+0.02 boost): Slight preference
- **C** (no change): Neutral
- **D** (-0.02 demote): Slight deprioritization
- **F** (-0.05 demote): Low-quality skills are avoided
- **?** (no routing data): Shown when a skill has zero routing feedback.
  Score displays as "—" (not 0%) — no data is NOT a bad score. Grade "?"
  never triggers deprecation/archive suggestions. Note: routing-confidence
  adjustments only apply with >=3 explicit feedback records.

> **Note:** Impact only applies when a skill has `>= 3` total routes (insufficient data otherwise).

---

#### `vibe skills scope`

Show or change the scope of a skill (global vs project).

```bash
vibe skills scope <skill-id> [options]
```

**Arguments:**
- `skill-id` - Skill to modify

**Options:**
- `--set, -s` - Set scope to `global` or `project`

**Examples:**
```bash
# Show current scope
vibe skills scope gstack/review

# Change to project-only
vibe skills scope gstack/review --set project
```

---

#### `vibe skills feedback`

Record post-execution feedback for a skill to improve routing quality.

```bash
vibe skills feedback [options]
```

**Options:**
- `--skill` - Skill ID (required)
- `--query` - Original query that routed to this skill
- `--helpful, -h` - Was the skill helpful? (`yes`/`no`)
- `--success` - Did execution succeed? (`yes`/`no`)
- `--time, -t` - Execution time in milliseconds
- `--notes, -n` - Optional notes

**Examples:**
```bash
# Mark as helpful
vibe skills feedback --skill gstack/review --query "review code" --helpful yes

# Report failure with details
vibe skills feedback --skill gstack/review --query "review code" --success no --notes "missed edge case"
```

---

### `vibe skill` (Lifecycle Management)

Manage skill lifecycle states: enable, disable, and check status.

#### `vibe skill list`

List all skills with their lifecycle state and read-only health summary
columns (gate37 L2-lite).

```bash
vibe skill list [options]
```

**Options:**
- `--all, -a` - Show all skills including archived
- `--project, -p` - Show only project-scoped skills

**Examples:**
```bash
# List active skills
vibe skill list

# Show all skills including archived
vibe skill list --all

# Show only project-scoped skills
vibe skill list --project
```

**Output:**
```
┌──────────────────────┬─────────────────┬────────┬─────────┬─────────┬─────────┬──────────┬───────────┐
│ ID                   │ Name            │ State  │ Scope   │ Version │ Source¹ │ Fire 30d²│ Feedback³ │
├──────────────────────┼─────────────────┼────────┼─────────┼─────────┼─────────┼──────────┼───────────┤
│ gstack/review        │ Code Review     │ active │ global  │ 2.1.0   │ builtin │        3 │ +2/-1     │
│ systematic-debugging │ Debug Workflow  │ active │ global  │ 1.5.0   │ builtin │        0 │ no records│
│ old-deploy-skill     │ Deploy Helper   │ deprecated│ global │ 0.9.0  │ external│        0 │ no records│
└──────────────────────┴─────────────────┴────────┴─────────┴─────────┴─────────┴──────────┴───────────┘
```

**Health columns (raw facts only — no rates, no derived actions):**
- `Source¹` — `builtin` / `project` / `external` (pack-installed skills
  fold into `external`; promoted/hand-installed skills carry no
  provenance data and are not specially labelled).
- `Fire 30d²` — route hits in **this project's** spans over the last 30
  days, CLI path included. Raw counts only — **n<30 proves nothing**.
  Renaming or reinstalling a skill resets its history; `/` vs `-` id
  normalisation also breaks the chain. Route outcomes
  (`route_outcomes.jsonl`, gate38) cover the **hook path only** — do NOT
  combine them with this column into a "fire → success rate"; the two
  populations are disjoint by design.
- `Feedback³` — raw yes/no counts from project-level explicit feedback.
  "partial" is recorded as "no". `no records` means no feedback exists —
  it is NOT a neutral signal. `vibe skills feedback` writes to the global
  store (a known gap) and is not counted here.

---

#### `vibe skill lint`

Advisory static checks on a skill (gate37 L1). Three plain-language
checks: triggers declared and not all machine-prompt-shaped, no unedited
auto-draft TODO skeleton left in the body, description present (≥10
chars). **Advisory only** — findings never block anything and the exit
code is always 0. The same checks also run during `vibe skill add` and
pack installs: when an install actually happens, the lint findings ride
the install's `warnings`/advisory output (an already-installed skill
returns early and is not re-linted).

```bash
vibe skill lint <path>
```

**Example:**
```bash
vibe skill lint ./skills/my-skill
```

**Output:**
```
⚠ ./skills/my-skill: 1 advisory finding(s)
  • No triggers declared — the router can never match this skill automatically; ...
Advisory only — these findings block nothing.
```

---

#### `vibe skill enable`

Enable a skill for routing.

```bash
vibe skill enable <skill-id>
```

**Example:**
```bash
vibe skill enable gstack/review
```

**Output:**
```
✓ Skill 'gstack/review' enabled
```

---

#### `vibe skill disable`

Disable a skill from routing.

```bash
vibe skill disable <skill-id>
```

**Example:**
```bash
vibe skill disable old-deploy-skill
```

**Output:**
```
✓ Skill 'old-deploy-skill' disabled
```

---

#### `vibe skill status`

Show detailed status of a skill including lifecycle transitions.

```bash
vibe skill status <skill-id>
```

**Example:**
```bash
vibe skill status gstack/review
```

**Output:**
```
┌─────────────────────────────────────┐
│ Skill Status: gstack/review         │
├─────────────────────────────────────┤
│ ID:           gstack/review         │
│ Name:         Code Review Skill     │
│ State:        active                │
│ Enabled:      Yes                   │
│ Scope:        global                │
│ Version:      2.1.0                 │
│ Valid transitions: deprecated       │
└─────────────────────────────────────┘
```

---

#### `vibe skill stale`

Detect stale or underperforming skills. Analyzes usage statistics and quality
scores to identify skills that may need deprecation, review, or are performing well.

```bash
vibe skill stale [options]
```

**Options:**
- `--auto, -a` - Apply suggested deprecations/archives (explicit opt-in)
- `--json, -j` - Output as machine-readable JSON (still read-only)

Since gate38 the default path — including `--json` — performs **no
lifecycle writes**. The only explicit auto-disposition entry points are
`vibe skill stale --auto`, `vibe optimize --apply`, and
`vibe skill cleanup --auto`.

**Examples:**
```bash
vibe skill stale               # Report only (read-only)
vibe skill stale --auto        # Apply suggested deprecations/archives
vibe skill stale --json        # Machine-readable output (read-only)
```

**Output:**
```
┌──────────────────────────────────────────────────────┐
│              Skill Health Analysis                    │
├──────────────────┬─────────┬───────┬────────┬────────┤
│ Skill ID         │ Action  │ Grade │ Unused │ Routes │
├──────────────────┼─────────┼───────┼────────┼────────┤
│ old-deploy-skill │ DEPRECATE│ F    │ 45d    │ 5      │
│ slow-review      │ WARN    │ D    │ 15d    │ 8      │
│ fast-builder     │ BOOST   │ A    │ 1d     │ 50     │
└──────────────────┴─────────┴───────┴────────┴────────┘
Summary: 1 to deprecate, 1 to warn, 1 performing well
```

**How it works:**
- Reads `usage_stats` from `SkillConfig` (updated by each route via `record_usage()`)
- Reads quality scores from `RoutingEvaluator` (A-F grades; "?" = no routing
  feedback — such skills are never flagged)
- Skills unused >30 days or with F-grade are flagged for deprecation
- `--auto` transitions flagged skills to DEPRECATED/ARCHIVED lifecycle state
- Discovery no longer silently archives DEPRECATED skills idle ≥90 days
  (gate38): they stay DEPRECATED and visible in `discover_all` until you
  archive them via an explicit entry point. Note: DEPRECATED skills with
  grade "?" have no rule-based archive path — archive them manually if
  needed.

---

#### `vibe skill cleanup` (v5.3.0+)

Interactively review and clean up low-quality or stale skills with checkbox selection.

```bash
vibe skill cleanup [options]
```

**Options:**
- `--auto, -a` — Apply all suggested deprecations and archives (one of the three explicit auto-disposition entry points; everything is read-only without it)
- `--dry-run, -n` — Preview what would be cleaned without making changes

**Examples:**
```bash
# Interactive cleanup (select skills to deprecate/archive)
vibe skill cleanup

# Auto-apply all suggestions
vibe skill cleanup --auto

# Preview only
vibe skill cleanup --dry-run
```

**Output:**
```
Analyzing skill ecosystem...

Skills Needing Attention
────────────────────────────────
#  Skill ID          Action      Grade   Quality   Unused   Reason
1  gstack/old        ARCHIVE     D       30%       120d     Unused 120d, grade D
2  my-custom         DEPRECATE   F       10%        60d     Quality 0.1, grade F

Found: 1 to archive, 1 to deprecate

Select skills to clean up (space to select, enter to confirm):
  ◻ ARCHIVE  gstack/old
  ◻ DEPRECATE  my-custom
```

---

#### `vibe skill end-check` (v5.1.0+)

Run end-of-session checks: retention analysis + skill creation suggestions.

```bash
vibe skill end-check [options]
```

**Options:**
- `--json, -j` — Output as JSON

**Examples:**
```bash
# Run session-end checks
vibe skill end-check

# Machine-readable output
vibe skill end-check --json
```

---

#### `vibe skills suggestions` (v5.1.0+)

Unified suggestion inbox: repeated workflow patterns (`sequence` type, from instinct learning) **and repeated no-match queries** (`market-search` type, suggesting `vibe market search`). Shows pending suggestions with confidence and occurrence counts.

```bash
vibe skills suggestions [options]
```

**Options:**
- `--dismiss, -d` — Dismiss all pending suggestions
- `--json, -j` — Output as JSON

**Examples:**
```bash
# View pending suggestions
vibe skills suggestions

# Dismiss all
vibe skills suggestions --dismiss

# Distill a sequence suggestion into a real skill
vibe skills distill <suggestion-id>
```

---

#### `vibe skill scan-candidates` (v8.1.0)

Cluster recent route spans → populate the skill-candidate pool. Clusters with
`span_count >= --min-cluster-size` AND `gold_rate >= --min-gold-rate` become
stable candidates; clusters with `gold_rate < 0.30` land in the unstable
(diagnosis) bucket; in-between gold rates are silently skipped. Idempotent —
re-scanning refreshes counts without duplicating rows; TTL-expired pending
rows are pruned at start.

```bash
vibe skill scan-candidates [options]
```

**Options:**
- `--limit <N>` — Number of recent spans to scan (default: 100)
- `--days, -d <N>` — Best-effort look-back window in days (default: no filter; spans with missing/malformed timestamps are kept regardless; recommended: 7-30)
- `--min-cluster-size <N>` — Min spans per cluster to qualify (default: 3)
- `--min-gold-rate <F>` — Stable candidate threshold, 0.0-1.0 (default: 0.6)
- `--behavior-threshold <F>` — Behavior-consistency gate: min mean pairwise bigram-Jaccard for `behavior_evidence=consistent` (0-1; below → divergent; fewer than 2 sequences → unavailable). Provisional default 0.5 pending calibration
- `--miss-cosine-threshold <F>` — Cosine threshold for miss-vs-miss soft-merge clustering (default: 0.7)
- `--miss-min-pairs <N>` — Min distinct (task_key, natural-day) pairs for miss_recurrence admission (default: 3)
- `--miss-min-days <N>` — Min distinct natural days for miss_recurrence admission, conjunctive with pairs (default: 2)
- `--cross-project` — Scan spans across all pool members; candidates land in the global store at `~/.vibe/observability/` (register pool members via `vibe pool add <path>`)
- `--dry-run` — Classify clusters without writing to the pool

**Examples:**
```bash
# Scan the 100 most recent spans
vibe skill scan-candidates

# Restrict to the last two weeks, larger scan window
vibe skill scan-candidates --days 14 --limit 500

# Preview without writing
vibe skill scan-candidates --dry-run
```

---

#### `vibe skill candidates` (v8.1.0)

List pending skill candidates from the pool. Default: stable candidates sorted
by `gold_rate` descending. Reads from BOTH the project store
(`<cwd>/.vibe/observability/`) and the global store (`~/.vibe/observability/`);
cross-project candidates are tagged `[XP]`. Cluster IDs are rendered as 8-char
prefixes — `promote` / `dismiss` accept the displayed prefix (exact match
first, then unique-prefix resolution over both stores; ambiguous prefixes list
candidates and mutate nothing).

```bash
vibe skill candidates [options]
```

**Options:**
- `--unstable` — Show only unstable candidates (gold_rate < 0.30), sorted ascending
- `--include-unstable` — Show stable AND unstable candidates in one list
- `--json` — Machine-readable JSON output
- `--cross-project-only` — Show only candidates from the global (cross-project) store

---

#### `vibe skill discover` (v8.1.0)

Unified Discovery queue — one view over all skill candidates. The table shows
each candidate's cluster ID (8-char prefix), evidence, and two M12 additions:
the **First seen** column (age of the pattern's earliest span, persisted as
`first_seen_at` with earliest-wins merge on rescan; legacy rows fall back to
creation time) and the behavior-evidence column (four render states —
the literal tokens the CLI prints, for easy grepping: `consistent` /
`divergent` / `unavailable` / `未采集`; see
`scan-candidates --behavior-threshold`).

**列说明（gate35 N1 自解释列头）:** `ID` / `评分` / `模式` / `Examples` /
`来源` / `行为` / `为什么在` / `First seen`（`--all` 时追加 `Status`）。
其中 **为什么在** 只从实存字段直译（gate35 N1，修订 F）：`source`、
`gold_rate`、`span_count`、`task_ids` 数量、`first_seen_at`（存量行缺
`first_seen_at` 时回退 `created_at`）——不编造 recurrence pairs/days
等不落库的口径。完整字段词汇表见 `vibe skill discover --help`。

**agent-echo 卡片（gate35 D2）:** 代表 query 命中 agent prompt 前缀谓词的
候选在 `模式` 列打 `shape: agent-echo` 标签并沉底（组内保持既有评分排序；
CLI 与看板共用同一沉底规则与分组键），表后附计数行提示
`vibe skill discover dismiss --shape agent-echo` 批量否决。

**来源统计（只读）:** 表尾按来源输出成功/否决计数——成功 = promoted →
activated 后路由命中 ≥5（仅统计当前项目 cwd 的 `analytics.jsonl`，全局
scope 提升在其他项目的命中不计入）；否决 = 池状态翻转，**不含
shape-batch**（shape-batch 批量否决单列展示，见下文 dismiss 小节）。

```bash
vibe skill discover [options] [command]
```

**Options:**
- `--all` — Show dismissed/muted candidates too (default: hidden)
- `--mute <cluster-id>` — Temporarily mute a candidate by cluster ID or prefix (auto-restores)
- `--mute-days <N>` — Mute duration in days (default: 14)
- `--history` — Show closed-loop record + discovery precision

**Subcommands:**
- `dismiss <cluster-id>` — Dismiss a candidate into the sticky negative list (see below)

---

#### `vibe skill discover dismiss` (v8.1.0)

Dismiss a candidate into the sticky negative list
(`discovery_dismissals.jsonl`: cluster fingerprint + reason + time). The
candidate is no longer proactively suggested and is hidden by default
(`--all` reveals it). Does NOT flip the candidate-pool row status — that is
what `vibe skill dismiss` does; the two are separate mechanisms. Feedback
tightens one-way: when the dismiss count reaches a threshold, VibeSOP suggests
raising admission thresholds (suggestion only, never auto-applied).

```bash
vibe skill discover dismiss <cluster-id> [--reason <text>]
vibe skill discover dismiss --shape agent-echo [--yes]
```

**Arguments:**
- `cluster_id` — Cluster ID (full or 8-char prefix). Omit when using `--shape`

**Options:**
- `--reason <text>` — Why this candidate is rejected (recorded in the negative list). Not accepted together with `--shape` (batch reason is fixed to `shape-batch`)
- `--shape <agent-echo>` — Batch-dismiss every pending candidate carrying this display shape tag (currently only `agent-echo`)
- `--yes` — Confirm a `--shape` batch dismissal (required to execute)

**批量否决 `--shape agent-echo`（gate35 D2）:** 与逐条 dismiss 是**另一条
路、另一套语义**：逐条 dismiss 进指纹负名单（`discovery_dismissals.jsonl`）
并计入 threshold_suggestion 的 dismiss 输入；`--shape` 走**候选行池状态
翻转**（pending → dismissed，`dismiss_reason=shape-batch`），project 与
global 两个 scope 的镜像行一并翻转（只翻一边会让另一边下次渲染复活），
**不进指纹负名单、豁免 threshold_suggestion 输入**。选择谓词与展示打标
同一前缀谓词（标集 = 否决集）；terminal 状态粘性，重扫不会复活。不带
`--yes` 时只打印预览并要求确认——确认文案点名 **bd1bc217 先例**：回声簇
是合法池成员，全系统唯一真实 promote 成功案例正来自这类簇，批量否决前请
确认。`--history` 视图中 shape-batch 批量否决**单列展示**，不进 Dismissed
表（否则会一次灌满否决分母、污染发现精度）。

---

#### `vibe skill promote` (v8.1.0)

Promote a candidate → draft SKILL.md + flip status. The draft is written to
`.vibe/observability/skill_drafts/<id>/` (project scope, default) or
`~/.vibe/observability/skill_drafts/<id>/` (`--scope global`) — paths that are
NOT auto-discovered by routing. This is the literal "no review, no injection"
guarantee: to inject the skill, edit the draft and re-run with `--activate`,
or copy it into a `skills/` dir and run `vibe skill add <path>`.

**Edit guard:** the sha256 of the freshly generated draft is recorded on the
candidate (`draft_sha256`). `--activate` compares the CURRENT file hash —
identical means no human edit happened and activation is refused (content
hash, not mtime — a bare `touch` doesn't count, but any byte change, even
whitespace, does). A re-promote over an existing draft does NOT re-baseline
the guard; legacy candidates (promoted before the guard existed) require
`--force`.

**Shadow verifier（gate36）:** promote 成功后自动对草稿跑 `verify_draft`，
输出 PASS / WARN 徽章加明细（接住 / 未捕获的 query、最近邻、hijack 冲突
数）。徽章测的是**触发召回**（候选 query 能否被该草稿的 trigger 接住），
不是内容质量。要点：

- **只有 PASS / WARN 两级，无 FAIL；永不阻断激活**——verifier 是提示灯
  不是门（"the lamp must never become a gate"），异常时打印
  `shadow verifier unavailable (已跳过, 不阻断)` 继续。
- PASS 分母**排除 agent-echo 行**；任一 embedding 线不可用或被 skipped 时
  徽章至多为 WARN(degraded/skipped)——degraded 运行永不发 PASS。
- `--activate` 时复用 verdict：当前草稿哈希与 promote 时一致则直接复用，
  已变（用户编辑过）则以 `activate-rerun` 相位重跑；degraded 的重跑不会
  覆盖已有的非 degraded verdict（展示偏好完整结果）。
- verdict 存项目 `.vibe/observability/promote_verdicts.jsonl`
  （`RULESET_VERSION=gate36-r1`，随规则集演进）；**global scope 只存计数
  + query 的 sha256 哈希，不存原文**（修订 D 隐私口径）。

```bash
vibe skill promote <cluster-id> [options]
```

**Arguments:**
- `cluster_id` — Cluster ID from `vibe skill candidates` (full or displayed 8-char prefix)

**Options:**
- `--scope <project|global>` — Draft destination (default: project). Global drafts are visible from any cwd but still require explicit activation. `--scope project` on a cross-project cluster is allowed but warns (the draft will contain queries from multiple projects)
- `--activate` — Register the skill into routing in one step. Refused unless the draft was edited since generation (content-hash guard) or `--force` is passed. Global scope additionally requires cross-project evidence (or `--force`) AND an interactive privacy confirmation (always, even with `--force`)
- `--force` — Bypass the edit guard and the global cross-project evidence requirement; forwarded to the installer as a forced reinstall when the skill is already installed. Never skips the global privacy confirmation

**Examples:**
```bash
# Draft a SKILL.md for review (project scope)
vibe skill promote bd1bc217

# After editing the draft, activate into routing
vibe skill promote bd1bc217 --activate
```

---

#### `vibe skill dismiss` (v8.1.0)

Dismiss a candidate with an optional reason. Status is sticky (the candidate
stays dismissed across rescans). Distinct from `vibe skill discover dismiss`
(sticky negative list) — this command flips the candidate-pool row status.

```bash
vibe skill dismiss <cluster-id> [options]
```

**Arguments:**
- `cluster_id` — Cluster ID to dismiss (full or displayed 8-char prefix)

**Options:**
- `--reason <text>` — Why this candidate is rejected (recorded)
- `--scope <project|global>` — Which store to dismiss from (default: project). If the cluster isn't in the requested store, VibeSOP falls back to the other store with a hint (cross-project candidates live in the global store)

---

#### `vibe status` (v5.3.0+)

Show a unified snapshot of your VibeSOP skill ecosystem. Displays ecosystem health, recent activity, personalized recommendations, warnings, community trends, skill suggestions, and earned badges.

```bash
vibe status [options]
```
Also the default command when running `vibe` with no arguments.

**Options:**
- `--no-color` — Disable colored output

**Examples:**
```bash
# Full status dashboard
vibe status

# No args also shows status
vibe
```

**Output:**
```
──────────────────── VibeSOP Status ────────────────────

Ecosystem Health     289 skills · 29 with evaluation data  A: 12 B: 8 C: 5 D: 3 F: 1
Recent Activity      [route] systematic-debugging    2026-04-28
                     [route] gstack/review           2026-04-28
For You              refactor — your project has 12 TODOs, try this skill
                     security-review — you've never used this, matches Python project
Warnings             my-old-skill — grade F, quality 25%
Community Trending   django-test-helper  👍 23
Skill Suggestions    3 new pattern(s) detected from your workflows
```

---

#### `vibe instinct` (v5.4.5+)

Instinct learning system — record, review, and evolve workflow patterns into formal skills.

```bash
vibe instinct [command]
```

**Subcommands:**
- `learn <pattern> <action>` — Manually record a successful workflow pattern
- `eval` — Review auto-detected sequence patterns, convert to skill suggestions
- `status [--tag <tag>]` — View learned instincts by confidence level
- `export [--output <path>]` — Export instincts to JSON for team sharing
- `import <file>` — Import instincts from JSON export
- `evolve [--index <n>]` — Upgrade high-confidence instinct to formal SKILL.md

**Examples:**
```bash
vibe instinct learn "run tests before commit" "pytest && git commit" --tag testing
vibe instinct status
vibe instinct eval
vibe instinct export --output team-instincts.json
vibe instinct evolve --index 0
```

---

#### `vibe trace` (v5.4.5+)

Inspect routing traces for debugging and transparency.

```bash
vibe trace [command]
```

**Subcommands:**
- `list-traces` — List recent routing traces from .vibe/traces/
- `show <id>` — Show full detail of a routing trace (layer matches, rejected candidates)
- `clean` — Remove old routing traces, keep most recent

**Examples:**
```bash
vibe trace list-traces
vibe trace show abc123
trace clean
```

---

#### `vibe dashboard` (v8.0+)

Start a local web dashboard for background visualization of routing history,
traces, conversations, and health metrics.

```bash
vibe dashboard [options]
```

**Options:**
- `--host`, `-h` — Host to bind to (default: 127.0.0.1)
- `--port`, `-p` — Port to listen on (default: 8420)
- `--open` / `--no-open` — Automatically open browser (default: open)
- `--project`, `-P` — Project root directory (default: auto-detect from cwd)

**Dependencies:**
```bash
uv sync --extra dashboard
# or: uv pip install vibesop[dashboard]
```

**Examples:**
```bash
# Start dashboard on default port, auto-open browser
vibe dashboard

# Custom port, no browser auto-open
vibe dashboard --port 9000 --no-open

# Specify project root explicitly
vibe dashboard --project /path/to/project
```

**Dashboard Tabs:**
- **📊 Overview** — Route count, hit rate, avg satisfaction, latency P50/P95/P99,
  top skills bar chart, mode distribution
- **📋 History** — Sortable routing history table (time, query, skill, mode,
  duration), filterable by skill
- **🔍 Traces** — Per-route decision trees with per-layer match/reject details
- **💬 Conversations** — Multi-turn conversation history with full turn details
- **✨ Discoveries** — Read-only Discovery 队列：候选卡片（与 CLI 同一沉底
  规则/打标口径）、promote verdict 徽章（PASS/WARN，gate36 shadow verifier）、
  按来源的成功/否决统计

---

#### `vibe verify` (v5.4.5+)

Verify platform configuration integrity across all supported platforms.

```bash
vibe verify [platform] [--verbose]
```

**Arguments:**
- `platform` — Platform to verify: claude-code, kimi-cli, opencode, cursor, or all (default)

**Examples:**
```bash
vibe verify
vibe verify claude-code --verbose
```

---

#### `vibe workflows` (v5.4.5+)

Manage cross-cutting multi-skill workflows.

```bash
vibe workflows [command]
```

**Subcommands:**
- `list` — List all cross-cutting workflows
- `show <id>` — Show workflow details (depends_on, steps)
- `create` — Interactive wizard to create a workflow
- `match <skill_ids>` — Find workflows covering given skills

**Examples:**
```bash
vibe workflows list
vibe workflows show full-stack-feature
vibe workflows match skill-a skill-b
```

---

## Autonomous Loops

### `vibe loop` (v8.1.0)

Manage autonomous scheduled loops — recurring execution of a skill query or
vibe subcommand on a cron schedule. VibeSOP ships no long-running daemon: an
external scheduler (cron / systemd timer / launchd) invokes `vibe loop tick`
once per minute, and tick dispatches whatever is due.

Storage is HOME-level: `~/.vibe/loops/{name}/spec.json` (user-editable
definition) + `state.json` (system-managed runtime state). Loop names are
globally unique across projects. Setup walkthrough: see the
[Loop Setup Guide](../loop-setup-guide.md).

**Project ownership (`project_root`):** every loop carries an owning project
root. Ownership is pinned ONLY by explicit action — `create` (pins the current
directory by default, `--global` opts out), `adopt`, and `migrate-ownership`.
Bare `tick` never infers ownership. A loop with no `project_root` (legacy
specs and deliberate `--global`) is visible and runnable from any directory.
A pinned loop is owned by a directory when the current directory is inside its
`project_root`; the executor then runs the loop's target with `project_root`
as the working directory — command targets get it as subprocess `cwd`, routing
targets get an `AgentRuntime` constructed on it — regardless of where tick was
invoked. If a pinned root no longer exists, the tick fails PERMANENT (by
design, burning failure budget as a loud signal); re-pin with
`vibe loop adopt <name>` and clear the budget with `vibe loop reset <name>`.

> **⚠️ No-downgrade warning:** `project_root` is a new spec field and the
> model forbids unknown fields. An older VibeSOP reading a new
> `spec.json` **quarantines** the file (renamed to `spec.json.corrupt`): the
> loop disappears from `loop list`, and a registered launchd job keeps firing
> every minute but spins silently (`tick --name` finds no spec, takes the
> no-trigger branch, exits 0) — worse, with no alerting signal at all.
> `loop delete` removes the `.corrupt` backup along with everything else.
> `state.json` embeds a copy of the spec and is quarantined the same way
> (run history lost). **Back up `~/.vibe/loops/` before downgrading.**

**Subcommands:**
- [`create`](#vibe-loop-create-v810) — Create a scheduled loop
- [`list`](#vibe-loop-list-v810) — List loops (default: current project only)
- [`show`](#vibe-loop-show-v810) — Loop details + recent run history
- [`pause` / `resume` / `reset`](#vibe-loop-pause--resume--reset-v810) — Status lifecycle
- [`delete`](#vibe-loop-delete-v810) — Delete a loop (irreversible)
- [`adopt`](#vibe-loop-adopt-v810) — Pin ownership to the current directory
- [`migrate-ownership`](#vibe-loop-migrate-ownership-v810) — Backfill ownership from launchd plists (macOS)
- [`tick`](#vibe-loop-tick-v810) — Single polling cycle (the execution bridge)
- [`install-launchd`](#vibe-loop-install-launchd-v810) / [`uninstall-launchd`](#vibe-loop-uninstall-launchd-v810) — launchd integration (macOS)

`show` / `pause` / `resume` / `reset` / `delete` address loops by their
globally-unique name WITHOUT ownership filtering — cross-project operations
are legitimate. Only `list` and bare `tick` filter by ownership.

---

#### `vibe loop create` (v8.1.0)

Create a new scheduled loop. Exactly one execution target is required:
`--skill` / `--query` / `--workflow` / `--command`, or `--preset` to load a
predefined template (fills `--command` and `--schedule`).

**Ownership:** by default the current directory is pinned as `project_root`.
If the current directory is neither a git repo nor contains a
`pyproject.toml`, create warns but proceeds (it only writes JSON) — use
`--global` to deliberately create an unscoped loop instead. A name collision
error names the conflicting loop's owning project.

```bash
vibe loop create <name> [options]
```

**Arguments:**
- `name` — Loop name, kebab-case, globally unique (e.g. `ci-watcher`)

**Options:**
- `--skill, -s <id>` — Target skill ID
- `--query, -q <text>` — Natural-language routing query
- `--workflow, -w <id>` — Workflow ID
- `--command, -c <text>` — vibe subcommand + args, shlex-parsed (e.g. `'instinct auto-promote --min-confidence 0.85'`); executed as a subprocess, no LLM cost
- `--preset, -p` — Treat `name` as a preset key (`instinct-assemble` / `instinct-promote` / `instinct-feedback`)
- `--schedule <cron>` — 5-field cron expression (default: `0 0 * * *`)
- `--desc, -d <text>` — Description
- `--max-failures <N>` — Consecutive failures before the loop flips to DEAD (default: 3)
- `--global` — Do not pin project ownership (global loop: visible and runnable from any cwd; default is pinning the current directory)

**Examples:**
```bash
# Skill target, every 30 minutes, pinned to the current project
vibe loop create ci-watcher --skill systematic-debugging --schedule "*/30 * * * *"

# Command target from a preset
vibe loop create instinct-promote --preset

# Deliberately global loop (no ownership)
vibe loop create journal --query "summarise today's notes" --global
```

---

#### `vibe loop list` (v8.1.0)

List loops. **Default: only loops owned by the current project** (unscoped
loops plus loops whose `project_root` contains the current directory). Loops
belonging to other projects are hidden with a count hint.

```bash
vibe loop list [options]
```

**Options:**
- `--status, -s <status>` — Filter by status (active/paused/failing/dead/retired)
- `--all` — List every loop including other projects', with an extra `Project` column (unscoped loops shown as `(global)`)

---

#### `vibe loop show` (v8.1.0)

Show loop details and recent run history, including the `Project` line
(owning root or `(global)`).

```bash
vibe loop show <name>
```

---

#### `vibe loop pause` / `resume` / `reset` (v8.1.0)

Status lifecycle:

```bash
vibe loop pause <name>    # tick skips it; spec unchanged
vibe loop resume <name>   # back to ACTIVE; consecutive-failure counter cleared
vibe loop reset <name>    # DEAD → ACTIVE (the only revival path for DEAD)
```

DEAD is terminal: `resume` will not revive it — `reset` is the only way back
(clears the failure budget). Typical pairing after a missing-project-root
failure: `vibe loop adopt <name>` then `vibe loop reset <name>`.

---

#### `vibe loop delete` (v8.1.0)

Delete a loop — irreversible; spec, state, and all run history are removed.
On macOS, a registered launchd plist is booted out and removed first
(best-effort; if bootout fails the plist is kept as a recovery artifact with
a loud warning).

```bash
vibe loop delete <name> [--force]
```

**Options:**
- `--force, -f` — Skip the confirmation prompt

---

#### `vibe loop adopt` (v8.1.0)

Pin a loop's project ownership to the current directory (cwd). Untrusted cwd
(no `.git/` or `pyproject.toml`) warns but proceeds — confirm the directory is
the intended project root. Also syncs the spec copy embedded in `state.json`.

```bash
vibe loop adopt <name>
```

---

#### `vibe loop migrate-ownership` (v8.1.0)

Backfill project ownership for legacy loops from launchd plists (macOS only).
Reads the `WorkingDirectory` of `~/Library/LaunchAgents/com.vibesop.loop.*.plist`
and writes it back as the spec's `project_root` (syncing the `state.json`
spec copy). **Note: this also pins `--global` loops** that have a plist —
uninstall the plist first, or inspect with `--dry-run`, if a loop should stay
global. Loops without a plist are listed with an `adopt` hint (this is also
the non-macOS behavior: nothing is written).

```bash
vibe loop migrate-ownership [--dry-run] [--yes]
```

**Options:**
- `--dry-run` — Report what would be backfilled without writing
- `--yes, -y` — Skip per-loop confirmation (default: ask before each backfill)

---

#### `vibe loop tick` (v8.1.0)

Execute one polling cycle: check the cron of every eligible (ACTIVE/FAILING)
loop and run those due this minute. This is the command external schedulers
call once per minute.

**Ownership semantics:** a bare tick only enumerates loops owned by the
current project; skipped loops print a loud skip line (names, capped at 5,
plus a total count) — including when nothing ends up due. `--name` bypasses
ownership filtering (that is the launchd call shape, unchanged). `--all` is
the compatibility hatch for users running a bare tick from HOME via system
cron. Execution happens in each loop's owning root, not tick's cwd. Exit code
is non-zero if any loop failed, so cron/launchd can detect total failure.

```bash
vibe loop tick [options]
```

**Options:**
- `--name, -n <name>` — Check only the named loop (bypasses ownership filtering)
- `--dry-run` — Show which loops would trigger without executing
- `--all` — Skip ownership filtering, enumerate all loops (compat for system-cron-from-HOME)

**Examples:**
```bash
# crontab line (run from the project directory)
* * * * * cd /path/to/project && uv run vibe loop tick >> ~/.vibe/loops/tick.log 2>&1

# Preview without executing
vibe loop tick --dry-run

# launchd / single-loop shape
vibe loop tick --name ci-watcher
```

---

#### `vibe loop install-launchd` (v8.1.0)

Generate a launchd plist and register it under `~/Library/LaunchAgents/`
(macOS only). The plist invokes `vibe loop tick --name <name>` with the
current directory as `WorkingDirectory`; `launchctl bootstrap gui/$(id -u)`
registers it, and an already-registered label is refreshed automatically
(bootout → bootstrap). install-launchd does NOT backfill spec ownership —
ownership is pinned only by `create` / `adopt` / `migrate-ownership`; if the
spec is pinned to a different directory than the current one, install warns
(execution follows `spec.project_root`, not the plist's WorkingDirectory).

**Safety rails:** refuses to persist an untrusted cwd (no `.git/` or
`pyproject.toml`) unless `--trust-cwd`; when auto-resolving the default
prefix, refuses a `uv` binary outside the whitelist (Homebrew /
`~/.local/bin` / `/usr/bin`) unless `--trust-uv-path` — an explicit
`--vibe-prefix` bypasses the whitelist check entirely.

```bash
vibe loop install-launchd <name> [options]
```

**Options:**
- `--vibe-prefix <text>` — vibe CLI invocation prefix (default: auto-resolve absolute `uv` path + `run vibe`; quote paths with spaces). Env var: `VIBESOP_RUN_PREFIX`
- `--trust-cwd` — Allow a cwd that is not a git repo / has no pyproject.toml
- `--trust-uv-path` — Allow a `uv` resolved outside the whitelist
- `--dry-run` — Print the plist only; do not write or bootstrap

---

#### `vibe loop uninstall-launchd` (v8.1.0)

Unregister a loop from launchd (`launchctl bootout`) and delete the plist.
Idempotent — succeeds even if the loop was never registered.

```bash
vibe loop uninstall-launchd <name> [--keep-plist]
```

**Options:**
- `--keep-plist` — Keep the plist file (bootout only)

---

## Project Setup

### `vibe init`

Initialize a new project with VibeSOP configuration.

```bash
vibe init [options]
```

**Options:**
- `--platform, -p` - Target platform (default: claude-code)
- `--force, -f` - Overwrite existing configuration

**Example:**
```bash
# Initialize with defaults
vibe init

# Initialize for specific platform
vibe init --platform opencode
```

---

### `vibe build`

Build platform-specific configuration.

```bash
vibe build [platform] [options]
```

**Arguments:**
- `platform` - Target platform (claude-code, kimi-cli, opencode, cursor)

**Options:**
- `--output, -o` - Output directory
- `--force, -f` - Overwrite existing files

**Examples:**
```bash
# Build for default platform
vibe build

# Build for specific platform
vibe build claude-code

# Build to specific directory
vibe build claude-code --output ~/.claude
```

---

### `vibe quickstart`

Interactive setup wizard.

```bash
vibe quickstart [options]
```

**Options:**
- `--force, -f` - Skip confirmations and use defaults
- `--platform, -p` - Target platform (default: claude-code)
- `--global, -g` - Install to global configuration directory

**Example:**
```bash
# Interactive setup
vibe quickstart

# Non-interactive with defaults
vibe quickstart --force
```

---

### `vibe onboard`

Onboard to an existing project.

```bash
vibe onboard [path]
```

**Arguments:**
- `path` - Project path (default: current directory)

---

## Platform & Utility Commands

### `vibe switch`

Switch the active platform configuration.

```bash
vibe switch <platform>
```

**Arguments:**
- `platform` - Target platform (`claude-code`, `kimi-cli`, `opencode`, `cursor`, `superpowers`)

**Example:**
```bash
vibe switch claude-code
```

---

### `vibe targets`

List supported build and installation targets.

```bash
vibe targets
```

**Output:**
- Platform name
- Config directory path
- Installation status

---

### `vibe algorithms`

List available algorithm utilities in the VibeSOP algorithm library.

```bash
vibe algorithms [options]
```

**Options:**
- `--verbose, -v` - Show detailed descriptions

---

### `vibe tools`

List available platform tools and integrations.

```bash
vibe tools [options]
```

**Options:**
- `--platform, -p` - Filter by platform

---

### `vibe inspect`

Inspect project configuration, routing state, or skill details.

```bash
vibe inspect <target> [options]
```

**Targets:**
- `config` - Show merged configuration
- `route <query>` - Show routing trace for a query
- `skill <id>` - Show raw skill metadata

**Example:**
```bash
vibe inspect config
vibe inspect route "debug this error"
```

---

## Analysis Commands

### `vibe analyze`

Unified analysis command for sessions, security, and integrations.

```bash
vibe analyze <target> [options]
```

**Targets:**
- `session` - Analyze conversation session
- `security` - Security scan
- `integrations` - Detect skill pack integrations

### `vibe analyze session`

Analyze session history for patterns and skill suggestions.

```bash
vibe analyze session [file] [options]
```

**Arguments:**
- `file` - Session file path (optional)

**Options:**
- `--min-frequency, -f` - Minimum pattern frequency (default: 3)
- `--min-confidence, -c` - Minimum confidence (default: 0.7)
- `--auto-craft, -a` - Auto-create suggested skills

**Example:**
```bash
# Analyze current session
vibe analyze session

# Analyze specific file
vibe analyze session session.jsonl

# Auto-create skills
vibe analyze session --auto-craft
```

### `vibe analyze security`

Scan files for security issues.

```bash
vibe analyze security <path> [options]
```

**Arguments:**
- `path` - File or directory to scan

**Options:**
- `--all` - Scan all files (not just code files)
- `--json, -j` - Output as JSON

**Example:**
```bash
# Scan current directory
vibe analyze security .

# Scan specific directory
vibe analyze security src/

# Include all files
vibe analyze security . --all
```

### `vibe analyze integrations`

Detect available skill pack integrations.

```bash
vibe analyze integrations [options]
```

**Options:**
- `--verbose, -v` - Show detailed information
- `--json, -j` - Output as JSON

---

## Configuration

### `vibe config`

Manage VibeSOP configuration.

```bash
vibe config [command] [options]
```

**Subcommands:**
- `get <key>` - Get configuration value
- `set <key> <value>` - Set configuration value
- `list` - List all configuration
- `edit` - Open configuration in editor

**Examples:**
```bash
# Get configuration value
vibe config get routing.min_confidence

# Set configuration value
vibe config set routing.min_confidence 0.8

# List all configuration
vibe config list
```

---

## LLM Configuration

VibeSOP uses LLM for AI semantic triage (Layer 2 of the routing pipeline) and task decomposition.
Configure the LLM provider to enable semantic understanding.

### Quick Start

```bash
# Default: Ollama local (no API key needed)
brew install ollama
ollama pull qwen3:35b-a3b-mlx
ollama serve

# For cloud providers, set environment variables:
export VIBE_LLM_PROVIDER=anthropic
export ANTHROPIC_API_KEY=sk-ant-...
```

### Supported Providers

| Provider | Setup | Best for |
|----------|-------|----------|
| `ollama` | Local, no API key. `brew install ollama && ollama serve` | Offline, privacy, zero cost |
| `anthropic` | `export ANTHROPIC_API_KEY=sk-ant-...` | Best semantic accuracy |
| `openai` | `export OPENAI_API_KEY=sk-...` | Broad model selection |

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VIBE_LLM_PROVIDER` | `ollama` | Provider: `ollama`, `anthropic`, or `openai` |
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1` | Ollama API endpoint |
| `OLLAMA_MODEL` | `Qwen3.6-35B-A3B-mlx-mxfp8` | Default Ollama model |
| `ANTHROPIC_API_KEY` | — | Anthropic API key |
| `OPENAI_API_KEY` | — | OpenAI API key |
| `VIBE_AI_TRIAGE_ENABLED` | — | `0`/`false`/`no` disables the AI-triage LLM call only — fresh hits from the persistent triage cache (`.vibe/triage_cache.json`) are still served. Set `enable_ai_triage = false` in config for a full kill switch |

### Provider Detection Priority

When no `VIBE_LLM_PROVIDER` is set, VibeSOP auto-detects:

1. `OLLAMA_BASE_URL` or `OLLAMA_MODEL` env var → `ollama`
2. `ANTHROPIC_API_KEY` → `anthropic`
3. `OPENAI_API_KEY` → `openai`
4. Default → `ollama`

### Configuration File

```toml
# .vibe/config.toml
[llm]
provider = "ollama"
model = "Qwen3.6-35B-A3B-mlx-mxfp8"
temperature = 0.3
max_tokens = 500
```

### Verifying LLM Configuration

```bash
# Check which provider is active
vibe doctor

# Test with a query that triggers semantic triage
vibe route "analyze the architecture of my project" --verbose
```

---

---

## Preference Learning

### `vibe preferences`

Show preference learning statistics.

```bash
vibe preferences
```

**Output:**
```
📊 Preference Learning Statistics

Total selections: 45
Helpful rate: 87.5%
Unique skills: 12

Top Skills:
  • systematic-debugging: 12 selections
  • gstack/review: 8 selections
  • superpowers/tdd: 5 selections

Storage: ~/.vibe/preferences/
```

---

### `vibe record`

Record a skill selection for preference learning.

```bash
vibe record <skill-id> <query> [options]
```

**Arguments:**
- `skill-id` - Skill that was selected
- `query` - Original user query

**Options:**
- `--helpful, -h` - Mark as helpful (default: true)
- `--not-helpful, -H` - Mark as not helpful

**Examples:**
```bash
# Record helpful selection
vibe record systematic-debugging "debug this error" --helpful

# Record unhelpful selection
vibe record gstack/review "review code" --not-helpful
```

---

### `vibe top-skills`

Show most preferred skills.

```bash
vibe top-skills [options]
```

**Options:**
- `--limit, -l` - Number of skills to show (default: 5, max: 10)

**Example:**
```bash
vibe top-skills --limit 10
```

---

### `vibe route-stats`

Show routing statistics.

```bash
vibe route-stats
```

**Output:**
```
📊 Routing Statistics

Total routes: 128

Layer Distribution:
  • scenario: 45 (35%)
  • keyword: 38 (30%)
  • tfidf: 25 (20%)
  • ai_triage: 12 (9%)
  • explicit: 5 (4%)
  • embedding: 3 (2%)

Cache: ~/.vibe/cache/
```

---

## Experimental Commands

⚠️ These commands are experimental and may change in future versions.

### `vibe skill-craft`

Create skills from session history (experimental).

```bash
vibe skill-craft <action> [options]
```

**Actions:**
- `create` - Create skill from current session
- `from <file>` - Create skill from session file
- `templates` - List available templates

**Options:**
- `--name, -n` - Skill name
- `--description, -d` - Skill description

---

### `vibe import-rules`

Import external rules into VibeSOP configuration (experimental).

```bash
vibe import-rules <file> [options]
```

**Arguments:**
- `file` - Path to rules file

**Options:**
- `--force, -f` - Overwrite existing rules
- `--dry-run` - Preview changes without writing
- `--target, -t` - Target file (rules or behavior-policies)

---

## Command Summary

### Quick Reference

| Command | Description |
|---------|-------------|
| `vibe route <query>` | Route query to best skill |
| `vibe skills available` | List all available skills |
| `vibe skills info <id>` | Show skill details |
| `vibe install <source>` | Install skill pack |
| `vibe init` | Initialize project |
| `vibe build [platform]` | Build configuration |
| `vibe doctor` | Check environment |
| `vibe analyze <target>` | Analyze sessions/security/integrations |
| `vibe preferences` | Show preference statistics |
| `vibe quickstart` | Interactive setup |
| `vibe switch <platform>` | Switch active platform |
| `vibe targets` | List supported targets |
| `vibe algorithms` | List algorithm utilities |
| `vibe tools` | List available tools |
| `vibe inspect <target>` | Inspect config/route/skill |
| `vibe version` | Show version |
| `vibe dashboard` | Start web dashboard for routing history & health |
| `vibe loop create <name>` | Create an autonomous scheduled loop |
| `vibe loop list [--all]` | List loops (default: current project only) |
| `vibe loop tick` | Single polling cycle (called by cron/launchd) |
| `vibe skill scan-candidates` | Cluster spans into the skill-candidate pool |
| `vibe skill discover` | Unified discovery queue over candidates |
| `vibe skill promote <id>` | Promote candidate → draft SKILL.md |

### Removed Commands (removed in v4.1)

The following commands were removed:

| Command | Replacement | Reason |
|---------|-------------|--------|
| `vibe execute` | N/A | Violated "management not execution" principle |
| `vibe memory` | N/A | Internalized as SkillOS learning feature |
| `vibe deploy` | N/A | Out of scope for SkillOS |
| `vibe toolchain` | N/A | Out of scope for SkillOS |
| `vibe worktree` | N/A | Out of scope for SkillOS |
| `vibe checkpoint` | N/A | Out of scope for SkillOS |
| `vibe hooks` | N/A | Out of scope for SkillOS |

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | API key for Anthropic Claude |
| `OPENAI_API_KEY` | API key for OpenAI |
| `VIBESOP_SESSION_ID` | Override session ID for multi-terminal isolation |
| `VIBESOP_ENABLE_LEGACY` | Enable legacy/deprecated commands |
| `VIBESOP_CONFIG_DIR` | Custom configuration directory |

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Invalid command or arguments |
| 130 | Interrupted (Ctrl+C) |

---

For more information, see:
- [README.md](../README.md) - Project overview
- [Architecture Overview](../architecture/ARCHITECTURE.md) - System design
- [Positioning & Philosophy](../PHILOSOPHY.md) - Design principles
