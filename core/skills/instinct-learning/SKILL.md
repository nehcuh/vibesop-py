---
id: builtin/instinct-learning
name: instinct-learning
description: Automatic pattern learning system - extract reusable instincts from sessions
tags: [instinct, pattern, learn, extract, habit, 本能, 模式, 学习]
version: 1.0.0
commands:
  - learn
  - learn-eval
  - instinct-status
  - instinct-export
  - instinct-import
  - evolve
intent: learning
namespace: builtin
version: 1.0.0
type: prompt
---

# Instinct Learning System

> **Automatic pattern extraction from your work sessions**
> Learn from your successful workflows and build a personal knowledge base.

## What This Skill Does

### The Problem
- You solve the same problem multiple times but forget the solution
- Successful workflows are not captured and reused
- Team knowledge is scattered and not shared
- Manual documentation is tedious and often skipped

### The Solution
**Automatically learn** from your sessions:
1. **Pattern Detection**: Analyze successful tool call sequences
2. **Confidence Scoring**: Evaluate pattern reliability
3. **Knowledge Sharing**: Export/import instincts across team
4. **Skill Evolution**: Upgrade high-quality instincts to formal skills

## Commands

### `/learn` - Extract Patterns from Current Session

Analyzes the current session and extracts successful patterns as instinct candidates.

**Usage**: `/learn`

**What it does**:
- Analyzes tool call history
- Identifies successful sequences (3+ consecutive successes)
- Generates natural language pattern descriptions
- Creates instinct candidates for review

**Example output**:
```
Found 3 pattern candidates:

1. Ruby Syntax Fix Pattern
   Sequence: rubocop → Edit → ruby test
   Success rate: 100% (5/5 times)
   Suggested pattern: "When fixing Ruby syntax errors, run rubocop first"
   Tags: ruby, linting, debugging

2. Git Workflow Pattern
   Sequence: git status → git add → git commit
   Success rate: 100% (8/8 times)
   Suggested pattern: "Always check git status before committing"
   Tags: git, workflow

Use /learn-eval to review and save these patterns.
```

---

### `/learn-eval` - Evaluate and Save Instinct Candidates

Reviews instinct candidates and saves approved ones to the knowledge base.

**Usage**: `/learn-eval [instinct_id]`

**What it does**:
- Calculates confidence score
- Shows usage statistics
- Asks for user confirmation
- Saves to memory/instincts.yaml

**Example**:
```
Evaluating Instinct Candidate #1

Pattern: "When fixing Ruby syntax errors, run rubocop first"
Confidence: 0.85 (High)
  - Success rate: 100% (5/5) → 0.60
  - Usage frequency: 5/20 → 0.15
  - Source diversity: 2 sessions → 0.10

Tags: ruby, linting, debugging
Context: Ruby projects with rubocop configured

Save this instinct? [y/n/e]
y - Yes, save to knowledge base
n - No, discard
e - Edit before saving
```

---

### `/instinct-status` - View All Instincts

Lists all learned instincts with their confidence scores.

**Usage**:
- `/instinct-status` - List all active instincts
- `/instinct-status --tag ruby` - Filter by tag
- `/instinct-status --min-confidence 0.8` - Filter by confidence
- `/instinct-status --all` - Include archived and evolved

**Example output**:
```
Active Instincts (12 total)

High Confidence (≥ 0.8):
  1. Ruby syntax fix workflow (0.92) [ruby, linting]
  2. Git commit workflow (0.88) [git, workflow]
  3. Test-driven debugging (0.85) [testing, debugging]

Medium Confidence (0.6-0.8):
  4. API error handling (0.75) [api, error-handling]
  5. Database migration pattern (0.68) [database, rails]

Low Confidence (< 0.6):
  6. Performance optimization (0.55) [performance]
```

---

### `/instinct-export` - Export Instincts

Exports instincts to a file for backup or team sharing.

**Usage**:
- `/instinct-export backup.yaml` - Export all
- `/instinct-export ruby-patterns.yaml --tag ruby` - Export by tag
- `/instinct-export high-confidence.yaml --min-confidence 0.8` - Export high-confidence only

**Example**:
```
Exported 8 instincts to ruby-patterns.yaml
  - 5 high confidence
  - 3 medium confidence
  - Tags: ruby, rails, testing

Share this file with your team!
```

---

### `/instinct-import` - Import Instincts

Imports instincts from a file (team sharing or backup restore).

**Usage**:
- `/instinct-import team-patterns.yaml` - Import with skip strategy (default)
- `/instinct-import backup.yaml --overwrite` - Overwrite existing
- `/instinct-import shared.yaml --merge` - Merge usage statistics

**Merge strategies**:
- `skip`: Skip existing instincts (safe, default)
- `overwrite`: Replace existing instincts
- `merge`: Combine usage statistics

**Example**:
```
Importing from team-patterns.yaml...

Results:
  ✓ Imported: 12 new instincts
  ⊘ Skipped: 3 duplicates
  ⚠ Errors: 0

New instincts added:
  - React hooks best practices (0.90)
  - TypeScript type narrowing (0.85)
  - Jest testing patterns (0.82)
```

---

### `/evolve` - Upgrade Instinct to Skill

Converts high-quality instincts into formal skills.

**Usage**: `/evolve <instinct_id> [skill_name]`

**What it does**:
- Aggregates related instincts
- Generates skill markdown file
- Saves to skills/ directory
- Marks instinct as "evolved"

**Example**:
```
Evolving instinct #1 into skill...

Creating skill: ruby-linting-workflow
  - Based on 3 related instincts
  - Combined confidence: 0.88
  - Total usage: 45 times across 8 sessions

Generated files:
  ✓ skills/ruby-linting-workflow/SKILL.md
  ✓ Updated memory/instincts.yaml (marked as evolved)

You can now use: /ruby-linting-workflow
```

---

## How It Works

### 1. Pattern Detection
```
Session Activity:
  Bash: rubocop app.rb → Success
  Edit: app.rb (fix syntax) → Success
  Bash: ruby app.rb → Success

Pattern Detected:
  "Run linter before testing Ruby code"
  Confidence: 0.75 (initial)
```

### 2. Confidence Evolution
```
First use:  0.75 (1 success, 1 session)
After 5:    0.82 (5 successes, 2 sessions)
After 20:   0.90 (19 successes, 5 sessions)
```

### 3. Knowledge Sharing
```
Developer A: Learns pattern → Exports
Developer B: Imports → Applies pattern
Developer C: Imports → Pattern confidence increases
```

---

## Storage

**Location**: `memory/instincts.yaml`

**Format**:
```yaml
version: "1.0"
instincts:
  - id: "550e8400-e29b-41d4-a716-446655440000"
    pattern: "Run rubocop before testing Ruby code"
    confidence: 0.85
    source_sessions: ["session-001", "session-002"]
    usage_count: 12
    success_rate: 0.92
    tags: ["ruby", "linting"]
    status: "active"
```

---

## Best Practices

### When to Use `/learn`
- ✅ After solving a complex problem
- ✅ After establishing a new workflow
- ✅ At the end of a productive session
- ❌ During active debugging (wait until solved)

### Confidence Thresholds
- **0.9+**: Highly reliable, auto-apply
- **0.7-0.9**: Reliable, suggest to user
- **0.5-0.7**: Experimental, use with caution
- **< 0.5**: Low confidence, needs more data

### Team Sharing
1. Export high-confidence instincts (≥ 0.8)
2. Share via Git or team drive
3. Team members import with `--merge` strategy
4. Collective usage increases confidence

---

## Safety

**What this skill does NOT do**:
- ❌ Auto-apply patterns without confirmation
- ❌ Modify your code automatically
- ❌ Share data outside your control
- ❌ Execute commands without permission

**What it DOES**:
- ✅ Learn from your explicit actions
- ✅ Store data locally (memory/instincts.yaml)
- ✅ Require confirmation before saving
- ✅ Support team sharing via explicit export/import

---

## Upgrade Path

**Phase 1 (Current)**: Manual learning with `/learn` and `/learn-eval`
**Phase 2**: Auto-detection with user confirmation
**Phase 3**: High-confidence patterns auto-suggest
**Phase 4**: Cross-project pattern recognition

---

**Version**: 1.0.0
**Status**: Active Development
**Feedback**: Report issues to VibeSOP repository
