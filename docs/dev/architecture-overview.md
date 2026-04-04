# Architecture Overview

## VibeSOP is a Tool, Not a Consumer

VibeSOP is a CLI tool that generates and manages workflow SOPs (Standard Operating
Procedures) for AI-assisted development. It is NOT a consumer of the skills it produces.

### Two Roles

**VibeSOP (this project)** — The "skill factory":
- Discovers skills from filesystem (gstack, superpowers, builtin)
- Routes natural language queries to the right skill (5-layer routing)
- Generates platform configuration (Claude Code, OpenCode)
- Installs hooks, integrations, and workflows

**Your project** — The "skill consumer":
- Run `vibe install claude-code` to generate `.claude/` config
- The generated config includes skills, rules, hooks
- Your AI assistant (Claude Code) then uses those skills

### Why This Repo Doesn't Have Skills Installed

This is the source code of the tool itself. Installing VibeSOP's own output into
its own source repo would be circular. Skills are meant for project repos where
AI assistants help you write code — not for the tool's own development.

### Skill Discovery vs Skill Installation

- `vibe skills` — Lists all skills VibeSOP can route to (discovery)
- `vibe install <platform>` — Generates config with those skills for a target project
- `vibe route "query"` — Routes a query to the best skill (uses 5-layer system)
- `vibe auto "query"` — Detects intent + auto-executes the matched skill

### 5-Layer Routing Architecture

```
User Query → Layer 0: AI Triage (LLM)
              ↓ (no match)
            Layer 1: Explicit (/review, 使用 review)
              ↓ (no match)
            Layer 2: Scenario (debug/test/review/refactor keywords)
              ↓ (no match)
            Layer 3: Semantic (TF-IDF + cosine similarity)
              ↓ (no match)
            Layer 4: Fuzzy (Levenshtein distance)
              ↓ (no match)
            Fallback: riper-workflow
```

Each layer is implemented as a separate `RoutingHandler` class with a common
interface, registered in the `SkillRouter` handler chain.

### Key Modules

- `core/routing/` — 5-layer routing engine with pluggable handlers
- `triggers/` — Intent detection (keywords, regex, semantic)
- `semantic/` — Sentence transformer-based semantic matching
- `cli/` — Typer-based CLI with subcommand groups
- `workflow/` — Multi-stage workflow orchestration
- `security/` — Threat detection and path safety
- `adapters/` — Platform adapters (Claude Code, OpenCode)
- `builder/` — Configuration generation and rendering
- `hooks/` — Hook system for pre/post session events
- `integrations/` — External skill pack integration
- `installer/` — Installation and verification
