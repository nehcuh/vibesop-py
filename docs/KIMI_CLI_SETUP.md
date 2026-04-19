# Kimi CLI Setup Guide

> **Last Updated**: 2026-04-19
> **Status**: ✅ Working

## Overview

VibeSOP provides a Kimi Code CLI adapter that generates:
- `config.toml` - VibeSOP configuration fragment (security, routing)
- `skills/*/SKILL.md` - Individual skill definitions (flattened names like `gstack-qa`)
- `README.md` - Usage guide and skill catalog

**Important**: VibeSOP generates a **configuration fragment** that should be merged with Kimi CLI's auto-generated default configuration. Do not replace the entire config file.

## Quick Start

### 1. Generate VibeSOP Configuration

```bash
vibe build kimi-cli
```

This generates VibeSOP configuration in `.vibe/dist/kimi-cli/`.

### 2. Initialize Kimi CLI (First Time Only)

```bash
# Run Kimi CLI - it will auto-generate default config
kimi

# In the Kimi CLI prompt, authenticate:
/login
```

Follow the browser authentication flow. This will configure your API key automatically.

### 3. Merge VibeSOP Configuration

```bash
# Backup existing config
cp ~/.kimi/config.toml ~/.kimi/config.toml.backup

# Append VibeSOP configuration to existing config
cat .vibe/dist/kimi-cli/config.toml >> ~/.kimi/config.toml
```

Or manually copy the `[vibesop.*]` sections from the generated config to your `~/.kimi/config.toml`.

### 4. Deploy Skills

**Option A: User-level skills (global)**

```bash
# Remove old skills
rm -rf ~/.kimi/skills

# Deploy new skills
cp -r .vibe/dist/kimi-cli/skills ~/.kimi/
```

**Option B: Project-level skills (auto-discovered when inside project)**

```bash
# Create project-level skills directory
mkdir -p .kimi/skills

# Deploy skills to project
cp -r .vibe/dist/kimi-cli/skills/* .kimi/skills/
```

When using project-level skills, Kimi CLI automatically discovers them when you run `kimi` inside the project directory.

### 5. Verify Installation

```bash
kimi --version
# Output: kimi, version 1.36.0

# List available skills
ls ~/.kimi/skills/
```

## Authentication Methods

### Method 1: /login Command (Recommended)

```bash
kimi
> /login
```

This opens a browser for authentication. Kimi CLI will automatically add the `api_key` field to your configuration.

### Method 2: Environment Variable

```bash
export KIMI_API_KEY="sk-your-api-key"
```

Add this to your `~/.zshrc` or `~/.bashrc` for persistence.

### Method 3: Manual Configuration (Not Recommended)

Edit `~/.kimi/config.toml` and add the api_key field:

```toml
[providers.kimi-for-coding]
type = "kimi"
base_url = "https://api.kimi.com/coding/v1"
api_key = "sk-your-actual-api-key-here"
```

## Configuration Structure

### What VibeSOP Generates

VibeSOP generates **only** the VibeSOP-specific configuration:

```toml
# VibeSOP Security Settings
[vibesop.security]
scan_external_content = true
max_file_size_mb = 10.0

# VibeSOP Routing Settings
[vibesop.routing]
enable_ai_routing = true
confidence_threshold = 0.6
```

### What Kimi CLI Auto-Generates

When you first run `kimi`, it creates:

```toml
[providers.kimi-for-coding]
type = "kimi"
base_url = "https://api.kimi.com/coding/v1"
api_key = "sk-xxx"  # Added by /login command

[models.kimi-for-coding]
provider = "kimi-for-coding"
model = "kimi-for-coding"
max_context_size = 262144
```

## Complete Configuration Example

After merging, your `~/.kimi/config.toml` should contain both Kimi CLI's default configuration and VibeSOP's additions:

```toml
# Kimi CLI Default Configuration
default_model = "kimi-for-coding"
default_thinking = false
default_yolo = false
merge_all_available_skills = true

[providers.kimi-for-coding]
type = "kimi"
base_url = "https://api.kimi.com/coding/v1"
api_key = "sk-xxx"  # Configured via /login

[models.kimi-for-coding]
provider = "kimi-for-coding"
model = "kimi-for-coding"
max_context_size = 262144

[loop_control]
max_steps_per_turn = 500
max_retries_per_step = 3

[background]
max_running_tasks = 4

# VibeSOP Configuration
[vibesop.security]
scan_external_content = true
max_file_size_mb = 10.0

[vibesop.routing]
enable_ai_routing = true
confidence_threshold = 0.6
```

## What Gets Generated

- **44 Skills** total:
  - 7 builtin skills (systematic-debugging, verification-before-completion, etc.)
  - 7 superpowers skills (tdd, brainstorm, refactor, etc.)
  - 19 gstack skills (office-hours, plan-ceo-review, qa, ship, etc.)
  - 7 omx skills (deep-interview, ralph, ralplan, team, etc.)
  - 4 custom skills (riper-workflow, using-git-worktrees, etc.)

## Troubleshooting

### Error: "Field required: api_key"

**Cause**: VibeSOP config fragment doesn't include providers section (by design).

**Solution**: Run `kimi` first to generate default config, then use `/login` to authenticate.

**Do not** replace the entire `~/.kimi/config.toml` with VibeSOP's generated file. Merge only the `[vibesop.*]` sections.

### Error: "Control characters not allowed in strings"

**Cause**: Multi-line descriptions with newlines in TOML strings.

**Fix**: VibeSOP automatically escapes strings by:
- Removing newlines (replacing with spaces)
- Escaping quotes (`"` → `\"`)
- Collapsing multiple spaces

Generated by VibeSOP's `_escape_toml_string()` method.

### Skills Not Loading

**Check**:
1. Skills directory exists: `~/.kimi/skills/` (or `.kimi/skills/` for project-level)
2. Each skill has `SKILL.md` file directly inside its directory (no nested subdirectories)
3. Skill directory names use only lowercase letters, numbers, and hyphens (e.g., `gstack-qa`, not `gstack/qa`)
4. `merge_all_available_skills = true` in config.toml (optional, only needed if using multiple brand directories)

### First Time Setup Issues

If you encounter errors on first run:

1. Remove existing config: `rm ~/.kimi/config.toml`
2. Run `kimi` - it will regenerate default config
3. Use `/login` to authenticate
4. Merge VibeSOP config fragment

## File Locations

| File | Location |
|------|----------|
| Generated VibeSOP config | `.vibe/dist/kimi-cli/config.toml` |
| Generated skills | `.vibe/dist/kimi-cli/skills/` |
| Kimi CLI main config | `~/.kimi/config.toml` |
| Deployed skills | `~/.kimi/skills/` |
| Kimi CLI logs | `~/.kimi/logs/kimi.log` |

## Adapter Implementation

The Kimi CLI adapter is implemented in:
- `src/vibesop/adapters/kimi_cli.py`
- `src/vibesop/adapters/base.py` (base class)

Key methods:
- `render_config()` - Generates VibeSOP config fragment with skills
- `_generate_config()` - Creates TOML content with VibeSOP-specific settings
- `_escape_toml_string()` - Safely escapes multi-line strings for TOML

## Related Documentation

- [Skills Ecosystem Guide](SKILLS_GUIDE.md) - Complete guide to all 44 skills
- [OMX Guide](OMX_GUIDE.md) - Deep dive into OMX skill pack
- [Kimi CLI Official Docs](https://moonshotai.github.io/kimi-cli/)
- [Architecture](architecture/ARCHITECTURE.md) - System architecture

## Sources

- [Kimi CLI 命令参考](https://moonshotai.github.io/kimi-cli/zh/reference/kimi-command.html)
- [Kimi CLI 配置文件文档](https://moonshotai.github.io/kimi-cli/zh/configuration/config-files.html)
- [使用Kimi CLI 调用Kimi 大模型](https://platform.kimi.com/docs/guide/kimi-cli-support)

---

*Generated by VibeSOP*
