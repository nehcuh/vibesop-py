---
name: experience-evolution
description: Project knowledge accumulation system - learn from practice, avoid repeating mistakes
version: 1.0.0
mode: observe-only
---

# Experience Evolution — Knowledge Accumulation System

> **Current mode: Observe-Only**
> Won't modify any files, only provides learning summary at session end.

## What This Skill Does

### Problem Scenarios
- Last week's API quota fix — forgot how to solve it this week
- Same TypeScript error recurring across different projects
- Performance optimization approach not recorded, hitting same bottleneck again
- Experience from one project can't be reused in another

### Solution
**Automatically remember** your successes and failures:
1. **After command execution**: Record successful build/test/deploy commands
2. **After bug fix**: Capture effective solutions and debug paths
3. **After optimization**: Save benchmark data and improvement metrics
4. **At session end**: Generate learning summary, ask whether to save permanently

## What Gets Observed

**Command Execution (Bash)**
- Successful build/test/deploy commands
- Failed commands and error messages
- Execution time (for performance comparison)

**File Modifications (Write/Edit)**
- Which files were modified
- Approximate scope (line count)
- Context (what feature was being worked on)

**Working Directory**
- Which project you're in
- Cross-project reusable patterns

## Session End Learning Summary

```
Session Learning Summary

Project: your-project
Duration: 45 minutes
Commands: 15 (13 success, 2 failed)

Reusable Patterns Found:

1. API Retry Mechanism (High Value)
   Scenario: API QUOTA_EXCEEDED
   Solution: Exponential backoff retry (1s, 2s, 3s)
   Effect: 95% of rate limit errors auto-recover
   Reuse potential: All external API calls

2. TypeScript Type Fix (Medium Value)
   Scenario: Union type narrowing issues
   Solution: Type guard functions
   Effect: Eliminated 12 type errors
   Reuse potential: Medium (specific to current structure)

Save these learnings?
[y] Yes, save to knowledge base (confirm each)
[n] No, skip this time
[v] View details
```

## Upgrade Path

**Phase 1 (Current): Observe Only** — No file writes, session-end summaries
**Phase 2: Write Logs** — Record to `learned/` directory, manual confirmation
**Phase 3: Semi-auto** — Low-risk auto-save, high-risk needs confirmation
**Phase 4: Cross-project** — Experience from project A auto-suggests in project B

## Safety Commitment

**Will never**:
- Modify project source code
- Auto-commit to Git
- Modify package.json or config files
- Execute dangerous commands

**Will only**:
- Observe command execution results
- Record to isolated skill directory
- Require explicit approval before persisting
