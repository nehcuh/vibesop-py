---
id: builtin/slash-route
name: slash-route
description: Force trigger VibeSOP routing. Use when you need to explicitly route a query to the correct skill, or when routing was skipped. This is the primary user entry point for manual routing.
version: 2.0.0
tags: [routing, route, router, navigate, redirect, dispatch]
commands:
  - route
intent: routing
namespace: builtin
type: standard
user-invocable: true
---

# /route — Force Trigger Skill Routing

Manually triggers VibeSOP's routing engine. When the agent cannot or does not call `vibe route` proactively, the user can type `/route <query>` to force routing.

## Execution

Run the routing engine with the user's query:

```bash
vibe route "<QUERY>" --verbose
```

The output shows:
- **Matched skill** with confidence score
- **Routing decision tree** (which layers fired)
- **Alternative candidates**
- **Next step**: read `skills/<matched-skill>/SKILL.md`

## When to Use

- The agent didn't auto-route a complex request
- You want to verify which skill would handle a query
- You need the full routing transparency (decision tree)
- Multi-intent queries that need orchestration

## Examples

```
/route fix this null pointer bug
/route review this PR for security issues  
/route 帮我重构这个模块
/route design + implement a dark mode toggle
```

## After Routing

Once VibeSOP returns a recommendation:
1. Read the recommended skill file: `skills/<skill-id>/SKILL.md`
2. Follow the skill's workflow
3. Run verification when done
