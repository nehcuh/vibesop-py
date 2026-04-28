---
id: builtin/slash-install
name: slash-install
description: Install skill packs from trusted sources. Downloads and registers skill packs (gstack, superpowers, omx) into the central skill storage with platform symlinks.
version: 2.0.0
tags: [install, setup, pack, skills, download]
commands:
  - install
intent: setup
namespace: builtin
type: standard
user-invocable: true
---

# /install — Install Skill Packs

Install skill packs from trusted sources into VibeSOP's central storage.

## Execution

```bash
vibe install <pack-name>
# or:
uv run vibe install <pack-name>
```

Available packs: `gstack`, `superpowers`, `omx`

## Examples

```
/install gstack
/install superpowers
```

## After Installation

Run `vibe status` to verify all packs are healthy.
