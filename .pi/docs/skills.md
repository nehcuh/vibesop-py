# Skill Catalog

> **On-Demand**: Loaded when referenced

## How to Use Skills

```bash
# Route to the best skill for your request
vibe route "<your request>"

# View a specific skill's definition
vibe skills info <skill-id>

# List all available skills
vibe skills list
```

After `vibe route`, read the `skill_file` / `NEXT STEP` path it prints —
that is the real skill body location. A generated tree may exist at
`.pi/skills/<skill-id>/SKILL.md`, but it can be empty: do not guess paths,
follow the routing result.

Use Pi's `read` tool to load the skill file at the `skill_file` path the
routing result prints:
```
read <skill_file>
```

## Installing New Skill Packs

```bash
vibe install <pack-name>
vibe install https://github.com/user/skills
```

After installation, run `vibe sync` to update the skill index.

## Pi Prompt Templates

Pi-specific commands are available as prompt templates (type `/` in the editor):

- `/vibe-route` — Route a request to a skill
- `/vibe-install` — Install a skill package
- `/vibe-list` — List all skills
- `/vibe-help` — Show help
- `/vibe-orchestrate` — Multi-skill orchestration

---
*Part of VibeSOP skill documentation*