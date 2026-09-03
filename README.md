# VibeSOP

> **Skill routing and lifecycle management for AI coding agents** — [中文文档](README.zh-CN.md)

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Ruff](https://img.shields.io/badge/Ruff-Enabled-black.svg)](https://github.com/astral-sh/ruff)
[![Coverage](https://img.shields.io/badge/Coverage-73%25-yellow.svg)]()
[![Version](https://img.shields.io/badge/Version-8.1.4-blue.svg)](https://github.com/nehcuh/vibesop-py)
[![Spec](https://img.shields.io/badge/Spec-v3.0-green.svg)](docs/skill-format-spec-v3.md)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

VibeSOP is an **AI SkillOS**: it routes your intent to the right skill, orchestrates
multi-step tasks, and manages the full skill lifecycle for your AI coding agents.

## Why VibeSOP?

**1. Install once, works across your AI coding agents.**
One skill definition, every agent. Claude Code and Grok Build get full hook injection
(hook layer verified end-to-end on Claude Code); OpenCode, Cursor, Kimi CLI, and Pi are
supported at the config-generation level.

**2. Your experience compounds across projects.**
The task-memory loop turns daily work into reusable assets: every routed task leaves a
trace → traces cluster into repeatable patterns → `vibe recall` surfaces past solutions
when you hit a similar problem, even in another project.

## Quick start

```bash
pipx install vibesop   # or: uv tool install vibesop
vibe quickstart
```

No API key needed for the routing demo — quickstart runs on the local lightweight
routing path (keyword/scenario matching). LLM-enhanced routing is covered in
[LLM Configuration](#llm-configuration) below.

---

## Vision

**No more memorizing commands. Just express your intent.**
**No more guessing tools. Intelligent matching finds the best.**
**No more learning platforms. Master them all at once.**

---

## What is VibeSOP?

**VibeSOP is a Skill Operating System — managing the full lifecycle of skills:**

### Skill Lifecycle Management

- **Discovery & Installation** — one-click install, auto security audit, zero config

- **Intelligent Routing** — understand intent, match the best skill from 18 built-in
  workflow skills plus installable skill packs (superpowers, omx, gstack, ...)

- **Task Orchestration** — decompose complex requests, generate serial/grouped execution plans

- **Lifecycle Management** — enable/disable, scope isolation, quality evaluation, auto-deprecation

- **Cross-Platform** — one skill definition, per-platform config generation

**Note**: VibeSOP is a Skill Operating System with lightweight guided execution. It manages the **full skill lifecycle**: discovery → installation → routing →
orchestration → evaluation → retention/deprecation. Simple tasks are handled end-to-end by VibeSOP (route → inject → guide execution); complex tasks are delegated to AI Agents
(Claude Code, Cursor, OpenCode).

📖 **Read our philosophy**: [docs/PHILOSOPHY.md](docs/PHILOSOPHY.md) (中文)

🧭 **Skill routing in plain language** (experiments, vs similar tools, how to use): [docs/skill-routing-explained.md](docs/skill-routing-explained.md)

🎯 **See real use cases**: [docs/USE_CASES.en.md](docs/USE_CASES.en.md) (English) | [docs/USE_CASES.md](docs/USE_CASES.md) (中文) — 12 concrete scenarios with pain → approach → commands → expected output

---

## Core Values

### Discovery over Execution

**Finding the right tool is more important than executing it.** AI tools are already powerful enough. The real problem is: **finding the right tool**.

### Orchestration over Single-Skill

**Real-world requests are composite.** VibeSOP decomposes complex intents and orchestrates multiple skills working together.

### Lifecycle over Accumulation

**Skills should be managed, not infinitely accumulated.** Enable/disable, scope isolation, quality evaluation, auto-deprecation — keeping the skill ecosystem healthy.

### Matching over Guessing

**Understanding intent is more important than memorizing commands.** You can't memorize every skill's commands, but you can naturally express what you want to do.

### Open over Closed

**An open ecosystem is more valuable than a closed system.** VibeSOP doesn't lock you to a single agent — it generates per-platform configs for every supported agent.

---

## Quick Start

### 5-Minute Setup

```bash
# 1. Install globally (Windows: add %USERPROFILE%\.local\bin to your PATH)
pipx install vibesop   # or: uv tool install vibesop

# 2. Interactive setup wizard (platform config, skill packs)
vibe quickstart

# 3. Configure your platform (Grok Build / Claude Code)
vibe build grok-build --output ~/.grok
# vibe build claude-code --output ~/.claude

# 4. (Optional) Configure an LLM API key — see "LLM Configuration" below
export ANTHROPIC_API_KEY="sk-ant-..."

# 5. Restart your AI Agent, then test
vibe route "help me debug this code"
```

✅ **Done!** VibeSOP is now globally available with 18 built-in workflow skills,
extensible via skill packs (`vibe install mattpocock`, `vibe install gstack`, ...).

---

### One-Click Skill Installation (Core Feature)

**From 8 manual steps → 1 command!**

```bash
# Install a skill - auto-configured, zero learning curve
vibe skills add tushare

# The system auto-completes:
# ✅ Detect skill type
# ✅ Security audit
# ✅ Smart configure routing rules
# ✅ Auto-set priority
# ✅ Verify and sync

# Start using immediately
vibe route "帮我获取茅台最近一年的股价"
# → AI automatically matches to tushare skill (95% confidence)
```

**Comparison with old workflow**:
- ❌ Old way: 30-60 min, 8+ manual steps, 40% error rate
- ✅ New way: 1-2 min, 1 command, <5% error rate

See: [Smart Skill Installation Guide](docs/QUICKSTART_SKILL_INSTALLATION.md)

---

### First Use

Both examples below run on a fresh install with no API key (keyword/scenario layers):

```bash
# Single intent - routes to best skill
$ vibe route "帮我深入诊断并优化这个性能问题"

🔍 Routing Decision Report
Selected: builtin/deep-diagnosis-optimization (confidence: 82%)

# Session lifecycle intent
$ vibe route "wrap up the session"

🔍 Routing Decision Report
Selected: builtin/session-end (confidence: 95%)
```

> 💡 VibeSOP routes to a skill and injects instructions into your AI Agent's context; the Agent does the actual execution. Run `vibe doctor` to see which Agents are available.

```bash
# Multi intent - automatically orchestrates
# (requires LLM routing configured + community packs installed, e.g.
#  vibe install superpowers — skill names below come from installed packs)
$ vibe route "分析架构并生成测试"

🔍 Routing Summary
─────────────────────────────
Mode         Orchestrated
Steps        2
Strategy     sequential

Plan:
  1. riper-workflow — Architecture Analysis
  2. superpowers/test — Test Generation

[✅ Confirm] [✏️ Edit] [🔀 Single skill] [📝 Skip]
```

**That's it!** VibeSOP understands your intent — whether it's a single task or a complex multi-step request.

---

### Configure AI Agent Platforms

After installation, deploy the config to your AI Agent. VibeSOP supports:

| Platform | Command |
|------|------|
| **Claude Code** | `vibe build claude-code --output ~/.claude` |
| **Grok Build** | `vibe build grok-build --output ~/.grok` |
| **Kimi CLI** | `vibe build kimi-cli --output ~/.kimi-code` |
| **Pi Agent** | `vibe build pi --output .pi` |
| **OpenCode** | `vibe build opencode --output ~/.config/opencode` |
| **Cursor** | `vibe build cursor --output ~/.cursor` |

```bash
# Example: configure Claude Code
vibe build claude-code --output ~/.claude

# Sample output:
# ✓ Build complete!
# Files created:
#   📄 ~/.claude/CLAUDE.md
#   📄 ~/.claude/rules/behaviors.md
#   📄 ~/.claude/hooks/vibesop-route.sh
#   📄 ~/.claude/skills/...
#
# Restart Claude Code to apply changes.
```

> **Important**: After deploying, **restart your AI Agent** for changes to take effect.

---

## LLM Configuration

> 💡 **Agent developers can skip this section**: if your Agent integrates VibeSOP
> in-process as a Python library, `AgentRouter.set_llm()` can reuse the host Agent's
> LLM directly — no API key needed. See the
> **[Agent Integration Guide](docs/agent-integration.md)**. The configuration below
> only applies to the CLI subprocess path (`vibe route`).

On the CLI path, VibeSOP needs its own LLM configuration (a subprocess cannot reuse
the Agent's internal LLM):

**Linux / macOS:**
```bash
# Anthropic Claude (recommended)
export ANTHROPIC_API_KEY="sk-ant-..."

# or OpenAI
export OPENAI_API_KEY="sk-..."

# or local Ollama (zero cost, no data leaving your machine)
export VIBE_LLM_PROVIDER=ollama
export OLLAMA_BASE_URL=http://localhost:11434/v1
export OLLAMA_MODEL=qwen3:35b-a3b-mlx

# Persist (add to ~/.bashrc or ~/.zshrc)
echo 'export ANTHROPIC_API_KEY="sk-ant-..."' >> ~/.bashrc
```

**Windows:**
```cmd
# Temporary (current session)
set ANTHROPIC_API_KEY=sk-ant-...
set OPENAI_API_KEY=sk-...

# Permanent (user environment variable)
setx ANTHROPIC_API_KEY "sk-ant-..."
setx OPENAI_API_KEY "sk-..."

# Or via PowerShell
$env:ANTHROPIC_API_KEY="sk-ant-..."
[System.Environment]::SetEnvironmentVariable('ANTHROPIC_API_KEY', 'sk-ant-...', 'User')
```

> **Tip**: In PowerShell, environment variables set in-session only apply to the current process. To persist, use the GUI:
> - Windows Settings → System → About → Advanced system settings → Environment Variables
> - Add user variable `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`

---

## The Problem VibeSOP Solves

### The Problem

AI-assisted development tools are exploding:
- Claude Code, Cursor, Continue.dev, Aider...
- Each tool has its own commands and skills
- Skill packs like superpowers, mattpocock, omx are booming
- **You don't know which one to use**

### The Solution

```bash
# Just say what you want (natural language input)
vibe route "帮我深入诊断并优化这个性能问题"
# → Routes to: builtin/deep-diagnosis-optimization (82% confidence)

vibe route "wrap up the session"
# → Routes to: builtin/session-end (95% confidence)
```

With community packs installed (`vibe install superpowers`), their skills join the
same routing pool — one syntax, every source.

VibeSOP:
1. **Understands your intent** (natural language, English + Chinese)
2. **Finds the right skill** (from 18 built-in skills plus installable skill packs)
3. **Learns your preferences** (gets better over time)
4. **Works across AI coding agents** (hook injection on Claude Code / Grok Build;
   config generation for OpenCode, Cursor, Kimi CLI, Pi)

---

## Core Features

### One-Click Smart Installation

**From 8 manual steps → 1 command, AI auto-completes all configuration**

```bash
# Install any skill, zero config
vibe skills add tushare
vibe skills add git-helper
vibe skills add code-reviewer

# The system auto-completes:
# ✅ Detect skill type and metadata
# ✅ Run security audit
# ✅ Ask install scope (project/global)
# ✅ AI smart configures routing rules
# ✅ Auto-calculate priority
# ✅ Verify and sync to platform
```

**Comparison**:

| Feature | Traditional | VibeSOP |
|---------|-------------|---------|
| Install Steps | 8+ manual steps | 1 command |
| Time Cost | 30-60 min | 1-2 min |
| Config Files | 3-4 manual edits | 0 (AI generated) |
| Error Rate | 40% | <5% |
| Learning Curve | Steep | Gentle |

**Smart Features**:
- 🤖 **AI Config Engine** - Analyzes skill descriptions, auto-generates optimal config
- 🎯 **Smart Routing** - Extracts keywords, auto-generates regex
- ⚡ **Priority Calculation** - Auto-sets priority based on skill category
- 🔒 **Security Audit** - Auto-scans, risk grading, interactive confirmation
- 💬 **Friendly Wizard** - Clear progress display and error prompts

[Full documentation](docs/QUICKSTART_SKILL_INSTALLATION.md) | [.skill format spec](docs/skill-format-spec.md)

---

### Routing Accuracy (~90% internal estimate)

Based on a 4-stage routing cascade combining AI semantic analysis and scenario knowledge
(see the [Performance Metrics](#performance-metrics) table for provenance):

- **Stage 1**: Explicit override — exact skill ID match (e.g. `/review`), immediate dispatch
- **Stage 2**: Scenario + Semantic Index — predefined scenarios + skill semantic index
  (token-overlap + embedding), best-of-N selection
- **Stage 3**: AI Semantic Triage — LLM intent understanding (~95% on sampled
  validation, complex / long queries)
- **Stage 4**: Matcher aggregation — keyword, TF-IDF, embedding, and fuzzy matchers run
  in parallel; highest-confidence candidate wins (not serial fallback)

Terminal states (not routing layers):
- **No Match**: all candidates below the minimum confidence threshold
- **Fallback LLM**: last-resort raw LLM routing

### Skill Market (v5.2.0+)

Discover and install skills from the public ecosystem:

```bash
# Search GitHub public skill ecosystem (agent-skills topic + curated awesome lists)
vibe market search "debug"

# View trending skills by category (mapped to GitHub topics, sorted by stars)
vibe market trending agent

# Install skills from the market
vibe market install user/repo
```

Search results are sorted by trust level: official (built-in trusted packages) → curated (awesome list) → unverified sources, with stars descending within each tier.

```bash
# Install to current project (.vibe/skills/ only, full-chain security audit)
vibe market install user/repo --scope project

# View category trends
vibe market trending agent
```

**Smart Suggestion Feedback Loop** (v8.0): Unmatched queries are locally counted anonymously (hash only). Repeated misses trigger search suggestions. The orchestration confirmation flow and Claude Code tool hooks learn your repeat workflows. `vibe skills suggestions` provides a unified inbox, and `vibe skills distill` distills them into project-level skills in one click (LLM generation + full review + security audit).

### Degradation (v5.2.0+)

4-tier confidence degradation replacing binary fallback:

```
>= 0.6 → Auto-select    (AUTO)
>= 0.4 → Suggest        (SUGGEST)
>= 0.2 → Degrade        (DEGRADE)
< 0.2  → Raw LLM       (FALLBACK)
```

All thresholds are configurable. User-explicitly specified skills are unaffected by degradation.

### Proactive Discovery (v5.2.0+)

After every route, skills not yet used but matching the current workflow are automatically suggested, marked `[DISCOVER]`. Continuously discover skills in the ecosystem that fit your needs.

### Task Memory & Instinct Learning (v8.0+)

VibeSOP observes your real workflows and distills repeat patterns into reusable assets:

```bash
# Semantic recall of past task traces (embedding similarity, optional cross-project trust pool)
vibe recall "how did I fix that Windows path bug last time"

# Routing observability: span tracing, replay, and metrics
vibe trace metrics
vibe trace replay <trace-id>

# Instinct learning: mine skill candidates from session tool sequences
vibe analyze session
vibe instinct eval

# Skill distillation queue: repeated tasks → candidates → manual promote / dismiss
vibe skill scan-candidates
vibe skill promote <candidate-id>
```

- **Task-memory loop**: query → task_id derivation → trace clustering → gold status → `vibe recall` semantic recall
- **Instinct learning**: tool-sequence pattern mining + launchd background collection; mature candidates are promoted via `vibe instinct eval`
- **Discovery queue**: candidate clusters carry score/source/behavior tags (including agent-echo detection); promote attaches a shadow verifier badge (PASS/WARN, never blocks)
- **Cross-project pool**: `vibe pool` manages trusted projects; `vibe recall --cross-project` reuses experience distilled in other projects
- **Conversation mirror**: main session and sub-agent internals (thinking/tool_calls/usage) are fully mirrored for dashboard and replay

### Preference Learning

VibeSOP remembers your choices:

```bash
# First time
$ vibe route "帮我深入诊断并优化这个性能问题"
→ builtin/deep-diagnosis-optimization (82%)

# You use it and it works
$ vibe feedback record "帮我深入诊断并优化这个性能问题" "builtin/deep-diagnosis-optimization" --correct

# Next time
$ vibe route "帮我深入诊断并优化这个性能问题"
→ builtin/deep-diagnosis-optimization (89%) ← Boosted!
```

### Open Ecosystem

No platform lock-in — one skill definition, deployed per agent:

- ✅ Claude Code (hooks auto-injection)
- ✅ Grok Build (hooks auto-injection)
- ✅ Kimi CLI (config auto-injection)
- ✅ Pi Agent (extensions auto-injection)
- ✅ Cursor / OpenCode (config generation)
- ✅ Any agent that reads SKILL.md (bring your own wiring)

### Security Audit

Every external skill is security-scanned:

- ✅ Prompt injection detection
- ✅ Command injection detection
- ✅ Role hijacking detection
- ✅ Privilege escalation detection
- ✅ Path traversal protection

---

## Usage Examples

> Examples marked with a community skill id (e.g. `mattpocock/tdd`) assume that pack
> is installed (`vibe install mattpocock`). Builtin examples run on a fresh install.

### Debugging Errors

```bash
$ vibe route "帮我深入诊断并优化这个性能问题"

✅ Matched: builtin/deep-diagnosis-optimization
   Rationale: Error detected → Use debugging workflow
```

### Code Review

```bash
$ vibe route "review my changes before pushing"

✅ Matched: mattpocock/tdd
   Confidence: 93%
```

### Chinese Queries

```bash
$ vibe route "帮我重构这个函数"

✅ Matched: superpowers/refactor
   Confidence: 89%

$ vibe route "代码覆盖率太低怎么办"

✅ Matched: superpowers/tdd
   Confidence: 91%
```

### Brainstorming

```bash
$ vibe route "I need ideas for a new feature"

✅ Matched: mattpocock/grill-with-docs
   Confidence: 87%
   Rationale: "ideas" + "new feature" → design thinking
```

---

## Who Should Use VibeSOP?

### Developers

You're using AI-assisted development tools, but:

- ❌ Can't remember all the commands
- ❌ Don't know which skill fits the current scenario
- ❌ Want to switch tools without losing skills

**VibeSOP solves these problems for you!**

### Teams

You're adopting AI-assisted development, but:

- ❌ Team members use different skills
- ❌ Lack unified skill management
- ❌ Hard to track and share best practices

**VibeSOP provides unified skill management and routing!**

### Open Source Community

You're maintaining AI-assisted development tools, but:

- ❌ Inconsistent skill formats
- ❌ Hard to integrate external skills
- ❌ Lack cross-platform support

**VibeSOP provides standard SKILL.md format and cross-platform support!**

---

## CLI Reference

### Core Commands

```bash
# Route query to best skill
vibe route "<query>"

# Orchestrate complex multi-intent query
vibe orchestrate "<query>"

# Decompose query into sub-tasks (without routing)
vibe decompose "<query>"

# List all available skills
vibe skills available

# Show skill details
vibe skills info <skill-id>

# Install skill pack
vibe install <url-or-name>

# Check environment
vibe doctor
```

### Skills Management

```bash
# List installed skills
vibe skills list

# Show all skills including builtins
vibe skills available

# Show detailed skill information
vibe skills info <skill-id>

# Install from URL or name
vibe install mattpocock
vibe install https://github.com/user/skills

# Sync skills to platform
vibe skills sync claude-code
```

### Cross-Cutting Workflows (v7.0)

Cross-cutting workflows orchestrate multiple skills into a complete development pipeline (e.g. "diagnose → implement → verify → review"). VibeSOP's built-in `prompt-chain-validator` workflow implements a validated "dynamic prompt chain + container end-to-end verification" pattern for this repository:

```bash
# List all cross-cutting workflows
vibe workflows list-workflows

# Show workflow details
vibe workflows show prompt-chain-validator

# One-stop: diagnose → generate phased prompts → container verify
vibe prompt-chain run "Add Multi-Agent Squad capability to VibeSOP"

# Step-by-step execution
vibe prompt-chain diagnose "Multi-Agent Squad" --files="src/core/*.py"
vibe prompt-chain generate "Multi-Agent Squad" --output ./prompts
vibe prompt-chain validate --container orbstack --json
```

`vibe prompt-chain generate` outputs 7 `.md` prompt files (Phase 0 fan-out diagnosis → Phase 1-5 phased implementation → Final end-to-end verification), each independently feedable to Claude Code. `vibe prompt-chain validate` runs the full verification pipeline in a Linux container (orbstack/docker/lima auto-detected, or `--container local` for host), outputting a JSON report.

### Feedback Collection

```bash
# Record correct routing
vibe feedback record "<query>" "<skill>" --correct

# Record incorrect routing
vibe feedback record "<query>" "<skill>" --wrong "<actual-skill>"

# View feedback report
vibe feedback report
```

### Task Memory & Observability (v8.0+)

```bash
# Semantic recall of past task traces
vibe recall "<query>"
vibe recall "<query>" --cross-project   # recall across trusted project pool

# Routing observability: metrics and replay
vibe trace metrics
vibe trace replay <trace-id>

# Instinct learning: tool-sequence mining and promotion
vibe analyze session
vibe instinct eval
vibe instinct status

# Skill distillation queue (candidates → manual promote/dismiss, with shadow verifier badge)
vibe skill scan-candidates
vibe skill promote <candidate-id>
vibe skill dismiss <candidate-id>

# Cross-project trust pool management
vibe pool add / list / remove
```

### Session Intelligent Routing

> **⚠️ Enabled by default**: Session-aware tracking is **on** by default (`routing.session_aware: true`), automatically recording session state and supporting multi-turn conversation re-routing.
>
> **Why you might want to disable it?**
> - **Performance**: Some users want zero overhead
> - **Privacy**: Don't want to record tool usage history
> - **Control**: Fully user-decided whether to enable
>
> To disable:
> ```bash
> vibe config set routing.session_aware false
> ```

```bash
# Enable tracking (Claude Code)
vibe session enable-tracking

# Record tool usage (manual)
vibe session record-tool --tool "read" --skill "systematic-debugging"

# Check for re-routing suggestions
vibe session check-reroute "design new architecture" --skill "systematic-debugging"

# View session summary
vibe session summary
```

Full CLI reference: [docs/user/CLI_REFERENCE.md](docs/user/CLI_REFERENCE.md)

---

## Configuration

### Project-Level Config

Create `.vibe/config.toml`:

```yaml
# .vibe/config.toml
platform: claude-code

routing:
  min_confidence: 0.6
  enable_ai_triage: true
  enable_embedding: false
  max_candidates: 3
  confirmation_mode: ambiguous_only  # ambiguous_only (default) | always | never
  keyword_match_max_chars: 5  # max chars for keyword routing (0=always LLM, 200=always keyword)

  # Degradation: confidence-gated layered fallback (v5.2.0)
  degradation_enabled: true
  degradation_auto_threshold: 0.6    # >= this = auto-select
  degradation_suggest_threshold: 0.4 # >= this but < auto = suggest
  degradation_degrade_threshold: 0.2 # >= this but < suggest = degrade
  degradation_fallback_always_ask: true  # ask user before raw LLM

security:
  threat_level: medium
  scan_external: true

skills:
  namespaces:
    - builtin
    - mattpocock
    - superpowers
    - omx
```

#### User Confirmation Mode

Default `ambiguous_only`: routes with confidence ≥ `auto_select_threshold` (0.6) pass
through automatically (the threshold matches the degradation AUTO tier by default, but
the two are independently configurable). Confirmation is only prompted when confidence
is low or a multi-intent orchestration has disagreements:

```bash
$ vibe route "帮我 review 代码"
╭────────── 🔍 Routing Decision Report ──────────╮
│ Selected: mattpocock/tdd (confidence: 87%)      │
│ ...                                            │
╰────────────────────────────────────────────────╯
（≥ 0.6: auto-selected, continues directly）

$ vibe route "this query is a bit ambiguous"
How would you like to proceed?
  ✅ Confirm selected skill
  🔀 Choose a different skill
  📝 Skip skill, use raw LLM
```

Adjust it:

- **Confirm every time**: `routing.confirmation_mode = "always"` (the old default)
- **Temporary skip**: `vibe route "query" --yes` or `-y`
- **Fully off**: set `routing.confirmation_mode = "never"` in `~/.vibe/config.toml`

> 💡 **Why the default changed**: `always` conflicted with the fifth tenet of our
> philosophy — "Continuity > Startup / the bottleneck is the human, not the system."
> Requiring a manual confirmation on every route makes the system itself the
> bottleneck. `ambiguous_only` reserves the human gate for genuinely ambiguous
> decisions.

### Global Config

Create `~/.vibe/config.toml`:

```yaml
# ~/.vibe/config.toml
default_platform: claude-code
llm_provider: anthropic  # or openai

routing:
  enable_ai_triage: true
  use_cache: true

preferences:
  learning_enabled: true
```

---

## Integrations

### Claude Code

```bash
vibe build claude-code --output ~/.claude
# Shell hooks auto-trigger routing on UserPromptSubmit
```

### Kimi CLI

```bash
vibe build kimi-cli --output ~/.kimi-code
# Config hooks auto-trigger routing via config.toml
```

### Pi Agent

```bash
vibe build pi --output .pi
# TypeScript extensions auto-trigger routing
```

### OpenCode

```bash
vibe build opencode --output ~/.config/opencode
# Manual: source ~/.config/opencode/vibesop-env.sh && opencode
```

### Grok Build

```bash
vibe build grok-build --output ~/.grok
# Shell hooks auto-trigger routing on UserPromptSubmit
# (also collects PostToolUse tool sequences)
```

### Workflow Engine (v6.2.0+)

VibeSOP's dynamic workflow engine supports 6 orchestration patterns, automatically classifying user intent and selecting the best execution strategy.

**6 Workflow Patterns:**

| Pattern | Use Case |
|---------|----------|
| `SEQUENTIAL` | Linear dependency chain |
| `PARALLEL` | Independent concurrent tasks |
| `FAN_OUT` | One-to-many distribution |
| `ADVERSARIAL` | Independent critic verification |
| `LOOP_UNTIL_DRY` | Iterate until no new findings |
| `TOURNAMENT` | Best-of-N pairwise comparison |

```bash
# Force workflow pattern
vibe route --pattern fan_out "analyze architecture and optimize performance"

# Enable adversarial verification
vibe route --verify "refactor auth module"
```

**Platform Support:**

| Platform | Workflow | Native Parallel | Trigger |
|----------|----------|-----------------|---------|
| Claude Code | ✅ | ✅ Sub-agents | Auto (hooks) |
| Grok Build | ✅ | ⚠️ Serial only | Auto (hooks) |
| Kimi CLI | ✅ | ⚠️ Serial only | Auto (config) |
| Pi Agent | ✅ | ⚠️ Serial only | Auto (extensions) |
| OpenCode | ✅ | ⚠️ Serial only | Manual |

---

## Architecture

VibeSOP (v5.5.0+) introduces a **3-pillar architecture** (enhanced with Dynamic Workflow Engine):

| Pillar | Purpose | Artifacts |
|--------|---------|-----------|
| **The Spec** | Canonical SKILL.md v3.0 format | `spec/models.py`, 29 fields, `SpecValidator` |
| **The Reference** | 3 integration patterns | File-based, Hook-based, SDK-based adapters |
| **The Conformance Suite** | Any platform can verify compliance | 85 tests, `vibe spec conformance --all` |

```
┌─────────────────────────────────────────────────┐
│               AI Agent (Execution Layer)         │
│    Claude Code / Cursor / OpenCode / etc.        │
└────────────────────┬────────────────────────────┘
                     │ Execute skills
┌────────────────────▼────────────────────────────┐
│              VibeSOP SkillOS                     │
│                                                  │
│  ┌──────────────────────────────────────────┐   │
│  │         CLI / Agent Runtime Layer         │   │
│  │   vibe route │ orchestrate │ skill mgmt   │   │
│  └────────────────────┬─────────────────────┘   │
│                       │                         │
│  ┌────────────────────▼─────────────────────┐   │
│  │          UnifiedRouter (Routing Layer)    │   │
│  │   4-Stage Cascade:                        │   │
│  │   Explicit → Scenario+Index → AI Triage   │   │
│  │   → Matcher Aggregation → Fallback        │   │
│  └────────────────────┬─────────────────────┘   │
│                       │                         │
│  ┌────────────────────▼─────────────────────┐   │
│  │       TaskOrchestrator (Orchestration)    │   │
│  │   Multi-intent → Decompose → Plan         │   │
│  └────────────────────┬─────────────────────┘   │
│                       │                         │
│  ┌────────────────────▼─────────────────────┐   │
│  │      Skill Lifecycle Manager              │   │
│  │   Enable │ Scope │ Quality │ Retain/Depr  │   │
│  └────────────────────┬─────────────────────┘   │
│                       │                         │
│  ┌────────────────────▼─────────────────────┐   │
│  │        Integration Layer (Adapters)        │   │
│  │   Claude Code │ OpenCode │ Kimi CLI       │   │
│  └──────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

Detailed architecture docs: [docs/architecture/](docs/architecture/)

---

## Documentation

**📚 Complete Documentation Index**: [docs/INDEX.md](docs/INDEX.md)

### Core Documentation

- [docs/PHILOSOPHY.md](docs/PHILOSOPHY.md) - Core philosophy and mission (中文)
- [docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md) - System architecture
- [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) - Project context
- [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md) - Project status

### User Guides

- **🆕 [docs/SKILLS_GUIDE.md](docs/SKILLS_GUIDE.md)** - Complete skills ecosystem guide
  - 18 built-in + community pack skills explained (superpowers, omx, gstack)
  - 4-stage routing cascade
  - Priority decision mechanism
  - How to switch skills
- **🆕 [docs/agent-integration.md](docs/agent-integration.md)** - In-process Agent integration guide
  - `AgentRouter.set_llm()` reuses the host Agent's LLM, no API key needed
  - Multi-turn reroute / confidence awareness
- [docs/QUICKSTART_USERS.md](docs/QUICKSTART_USERS.md) - User quick start
- [docs/QUICKSTART_DEVELOPERS.md](docs/QUICKSTART_DEVELOPERS.md) - Developer quick start
- [docs/user/CLI_REFERENCE.md](docs/user/CLI_REFERENCE.md) - CLI command reference
- [docs/EXTERNAL_SKILLS_GUIDE.md](docs/EXTERNAL_SKILLS_GUIDE.md) - External skill development

### Skill Pack Guides

- **[docs/OMX_GUIDE.md](docs/OMX_GUIDE.md)** - oh-my-codex (OMX) complete guide
  - deep-interview, ralph, ralplan, team, ultrawork, autopilot, ultraqa
  - Usage scenarios and best practices

### Developer Documentation

- [docs/dev/CONTRIBUTING.md](docs/dev/CONTRIBUTING.md) - Contributing guide
- [docs/ROADMAP.md](docs/ROADMAP.md) - Roadmap
- [docs/CODE_OF_CONDUCT.md](docs/CODE_OF_CONDUCT.md) - Code of conduct
- [docs/SECURITY.md](docs/SECURITY.md) - Security policy

---

## Performance Metrics

### Routing Accuracy

| Metric | Value | Note |
|--------|-------|------|
| **Overall Accuracy** | **~90%** | Estimated from internal test set, not a standardized benchmark |
| **AI Triage Accuracy** | **~95%** | Estimated from sampled validation |
| **Scenario Matching Accuracy** | **~90%** | Estimated from keyword matching |
| **Semantic Ambiguity Accuracy** | **~90%** | Estimated from LLM evaluation |

### Response Time

| Operation | Time | Note |
|-----------|------|------|
| **Simple Routing** (cache hit) | ~10-50ms | P50 estimate, varies by hardware |
| **Complex Routing** (multi-layer) | ~200-300ms | Includes LLM Triage |
| **AI Triage** | ~200-300ms | Depends on LLM provider and network |

> ⚠️ **Performance Note**: The above figures are design targets and internal estimates, not standardized benchmark results. Actual performance varies by hardware, network, LLM provider, and skill count. A standardized benchmark suite is under construction.

---

## Comparison

### vs Other Tools

| Feature | VibeSOP | Cursor | Continue.dev | Aider |
|---------|---------|--------|--------------|-------|
| **Routing** | 4-stage cascade routing | Built-in commands | Extension-based | CLI flags |
| **Orchestration** | Multi-skill composition | No | No | No |
| **Lifecycle Mgmt** | Enable/disable, scope, evaluate | No | No | No |
| **Skills** | 18 built-in + community skill packs | Built-in features | Community extensions | Built-in workflows |
| **Learning** | Preference learning | Fixed | No | No |
| **Cross-Platform** | ✅ Per-agent config generation | ❌ Cursor only | ❌ Continue only | ❌ Aider only |
| **Open Ecosystem** | ✅ Any SKILL.md | ❌ Closed | ⚠️ Extension API | ❌ Closed |
| **Security Audit** | ✅ Before loading skills | N/A | ⚠️ User discretion | N/A |

### Why Choose VibeSOP?

1. **Not tied to one tool** — Switch from Cursor to Claude Code? Your skills come with you
2. **Discovers skills you didn't know existed** — "What can I do?" → `vibe skills available`
3. **Gets smarter over time** — Remembers what worked for you
4. **Open & extensible** — Create your own skills with a simple markdown file

---

## Development

```bash
# Type checking
uv run basedpyright

# Linting
uv run ruff check

# Formatting
uv run ruff format

# Testing (fast, parallel, ~30s)
make test-fast

# Full test suite with coverage (~4 min)
uv run pytest

# Test coverage
uv run pytest --cov=src/vibesop --cov-report=html
```

---

## Roadmap

For the full version history see [docs/ROADMAP.md](docs/ROADMAP.md)
(historical record) and the [version_05.md ADR](docs/archive/version_05.md).

---

## License

MIT License - see [LICENSE](LICENSE) file.

---

## Acknowledgments

VibeSOP stands on the shoulders of giants, integrating excellent AI engineering practices from the community:

### Community Integration

VibeSOP provides built-in support and intelligent routing for the following community skill packs:

- **[mattpocock/skills](https://github.com/mattpocock/skills)** by [@mattpocock](https://github.com/mattpocock)
  - 🎯 **Positioning**: High-quality engineering skills — TDD, diagnosis, architecture improvement, code review
  - 📦 **Skills**: 6+ skills (tdd, diagnose, grill-with-docs, improve-codebase-architecture, handoff, grill-me)
  - 🎨 **Features**: `.claude-plugin/plugin.json` registry format, focused skill design paradigm
  - ⚡ **Default install**: `vibe install` auto-installs

- **[superpowers](https://github.com/obra/superpowers)** by [@obra](https://github.com/obra)
  - 🎯 **Positioning**: Foundational development workflows — TDD, refactoring, debugging, optimization
  - 📦 **Skills**: 7 skills (tdd, refactor, debug, optimize, architect, review, brainstorm)
  - 🎨 **Features**: Development best practices, red-green-refactor cycle
  - 💡 **Best for**: Daily development tasks, personal workflow optimization

- **[oh-my-codex (OMX)](https://github.com/Yeachan-Heo/oh-my-codex)** by [@Yeachan-Heo](https://github.com/Yeachan-Heo)
  - 🎯 **Positioning**: Advanced engineering methodologies — structured thinking and systematic execution
  - 📦 **Skills**: 7 skills (deep-interview, ralph, ralplan, team, ultrawork, autopilot, ultraqa)
  - 🎨 **Features**: Requirements clarification, persistent execution, consensus planning, multi-agent parallelism
  - 📖 **Docs**: [OMX_GUIDE.md](docs/OMX_GUIDE.md) (complete usage guide)

- **[gstack](https://github.com/anthropics/gstack)** by [@brandonrobertz](https://github.com/brandonrobertz)
  - 🎯 **Positioning**: Virtual engineering team — engineering skills and browser automation
  - 📦 **Skills**: 19 skills (review, qa, ship, office-hours, browse, etc.)
  - 🎨 **Features**: Role-based skills (product, engineering, design, QA)
  - 💡 **Best for**: Requires explicit install `vibe install gstack` (not default)

### Core Technologies

- **[Claude Code](https://github.com/anthropics/claude-code)** by Anthropic
  - 📋 **Contribution**: SKILL.md specification standard
  - 🔧 **Integration**: VibeSOP is fully compatible with the SKILL.md spec
  - 📚 **Docs**: [SKILL.md Specification](docs/EXTERNAL_SKILLS_GUIDE.md)

### VibeSOP Unique Value

VibeSOP is not just a collection of these skill packs, but a **Skill Operating System (SkillOS)** that provides:

- 🧠 **Intelligent Routing** (~90% internal estimate) — Auto-selects the most suitable skill
- 🔄 **Unified Management** — One tool to manage all skill packs
- 🛡️ **Security Audit** — All external skills are security-scanned
- 📚 **Cross-Platform** — Use across Claude Code, Cursor, Continue.dev, and more
- 🎓 **Preference Learning** — Remembers your choices, gets more accurate over time

### Skill Selection Guide

**Detailed comparison**: See [OMX_GUIDE.md](docs/OMX_GUIDE.md#differences-from-other-skill-packs)

```
Unclear requirements? → OMX deep-interview (deep clarification)
TDD development? → mattpocock/tdd (red-green-refactor)
Code review? → mattpocock/grill-me (deep scrutiny)
Debug errors? → mattpocock/diagnose (systematic diagnosis)
Architecture improvement? → mattpocock/improve-codebase-architecture (domain-driven refactor)
Documentation design? → mattpocock/grill-with-docs (domain model challenge)
Full implementation? → OMX ralph (persistent execution + deslop)
Team decisions? → OMX ralplan (consensus planning + ADR)
Parallel tasks? → OMX team (multi-agent collaboration)
QA testing? → OMX ultraqa (architecture-driven)
Session handoff? → mattpocock/handoff (session transfer)
```

---

## Contact

**Built with ❤️ for AI-native developer workflows**

[GitHub](https://github.com/nehcuh/vibesop-py) • [Issues](https://github.com/nehcuh/vibesop-py/issues) • [Discussions](https://github.com/nehcuh/vibesop-py/discussions)

---

> 📖 [中文文档](README.zh-CN.md)
