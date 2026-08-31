---
id: builtin/slash-analyze
name: slash-analyze
description: Deep project architecture and tech stack analysis. Detects project type, tech stack, and optionally file/line counts.
version: 2.0.0
tags: [analyze, architecture, tech stack, project, profile, 分析, 架构, 技术栈]
commands:
  - analyze
intent: analysis
namespace: builtin
type: standard
user-invocable: true
---

# /analyze — Project Architecture Analysis

Analyze the current project's architecture and tech stack.

## Execution

```bash
vibe route --slash "/vibe-analyze"          # project type + tech stack
vibe route --slash "/vibe-analyze --deep"   # also file and line counts
```

## Examples

```
/analyze
```

## What It Shows

- Detected project type
- Detected tech stack
- With `--deep`: file count and code line count
