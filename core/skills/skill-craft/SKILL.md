---
name: skill-craft
description: Craft personal skills from session history - extract patterns, generate reusable skills
tags: [skill, craft, generate, template, 技能, 生成]
version: 1.0.0
commands:
  - skill-craft
  - craft-review
  - craft-generate
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
---

# Skill Craft — Personal Skill Generation System

> **Transform your successful workflows into reusable skills**
> Learn from your own experience, build your personal knowledge base.

## What This Skill Does

### The Problem
- You've solved similar problems multiple times, but solutions aren't documented
- Successful workflows stay in chat history, never formalized
- Team members repeat the same learning curve
- Generic skills don't match your specific workflow preferences

### The Solution
**Craft skills from your own sessions**:
1. **Pattern Detection**: Analyze your session history for successful patterns
2. **Interactive Review**: Select which patterns to formalize
3. **Skill Generation**: Create personalized SKILL.md files
4. **Auto-Registration**: Skills become immediately usable

---

## Commands

### `/skill-craft` - Main Entry Point

Launches the skill crafting workflow.

**Usage**:
- `/skill-craft` - Start interactive crafting session
- `/skill-craft --recent 5` - Analyze last 5 sessions
- `/skill-craft --tag debugging` - Focus on specific domain
- `/skill-craft --auto` - Auto-generate without prompts (advanced)

**Workflow**:
```
┌─────────────────────────────────────────────────────────┐
│  Skill Crafting Session                                 │
├─────────────────────────────────────────────────────────┤
│  Step 1: Scanning session history...                    │
│  Step 2: Identifying patterns...                        │
│  Step 3: Clustering similar patterns...                 │
│  Step 4: Ranking by value...                            │
│                                                         │
│  Found 4 pattern clusters ready for crafting:           │
│                                                         │
│  1. 🔧 Error Recovery Pattern                          │
│     Occurrences: 8 sessions | Success: 87%             │
│     Preview: When encountering [error type], run       │
│              [command] → analyze output → fix          │
│                                                         │
│  2. 📋 Pre-commit Checklist                            │
│     Occurrences: 12 sessions | Success: 100%           │
│     Preview: lint → test → typecheck → commit          │
│                                                         │
│  3. 🔍 Debug Investigation                             │
│     Occurrences: 6 sessions | Success: 83%             │
│     Preview: logs → grep errors → locate → fix         │
│                                                         │
│  4. 🚀 Feature Implementation                          │
│     Occurrences: 5 sessions | Success: 80%             │
│     Preview: plan → tests → implement → verify         │
│                                                         │
│  Select patterns to craft [1-4, comma-separated, a=all]│
└─────────────────────────────────────────────────────────┘
```

---

### `/craft-review` - Review Generated Skills

Review and edit generated skills before finalizing.

**Usage**:
- `/craft-review` - Review pending skills
- `/craft-review [skill-name]` - Review specific skill
- `/craft-review --apply` - Apply all pending skills

**Output**:
```
Pending Skills for Review:

1. error-recovery-workflow (new)
   Source: 8 sessions
   Confidence: 0.87
   
   ┌─────────────────────────────────────────┐
   │ # Error Recovery Workflow               │
   │                                         │
   │ ## When to Use                          │
   │ Encountering runtime errors in [context]│
   │                                         │
   │ ## Steps                                │
   │ 1. Run [diagnostic command]             │
   │ 2. Analyze error output                 │
   │ 3. Apply fix based on pattern           │
   │ 4. Verify with test                     │
   └─────────────────────────────────────────┘
   
   Actions: [e]dit [a]pprove [d]iscard [s]kip
```

---

### `/craft-generate` - Direct Skill Generation

Generate a skill from a specific pattern description.

**Usage**:
- `/craft-generate "When fixing TypeScript errors, check types first"`
- `/craft-generate --from-instinct <instinct-id>`

---

## Trigger Mechanisms

### 1. Project Completion Trigger

**Condition**: Git merge/push to main branch detected

**Behavior**:
```
┌─────────────────────────────────────────────────────────┐
│  Project Milestone Detected                              │
├─────────────────────────────────────────────────────────┤
│  You just completed: Feature X                           │
│  Sessions in this feature: 5                             │
│                                                          │
│  Would you like to review and extract skills?            │
│  [y] Yes, start skill crafting                           │
│  [n] No, maybe later                                     │
│  [r] Remind me in 1 hour                                 │
└─────────────────────────────────────────────────────────┘
```

### 2. Accumulation Trigger

**Condition**: N sessions completed (configurable, default 10)

**Behavior**: Gentle prompt at session end
```
Session count: 10 | Consider crafting skills? /skill-craft
```

### 3. Periodic Trigger

**Condition**: Weekly/monthly review time

**Behavior**: Proactive suggestion
```
Weekly Review: 23 sessions this week, 4 pattern candidates found.
Run /skill-craft to review.
```

### 4. Manual Trigger

**Condition**: User invokes `/skill-craft`

**Behavior**: Immediate interactive session

---

## Pattern Detection Algorithm

### Input Sources

1. **Session Logs**: `~/.claude/memory/session.md`
2. **Project Knowledge**: `memory/project-knowledge.md`
3. **Instincts Database**: `memory/instincts.yaml`
4. **Git History**: Recent commits and their messages

### Detection Process

```
┌──────────────────────────────────────────────────────┐
│  Pattern Detection Pipeline                           │
├──────────────────────────────────────────────────────┤
│                                                       │
│  1. SCAN                                              │
│     ├─ Read session history (last N sessions)        │
│     ├─ Extract tool call sequences                   │
│     └─ Note success/failure outcomes                 │
│                                                       │
│  2. IDENTIFY                                          │
│     ├─ Find repeating sequences (≥3 occurrences)     │
│     ├─ Calculate success rate per pattern            │
│     └─ Extract context tags                          │
│                                                       │
│  3. CLUSTER                                           │
│     ├─ Group similar patterns                        │
│     ├─ Merge overlapping sequences                   │
│     └─ Assign cluster representative                 │
│                                                       │
│  4. RANK                                              │
│     ├─ Score by: frequency × success_rate × value    │
│     ├─ Filter by minimum threshold                   │
│     └─ Present top candidates                        │
│                                                       │
└──────────────────────────────────────────────────────┘
```

### Scoring Formula

```python
pattern_score = (
    frequency_score * 0.3 +      # How often this pattern occurs
    success_rate * 0.4 +          # How reliable it is
    complexity_score * 0.2 +      # Non-trivial patterns preferred
    cross_project_score * 0.1     # Reusable across projects
)

frequency_score = min(occurrences / 10, 1.0)
success_rate = successful_occurrences / total_occurrences
complexity_score = min(steps_count / 5, 1.0)
cross_project_score = unique_projects / max(1, total_projects)
```

---

## Skill Generation Template

### Generated Skill Structure

```markdown
---
name: [skill-name]
description: [Auto-generated description]
version: 1.0.0
generated: true
source:
  sessions: [session-ids]
  pattern_score: [score]
  created_at: [timestamp]
---

# [Skill Name]

> **Generated from your successful workflows**
> Confidence: [score] | Occurrences: [N] | Success Rate: [%]

## When to Use

[Context description extracted from sessions]

## Steps

1. [Step 1 from pattern]
   - Command: `[actual command if applicable]`
   - Expected: [what to look for]

2. [Step 2 from pattern]
   ...

## Examples

### Example 1: [Scenario]
```
[Actual session excerpt showing the pattern in action]
```

## Customization

This skill was auto-generated. Edit to:
- Add more context
- Refine steps
- Add edge cases

---
*Generated by skill-craft on [date]*
```

---

## Configuration

### User Preferences

Located in `~/.claude/config/skill-craft.yaml`:

```yaml
skill-craft:
  triggers:
    project_completion: true
    accumulation_threshold: 10
    periodic_review: weekly
  
  detection:
    min_occurrences: 3
    min_success_rate: 0.7
    scan_recent_sessions: 20
  
  generation:
    auto_register: false      # Require manual approval
    skill_directory: personal # Where to save new skills
    
  notifications:
    quiet_hours: [22:00, 08:00]
    max_prompts_per_day: 2
```

---

## Integration with Existing Skills

### With `instinct-learning`

```
instinct-learning          skill-craft
     │                         │
     │  Low-level patterns     │
     ├────────────────────────►│
     │                         │
     │                         │ Aggregates instincts
     │                         │ into higher-level skills
     │                         │
     │  Generated skill        │
     │◄────────────────────────┤
     │  (marks instincts as    │
     │   "evolved")            │
```

### With `session-end`

Session-end skill will check trigger conditions and suggest `/skill-craft` when appropriate.

---

## Safety & Privacy

### What Gets Analyzed
- Tool call sequences (anonymized)
- Success/failure outcomes
- File types touched
- Command patterns

### What's NEVER Analyzed
- File contents (unless user explicitly shares)
- Credentials, tokens, secrets
- Private user data
- Cross-user information

### Data Storage
- All analysis runs locally
- Generated skills stored in `~/.claude/skills/personal/`
- No cloud sync unless explicitly configured

---

## Best Practices

### When to Craft Skills
- After completing a complex feature
- When you notice yourself repeating a workflow
- At the end of a productive week
- Before starting similar work on a new project

### What Makes a Good Skill
- **Reusable**: Applies to multiple scenarios
- **Specific**: Clear when to use it
- **Actionable**: Concrete steps, not vague advice
- **Tested**: Proven success in real sessions

### When NOT to Craft
- One-time fixes
- Project-specific temporary workarounds
- Patterns with low success rates
- Things already covered by existing skills

---

## Examples

### Example 1: Crafting a Debug Workflow

```
User: /skill-craft

Analyzing last 15 sessions...

Found pattern: "API Error Debug Workflow"
  Occurrences: 7 sessions
  Success rate: 85%
  
  Pattern detected:
    1. Check error response status
    2. Grep logs for error code
    3. Check API documentation
    4. Implement fix
    5. Add retry logic

Craft skill from this pattern? [y/n/e]
> y

Generating skill...
Created: ~/.claude/skills/personal/api-error-debug/SKILL.md

Skill registered! Use /api-error-debug to invoke.
```

### Example 2: Project Completion Review

```
[After git push to main]

┌─────────────────────────────────────────────────────────┐
│  Feature Complete: User Authentication                   │
├─────────────────────────────────────────────────────────┤
│  8 sessions | 47 commands | 12 files changed            │
│                                                          │
│  Patterns detected:                                      │
│  • Auth flow implementation (new)                        │
│  • Token refresh handling (new)                          │
│  • Session management (similar to existing)              │
│                                                          │
│  Review and extract skills? [y/n/later]                  │
└─────────────────────────────────────────────────────────┘
```

---

## Future Enhancements

- **Team Sharing**: Export/import personal skills
- **Skill Marketplace**: Community skill repository
- **Auto-Suggestion**: Proactively suggest skills during work
- **Skill Evolution**: Skills that improve over time

---

**Version**: 1.0.0
**Status**: Ready for Implementation
**Dependencies**: instinct-learning, session-end
