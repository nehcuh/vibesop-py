# Automatic Learning and Skill Creation Guide

> **VibeSOP-Py v2.1.0+ Feature**
> **Status**: ✅ Implemented

## Overview

VibeSOP-Py now automatically learns from your session history and suggests new skills to create. This helps you:
- ✅ Detect repeated patterns in your work
- ✅ Automatically identify skill creation opportunities
- ✅ Create reusable skills from common workflows
- ✅ Improve productivity over time

## How It Works

### 1. Session Analysis

When a session ends, VibeSOP automatically:
1. Scans the session history
2. Detects repeated query patterns
3. Clusters similar requests
4. Estimates value of creating a skill

### 2. Pattern Detection

Uses character-based similarity analysis:
- **Works with Chinese and English**
- **Detects semantic similarity**
- **Adjusts confidence scores**
- **Estimates skill value**

### 3. Automatic Suggestions

High-value patterns are suggested:
- **High value**: 5+ occurrences, 70%+ confidence
- **Medium value**: 3+ occurrences, 40%+ confidence
- **Low value**: Below thresholds

## Usage

### Manual Analysis

```bash
# Analyze a specific session
vibe analyze session session.jsonl

# Generate suggestions
vibe analyze suggestions session.jsonl

# Auto-create skills
vibe analyze suggestions session.jsonl --auto-craft
```

### Automatic Analysis (Hooks)

The pre-session-end hook automatically:
```bash
# Runs when session ends
~/.claude/hooks/pre-session-end.sh

# Output:
[VibeSOP] Found 2 skill creation opportunities
```

### Non-Interactive (Scripts)

```bash
# Analyze without interaction
vibe auto-analyze-session session.jsonl --quiet

# Create skills automatically
vibe create-suggested-skills session.jsonl
```

## Example Workflow

### 1. During Session

You repeatedly ask similar questions:
```
User: "请帮我优化这段代码的性能"
User: "请帮我优化这个函数的执行效率"
User: "请帮我优化代码让它更快"
```

### 2. Session Ends

Hook detects patterns:
```
[pre-session-end] Session ending at 2026-04-04
[pre-session-end] Analyzing session patterns...
[VibeSOP] Found 1 skill creation opportunity
```

### 3. Review Suggestions

```bash
$ vibe analyze session
💡 Session Analysis
Found 1 skill creation opportunities

1. 优化代码性能
   Frequency: 3 queries
   Confidence: 45%
   Value: medium

   Example: 请帮我优化这段代码的性能...
```

### 4. Create Skill

```bash
$ vibe create-suggested-skills session.jsonl
Creating skill: 请帮我优化这段代码的性能
✓ Created: .vibe/skills/优化代码性能.md
✓ Created 1 skills
```

### 5. Use New Skill

```bash
# Build configuration
vibe build

# Next time, VibeSOP automatically routes to this skill
```

## Configuration

### Thresholds

Adjust sensitivity:
```bash
# More aggressive (more suggestions)
vibe analyze session --min-frequency 2 --min-confidence 0.3

# More conservative (fewer suggestions)
vibe analyze session --min-frequency 5 --min-confidence 0.7
```

### Hook Behavior

Enable/disable automatic analysis:
```bash
# Edit hook to disable analysis
~/.claude/hooks/pre-session-end.sh

# Comment out the analysis call:
# analyze_session
```

## Technical Details

### Similarity Algorithm

```python
# Character-based similarity (works for CJK)
similarity = intersection(set1, set2) / union(set1, set2)

# Clustering threshold: 35% character overlap
# Min frequency: 3 occurrences
# Min confidence: 30-40%
```

### Value Estimation

```python
if frequency >= 5 and confidence >= 0.7:
    value = "high"
elif frequency >= 3 and confidence >= 0.4:
    value = "medium"
else:
    value = "low"
```

## Best Practices

### 1. Review Suggestions

Always review before creating:
```bash
# Check what will be created
vibe analyze suggestions session.jsonl

# Then create
vibe create-suggested-skills session.jsonl
```

### 2. Edit Generated Skills

Auto-generated skills are templates:
```bash
# Edit skill to add specific steps
vim .vibe/skills/优化代码性能.md

# Rebuild
vibe build
```

### 3. Use with Preference Learning

Combine with automatic preference learning:
- VibeSOP records your skill choices
- Improves routing accuracy over time
- Suggests skills based on actual patterns

## FAQ

**Q: Does this slow down session-end?**
A: No, analysis is fast (< 1 second for typical sessions)

**Q: Can I disable automatic analysis?**
A: Yes, edit `~/.claude/hooks/pre-session-end.sh` and comment out `analyze_session`

**Q: How accurate are the suggestions?**
A: Depends on pattern consistency. Higher frequency = better suggestions.

**Q: What if I don't want to create the skill?**
A: No problem! Suggestions are optional. Just ignore them.

**Q: Can I merge similar skills?**
A: Yes! Edit the generated skills and customize as needed.

## Related Commands

- `vibe analyze` - Interactive session analysis
- `vibe auto-analyze-session` - Non-interactive analysis
- `vibe create-suggested-skills` - Auto-create from patterns
- `vibe skill-craft` - Manual skill creation
- `vibe record` - Record skill selections for learning

## Future Enhancements

Planned improvements:
- [ ] AI-powered skill description generation
- [ ] Interactive suggestion confirmation
- [ ] Automatic skill merging
- [ ] Cross-session pattern learning
- [ ] Skill execution tracking
