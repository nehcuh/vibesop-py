---
id: builtin/slash-analyze
name: slash-analyze
description: Deep project architecture and tech stack analysis. Understand the current project structure, dependencies, and technology choices.
version: 2.0.0
tags: [analyze, analysis, architecture, project, inspect, tech-stack]
commands:
  - analyze
intent: analysis
namespace: builtin
type: standard
user-invocable: true
---

# /analyze — Deep Project Analysis

Analyzes the current project's architecture, tech stack, and structure.

## Execution

```bash
vibe analyze
# Deep analysis:
vibe analyze --deep
# JSON output:
vibe analyze --deep --json
```

## Examples

```
/analyze
/analyze --deep
```

## What It Shows

- Project type and structure
- Technology stack and dependencies
- File count and code lines (with `--deep`)
