# Workflow Orchestration

> **Version**: v8.1.3+  
> **Last Updated**: 2026-04-17

---

## Current Status

**Workflow orchestration is available via `vibe workflows` CLI (v5.3.0+).**

VibeSOP manages the full skill lifecycle including cross-cutting workflows.
Historical commands removed in v4.1 (now superseded):

- ❌ `vibe workflow run` → Use `vibe route` or `vibe orchestrate`
- ❌ `vibe workflow list` → Use `vibe workflows list`
- ❌ `vibe workflow resume` → Use orchestration plan resumption
- ❌ `vibe workflow validate` → Use `vibe workflows show <id>`

Skills are defined via SKILL.md; execution is the responsibility of your AI Agent (Claude Code, Cursor, OpenCode). VibeSOP provides routing, orchestration, and lifecycle management.

---

## What You Can Do Instead

### 1. Use Skill-Based Workflows
Many skills in the ecosystem define multi-step workflows directly inside their `SKILL.md` files. For example:

- `riper-workflow` — Structured 5-phase development workflow
- `systematic-debugging` — Step-by-step debugging methodology
- `session-end` — Wrap-up and handoff procedures

Simply route to the skill and let your AI Agent execute the steps:

```bash
vibe route "start a new project with planning"
# → Matched: riper-workflow
```

### 2. Preference Learning
VibeSOP learns from your routing history. Enable it in `.vibe/config.toml`:

```toml
[routing]
enable_ai_triage = true

[preferences]
learning_enabled = true
```

See [Troubleshooting](troubleshooting.md) and [CLI Reference](CLI_REFERENCE.md) for more details.

---

*If you need programmatic pipeline orchestration, consider using the underlying Python APIs in `src/vibesop/core/` or external tools like `make`, `just`, or CI/CD pipelines.*
