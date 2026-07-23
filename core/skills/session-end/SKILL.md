---
id: builtin/session-end
name: session-end
description: Session wrap-up - update handoff + commit + auto-record experience
tags: [session, wrap, handoff, commit, summary, end, 会话, 结束, 总结,
       done, finished, leaving, heading out, wrap up, that's all, gotta go,
       离开, 走了, 拜拜, 再见, 先撤, 就到这里, 今天就到这里]
triggers:
  - "that's all for now"
  - "heading out"
  - "I'm leaving"
  - "I'm done"
  - "gotta go"
  - "我要离开了"
  - "先走了"
  - "收工"
  - "拜拜"
  - "今天就到这里"
  - "session end"
  - "/session-end"
version: 2.1.0
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
intent: Session end and wrap-up — capture handoff, update memory, and commit changes when the user signals they are leaving or done
namespace: builtin
type: prompt
---

# Session End — Wrap-up Workflow

> Trigger: `/session-end` or exit signals ("that's all for now" / "heading out")

## Core Steps (8 steps)

### 1. Experience Recording

Review the session for valuable learnings:

**Recording threshold (must meet at least one)**:
- Reusability: Next time encountering similar problem, can look it up directly
- Counter-intuitive: Violates common assumptions
- High cost: Took >10 minutes cumulative

**Don't record**:
- One-shot small fixes
- Project-specific temporary config
- Issues already in project-knowledge.md

**Write target**:
- Technical pitfalls → `memory/project-knowledge.md` (Technical Pitfalls section)
- Reusable patterns → `memory/project-knowledge.md` (Reusable Patterns section)
- Architecture decisions → `memory/project-knowledge.md` (Architecture Decisions section)

### 2. session.md Hot Data Layer

Append to `memory/session.md` under `## Current Session`:

```markdown
### SN (HH:MM~) [project/topic]
- [1-2 sentences of what was done]
- [Important decisions/discoveries]
- [Next steps]
- [Recorded: yes/no - brief description]
```

Also update `## In-Flight Tasks (Cross-Session)` if applicable:
- Tasks progressed → Update context/next_action/updated
- New multi-session tasks → Append new entry
- Completed tasks → Remove (session.md already has the completion record)
- Blocker resolved → Change status from blocked to active

### 3. overview.md Status Refresh (if needed)

**Identify projects touched in this session** (from session.md, changed files, conversation content).

**Goals section update**:
- **Completed** → Remove entry (session.md already has the record)
- **Progress made** → Update description
- **New important item discovered** → Add to current week (max 5 items)

**Projects Summary update** (only rows for touched projects):
- Metric changes → Update (e.g. follower count, stars, metrics)
- Status changes → Update (e.g. "not started" → "first version shipped")

### 4. PROJECT_CONTEXT.md Handoff

**Check if file exists**:
- If `PROJECT_CONTEXT.md` exists → Update `<!-- handoff:start/end -->` block
- If file does NOT exist → Create the file with initial structure and add handoff

**File structure (when creating)**:
```markdown
# Project Context

## Session Handoff

<!-- handoff:start -->
### [Date] [Time]
- [Session summary]
- [Key decisions]
- [Next steps]
<!-- handoff:end -->
```

**When updating (if file exists)**:

Update the `<!-- handoff:start/end -->` block with current session summary.

**Auto-trim (every execution)**:
- Keep only **latest + 1 previous** handoff block within markers
- Delete older handoffs (git history has full record)
- Target: SESSION_HANDOFF section ≤80 lines

**Note**: PROJECT_CONTEXT.md is automatically created if it doesn't exist, ensuring session continuity across conversations.

### 5. Git Commit (when there are changes)

```bash
git add [specific files]  # Never git add .
git commit -m "[type]: [description]"
```

### 6. Instinct Learning

**Condition**: Session had ≥5 tool calls.

Run the two commands that close the instinct loop. Both are idempotent —
no-op if there's nothing new, so always-safe to invoke.

```bash
# (a) Mine this session's tool sequences for skill candidates.
#     Reads the current session jsonl, looks for repeated tool patterns,
#     surfaces anything crossing min-frequency / min-confidence thresholds.
vibe analyze session

# (b) Promote any sequence candidates that have matured during the session
#     into skill suggestions. Reads .vibe/instincts.jsonl (the live store,
#     not memory/instincts.yaml — the latter was a stale doc reference).
vibe instinct eval

# (c) Show the current instinct inventory (optional, for visibility).
vibe instinct status
```

**What each command does**:
- `vibe analyze session` → `SessionAnalyzer` reads `.vibe/session.jsonl`
  (or platform equivalent), extracts repeated tool-call patterns,
  outputs skill suggestions. Use `--auto-craft` to auto-create them.
- `vibe instinct eval` → `InstinctLearner.get_sequence_candidates()`
  returns candidates with ≥5 occurrences and ≥80% success rate; those
  get fed to `SkillSuggestionCollector` for review.
- `vibe instinct status` → inventory by confidence band.

**Output**:
```
Instincts: [analyze: N suggestions / eval: M promoted / status: K total]
```

**Skipped silently when**: `vibe` CLI not found, or `.vibe/instincts.jsonl`
doesn't exist (no routing has happened yet).

### 7. Content Mining (Optional)

**Condition**: session.md has ≥3 session records for the day.

Quick scan session.md for 1-2 findings with sharing potential (counter-intuitive / data-driven / pitfall-to-solution).

**Output (when found)**:
```
Content material: Found N shareable discoveries today
  1. [Title] — [one-line angle]
  2. [Title] — [one-line angle]
```

**Nothing found**: Skip silently.

### 8. Skill Craft Trigger (Optional)

**Condition**: One of the following triggers is met.

Check for skill crafting opportunities:

**Trigger 1: Accumulation**
- Count sessions since last skill-craft
- If ≥10 sessions (configurable), prompt user

**Trigger 2: Project Completion**
- Detect recent merge/push to main branch
- Check if this completed a feature (from commit messages)

**Trigger 3: Periodic Review**
- Check if it's been ≥7 days since last skill review
- Day of week check (e.g., Friday afternoon)

**Output (when triggered)**:
```
Skill Craft: [Trigger type detected]
  - Sessions accumulated: N since last review
  - Patterns available: ~M candidates
  
  Run /skill-craft to extract personal skills? [hint]
```

**Configuration** (in `~/.claude/config/skill-craft.yaml`):
```yaml
triggers:
  accumulation_threshold: 10    # sessions before prompt
  periodic_interval: 7          # days between reviews
  max_prompts_per_day: 1        # don't spam user
```

**Not triggered**: Skip silently.

## Output Format

```
Experience: [Recorded N items / None needed]
session.md updated
overview.md: [goals updated / projects updated / no changes]
PROJECT_CONTEXT.md: [updated / created]
Committed [N] files
Instincts: [Extracted N / Updated M / No new patterns]
Content material: [N items / none (<3 sessions)]
Skill Craft: [triggered - N sessions accumulated / not triggered]
```

## Migration Notes

> This skill was updated for the 3-tier memory architecture (v2.0.0).
> 
> Old files replaced:
> - `memory/today.md` → `memory/session.md`
> - `memory/active-tasks.json` → inline in `memory/session.md`
> - `memory/goals.md` + `memory/projects.md` + `memory/infra.md` → `memory/overview.md`
> - `patterns.md` → `memory/project-knowledge.md` (Reusable Patterns section)
