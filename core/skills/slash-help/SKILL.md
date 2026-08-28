---
id: builtin/slash-help
name: slash-help
description: Show all available VibeSOP slash commands and their usage.
version: 2.0.0
tags: [help, commands, reference, guide, slash, vibe, 帮助, 怎么用]
commands:
  - help
intent: help
namespace: builtin
type: standard
user-invocable: true
---

# /help — VibeSOP Command Reference

Show all available slash commands and usage.

## Execution

```bash
vibe route --slash "/vibe-help"
```

## Examples

```
/help
```

## All Available Commands

Run `/vibe-help` for the live list. Registered slash commands (prefix `/vibe-`):

- **/vibe-route** — Force trigger skill routing with transparency
- **/vibe-install** — Install skill packs
- **/vibe-analyze** — Deep project architecture analysis
- **/vibe-evaluate** — Evaluate skill quality and usage
- **/vibe-orchestrate** — Multi-skill orchestration for complex tasks
- **/vibe-list** — List installed skills and available packs
- **/vibe-help** — This reference

**/instinct** (learn, eval, status, export, import, evolve) works through skill routing, not the `/vibe-` registry — see `vibe instinct --help`.
