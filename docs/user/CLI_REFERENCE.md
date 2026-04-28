# VibeSOP CLI Reference

Complete reference for all VibeSOP CLI commands.

---

## Table of Contents

- [Core Commands](#core-commands)
  - [`vibe route`](#vibe-route)
  - [`vibe status`](#vibe-status-v530)
  - [`vibe orchestrate`](#vibe-orchestrate)
  - [`vibe decompose`](#vibe-decompose)
  - [`vibe doctor`](#vibe-doctor)
  - [`vibe version`](#vibe-version)
  - [`vibe install`](#vibe-install)
- [Skills Management](#skills-management)
  - [`vibe skills`](#vibe-skills)
  - [`vibe skill cleanup`](#vibe-skill-cleanup-v530)
  - [`vibe skill stale`](#vibe-skill-stale)
  - [`vibe skill end-check`](#vibe-skill-end-check-v510)
  - [`vibe skill share`](#vibe-skill-share-v530)
  - [`vibe skill discover`](#vibe-skill-discover-v530)
  - [`vibe skills suggestions`](#vibe-skills-suggestions-v510)
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
- `--strategy, -s` - Force execution strategy: auto, sequential, parallel, hybrid

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

**Examples:**
```bash
# Install from registry shorthand
vibe install gstack

# Install from URL
vibe install https://github.com/anthropics/gstack

# Force reinstall
vibe install gstack --force
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
- `--grade, -g` - Filter by grade (A, B, C, D, F)
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

List all skills with their lifecycle state.

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
┌──────────────────────┬─────────────────┬────────┬─────────┬─────────┐
│ ID                   │ Name            │ State  │ Scope   │ Version │
├──────────────────────┼─────────────────┼────────┼─────────┼─────────┤
│ gstack/review        │ Code Review     │ active │ global  │ 2.1.0   │
│ systematic-debugging │ Debug Workflow  │ active │ global  │ 1.5.0   │
│ old-deploy-skill     │ Deploy Helper   │ deprecated│ global │ 0.9.0   │
└──────────────────────┴─────────────────┴────────┴─────────┴─────────┘
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
- `--auto, -a` - Automatically deprecate F-grade skills
- `--json, -j` - Output as machine-readable JSON

**Examples:**
```bash
vibe skill stale               # Report only
vibe skill stale --auto        # Auto-deprecate F-grade skills
vibe skill stale --json        # Machine-readable output
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
- Reads quality scores from `RoutingEvaluator` (A-F grades)
- Skills unused >30 days or with F-grade are flagged for deprecation
- `--auto` transitions flagged skills to DEPRECATED lifecycle state

---

#### `vibe skill cleanup` (v5.3.0+)

Interactively review and clean up low-quality or stale skills with checkbox selection.

```bash
vibe skill cleanup [options]
```

**Options:**
- `--auto, -a` — Apply all suggested deprecations and archives automatically
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

#### `vibe skill share` (v5.3.0+)

Publish a skill to the community via GitHub Issues. Opens a browser with a prefilled issue form, or uses `gh` CLI if installed.

```bash
vibe skill share <skill-id>
```

**Examples:**
```bash
# Share your custom skill
vibe skill share my-custom-linter

# Share a gstack skill variant
vibe skill share gstack/custom-review
```

---

#### `vibe skill discover` (v5.3.0+)

Browse community-shared skills from GitHub Issues, sorted by 👍 reactions.

```bash
vibe skill discover [query] [options]
```

**Arguments:**
- `query` — Optional search keywords to filter community skills

**Options:**
- `--json, -j` — Output as JSON

**Examples:**
```bash
# Browse all community skills
vibe skill discover

# Search for debugging-related skills
vibe skill discover debugging

# Search with keywords
vibe skill discover "python lint"
```

---

#### `vibe skills suggestions` (v5.1.0+)

View auto-detected skill suggestions from your repeated workflow patterns.

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
```

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

### Provider Detection Priority

When no `VIBE_LLM_PROVIDER` is set, VibeSOP auto-detects:

1. `OLLAMA_BASE_URL` or `OLLAMA_MODEL` env var → `ollama`
2. `ANTHROPIC_API_KEY` → `anthropic`
3. `OPENAI_API_KEY` → `openai`
4. Default → `ollama`

### Configuration File

```yaml
# .vibe/config.yaml
llm:
  provider: ollama
  model: Qwen3.6-35B-A3B-mlx-mxfp8
  temperature: 0.3
  max_tokens: 500
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

### Removed Commands (v4.1.0)

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
- [Architecture Overview](architecture/README.md) - System design
- [Positioning & Philosophy](POSITIONING.md) - Design principles
