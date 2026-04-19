# VibeSOP CLI Reference

Complete reference for all VibeSOP CLI commands.

---

## Table of Contents

- [Core Commands](#core-commands)
- [Skills Management](#skills-management)
- [Project Setup](#project-setup)
- [Analysis Commands](#analysis-commands)
- [Configuration](#configuration)
- [Preference Learning](#preference-learning)
- [Experimental Commands](#experimental-commands)
- [Legacy Commands](#legacy-commands)

---

## Core Commands

### `vibe route`

Route a natural language query to the appropriate skill.

```bash
vibe route <query> [options]
```

**Arguments:**
- `query` - Natural language query (required)

**Options:**
- `--min-confidence, -c` - Minimum confidence threshold (0.0-1.0)
- `--json, -j` - Output as JSON
- `--validate, -V` - Validate routing configuration
- `--explain, -e` - Explain routing decision (alias for `--validate`)

**Examples:**
```bash
# Basic routing
vibe route "help me debug this error"

# With confidence threshold
vibe route "review my code" --min-confidence 0.8

# JSON output
vibe route "test this" --json

# Validate routing
vibe route "debug" --validate

# Explain routing decision
vibe route "debug" --explain
```

**Output:**
```
✅ Matched: systematic-debugging
   Confidence: 95%
   Layer: scenario
   Source: builtin

💡 Alternatives:
   • gstack/investigate (82%)
   • superpowers/debug (75%)
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
⚠️  Hook Status: claude-code: 0/2; opencode: not installed

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
- `platform` - Target platform (claude-code, opencode, cursor)

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
- `platform` - Target platform (`claude-code`, `opencode`, `cursor`, `superpowers`)

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
| `vibe execute` | N/A | Violated "router not executor" principle |
| `vibe memory` | N/A | Internalized as routing engine feature |
| `vibe instinct` | N/A | Internalized as automatic learning |
| `vibe scan` | `vibe analyze security` | Merged into unified analyze |
| `vibe detect` | `vibe analyze integrations` | Merged into unified analyze |
| `vibe skill-info` | `vibe skills info` | Moved to skills subcommand |
| `vibe deploy` | N/A | Out of scope for routing engine |
| `vibe toolchain` | N/A | Out of scope for routing engine |
| `vibe worktree` | N/A | Out of scope for routing engine |
| `vibe checkpoint` | N/A | Out of scope for routing engine |
| `vibe hooks` | N/A | Out of scope for routing engine |

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | API key for Anthropic Claude |
| `OPENAI_API_KEY` | API key for OpenAI |
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
