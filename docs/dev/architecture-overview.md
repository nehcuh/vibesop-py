# Architecture Overview

## VibeSOP is a Tool, Not a Consumer

VibeSOP is a CLI tool that generates and manages workflow SOPs (Standard Operating
Procedures) for AI-assisted development. It is NOT a consumer of the skills it produces.

### Two Roles

**VibeSOP (this project)** — The "skill router":
- Discovers skills from filesystem (gstack, superpowers, builtin)
- Routes natural language queries to the right skill (10-layer routing)
- Generates platform configuration (Claude Code, OpenCode)
- Manages skill installations and integrations

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
- `vibe route "query"` — Routes a query to the best skill (uses 10-layer system)
- `vibe route --validate` — Shows routing decision path and diagnostics

### 10-Layer Routing Architecture

```
User Query → Layer 0: Explicit (/review, 使用 review)
              ↓ (no match)
            Layer 1: Scenario (debug/test/review/refactor keywords)
              ↓ (no match)
            Layer 2: AI Triage (LLM, optional — forced for long queries >5 chars by default)
              ↓ (no match)
            Layer 3: Keyword (exact token matching, short queries only)
              ↓ (no match)
            Layer 4: TF-IDF Semantic (cosine similarity)
              ↓ (no match)
            Layer 5: Embedding (vector-based semantic)
              ↓ (no match)
            Layer 6: Fuzzy (Levenshtein distance)
              ↓ (no match)
            Layer 7: Custom Plugin Matchers
              ↓ (no match)
            Layer 8: No Match (below threshold)
              ↓ (no match)
            Layer 9: Fallback LLM (last-resort routing)
```

Each layer is implemented as a separate `RoutingHandler` class with a common
interface, registered in the `SkillRouter` handler chain.

### Key Modules

- `core/routing/` — 10-layer intelligent routing with pluggable handlers
- `core/matching/` — Matching algorithms (keyword, TF-IDF, embedding, fuzzy)
- `core/optimization/` — Preference boost, instinct learning, conflict resolution
- `cli/` — Typer-based CLI with subcommand groups
- `security/` — Threat detection and path safety
- `adapters/` — Platform adapters (Claude Code, OpenCode)
- `builder/` — Configuration generation and rendering
- `integrations/` — External skill pack integration
- `installer/` — Installation and verification
