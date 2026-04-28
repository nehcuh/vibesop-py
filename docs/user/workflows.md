# Workflow Orchestration

> **Version**: v5.3.0+  
> **Last Updated**: 2026-04-17

---

## Current Status

**Workflow CLI commands are not exposed in VibeSOP v4.0.0.**

VibeSOP has transitioned to a pure **routing engine** philosophy. As of v4.1.0, the following commands were removed:

- ❌ `vibe workflow run`
- ❌ `vibe workflow list`
- ❌ `vibe workflow resume`
- ❌ `vibe workflow validate`

This aligns with the core principle that VibeSOP **routes** queries to the right skill (via `SKILL.md` definitions), but does **not** execute them. Execution is the responsibility of your AI Agent (Claude Code, OpenCode, Cursor, etc.).

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
VibeSOP learns from your routing history. Enable it in `.vibe/config.yaml`:

```yaml
routing:
  enable_ai_triage: true

preferences:
  learning_enabled: true
```

See [Troubleshooting](troubleshooting.md) and [CLI Reference](../../CLI_REFERENCE.md) for more details.

---

*If you need programmatic pipeline orchestration, consider using the underlying Python APIs in `src/vibesop/core/` or external tools like `make`, `just`, or CI/CD pipelines.*
