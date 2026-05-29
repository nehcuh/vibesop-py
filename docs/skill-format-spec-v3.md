# SKILL.md Format Specification v3.0

**Version**: 3.0
**Status**: Current (supersedes v1.0 and v2.0)
**Date**: 2026-05-28

## Overview

This document defines the canonical format for SKILL.md files — the standard
unit of AI-assisted development skills. Any platform, IDE, or AI agent that
implements this specification can discover, load, and execute skills defined
in this format.

A SKILL.md file is a Markdown file with YAML frontmatter. The frontmatter
contains structured metadata; the body contains the skill's instructions
(prompt template, workflow steps, or command specification).

## Specification Versions

| Version | Status | Key Changes |
|---------|--------|------------|
| 1.0 | Deprecated | Basic metadata: id, name, description, type, tags |
| 2.0 | Deprecated | Added llm_config, source_config, priority, routing_patterns |
| 3.0 | **Current** | Unifies all definition models; adds commands, user_invocable, allowed_tools, mode, keywords, lifecycle, scope, capabilities, algorithms, deprecation_reason |

### Migration from v1/v2

- `skill_type` key is renamed to `type` in v3 (both accepted for backward compatibility)
- `keywords` is now separate from `tags` (previously an undocumented alias)
- `intent` becomes optional — auto-derived from `description` if absent
- `type: standard` is now a valid value (was silently rejected before v3)
- All previously discarded fields (commands, user_invocable, allowed_tools, mode) are now captured

## Frontmatter Schema

### Required Fields

| Field | Type | Description |
|-------|------|------------|
| `id` | string | Unique skill identifier, e.g. `"gstack/review"` |
| `name` | string | Human-readable name |
| `description` | string | What the skill does |
| `version` | string | SemVer version, e.g. `"1.2.3"` |

### Identity Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `author` | string | `""` | Skill author or maintainer |
| `namespace` | string | `"builtin"` | Skill namespace: `builtin`, `gstack`, `superpowers`, `project` |

### Type & Intent

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `type` | enum | `"prompt"` | Skill type: `prompt`, `workflow`, `command`, `hybrid`, `standard` |
| `intent` | string | auto-derived | What the skill does (used for routing). Auto-derived from description if absent. |

### Routing Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `trigger_when` | string | `""` | Natural language trigger condition |
| `triggers` | list[string] | `[]` | Trigger phrases for keyword matching |
| `routing_patterns` | list[string] | `[]` | Regex/natural-language patterns for scenario routing |
| `priority` | int | `50` | Routing priority 1–100 (higher = preferred) |

### Categorization

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `tags` | list[string] | `[]` | Categorization tags |
| `keywords` | list[string] | `[]` | Search keywords (distinct from tags) |
| `category` | string | `"development"` | Category: `development`, `testing`, `ops`, `docs`, etc. |

### Capabilities

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `capabilities` | list[string] | `[]` | Capability tags: `analysis`, `review`, `design`, `debug`, `refactor`, `plan`, `test` |
| `algorithms` | list[string] | `[]` | Algorithmic strategies used |

### Command Interface

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `commands` | list[string] | `[]` | CLI sub-commands this skill provides |
| `user_invocable` | bool | `false` | Whether user can invoke via slash command |
| `allowed_tools` | list[string] | `[]` | Allowed tool names, e.g. `["Read", "Write", "Bash"]` |

### Operational

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `mode` | string | `""` | Operational mode, e.g. `"observe-only"` |

### Lifecycle & Scope

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `lifecycle` | enum | `"active"` | `draft`, `active`, `deprecated`, `archived` |
| `scope` | string | `"global"` | `global` (all projects) or `project` (specific project) |
| `enabled` | bool | `true` | Whether enabled for routing |
| `deprecation_reason` | string | `null` | Explanation if deprecated |

### Dependencies

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `dependencies` | list[string] | `[]` | Required pip packages |
| `env_vars` | list[string] | `[]` | Required environment variables |

### LLM Configuration

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `llm_config.provider` | string | `null` | LLM provider name |
| `llm_config.model` | string | `null` | Model identifier |
| `llm_config.temperature` | float | `null` | Sampling temperature |
| `llm_config.api_key` | string | `null` | API key (env var name) |
| `llm_config.api_base` | string | `null` | API base URL |
| `llm_config.parameters` | dict | `{}` | Provider-specific parameters |
| `llm_config.fallback` | string | `null` | Fallback provider |

### Source Configuration

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `source_config.type` | string | `"github"` | Source type: `github`, `url`, `local` |
| `source_config.repository` | string | `null` | Git repository URL |
| `source_config.checksum` | string | `null` | Content checksum for verification |
| `source_config.ref` | string | `null` | Git ref (branch, tag, commit) |

### Display & Metadata

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `confidence` | float | `0.5` | Default confidence 0.0–1.0 |
| `auto_configured` | bool | `false` | Whether config was auto-detected |
| `metadata` | dict | `{}` | Extension point for non-standard fields |

## Complete Example

```markdown
---
id: gstack/review
name: Code Review
description: Review code changes for quality, security, and style
version: 1.2.0
author: gstack
namespace: gstack
type: standard
intent: review
trigger_when: User asks for code review or PR feedback
triggers:
  - review
  - code review
  - pr review
tags:
  - review
  - quality
keywords:
  - code review
  - pull request
  - merge request
  - peer review
category: development
priority: 80
capabilities:
  - review
  - analysis
commands:
  - review
user_invocable: true
allowed_tools:
  - Read
  - Bash
  - Grep
lifecycle: active
scope: global
enabled: true
dependencies:
  - ruff
  - mypy
env_vars:
  - GH_TOKEN
llm_config:
  provider: anthropic
  model: claude-sonnet-4-6
  temperature: 0.3
source_config:
  type: github
  repository: https://github.com/gstack/skills
---

# Code Review Skill

## Instructions

When reviewing code changes, focus on:
1. Security vulnerabilities (OWASP Top 10)
2. Code quality and readability
3. Test coverage and edge cases
...
```

## Validation

The `vibe spec validate` command checks SKILL.md files for compliance:

```bash
vibe spec validate --path ./SKILL.md     # Validate a single file
vibe spec validate --all                  # Validate all installed skills
vibe spec version                         # Show spec version info
```

A valid SKILL.md MUST have:
- Non-empty `id`, `name`, `description`, and `version`
- A valid `type` value from the enumerated list
- SemVer-compatible `version` string

Implementations SHOULD warn on:
- Missing optional fields that affect routing quality
- v1/v2 naming conventions that should migrate to v3
- Version strings that don't look like SemVer

## .skill Archive Format

A `.skill` file is a gzipped tar archive containing:

```
my-skill.skill
├── SKILL.md          # Required: skill definition
├── requirements.txt  # Optional: pip dependencies
├── hooks/            # Optional: platform-specific hooks
│   ├── pre-session-end.sh
│   └── post-session-start.sh
└── templates/        # Optional: prompt templates
    └── review.md.j2
```

The SKILL.md at the archive root is the entry point. All other files are
optional and platform-specific.
