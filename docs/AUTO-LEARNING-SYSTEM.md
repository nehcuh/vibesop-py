# VibeSOP-Py Auto-Learning & Creation System

> **Complete Guide**
> **Version**: 2.1.0+
> **Status**: ✅ Fully Implemented

## 🎯 Overview

VibeSOP-Py features a **complete automatic learning and skill creation system** that learns from your usage patterns and automatically suggests and creates new skills.

## 🔄 Complete Learning Loop

```
┌─────────────────────────────────────────────────────────┐
│                     User Uses VibeSOP                    │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│              Step 1: Auto-Record Selections              │
│  • SkillManager.execute_skill() auto-records           │
│  • route-select --auto auto-records                    │
│  • Interactive choice auto-records                      │
│  • Saves to .vibe/preferences.json                        │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│              Step 2: Preference Learning                  │
│  • PreferenceLearner calculates scores                   │
│  • Higher frequency → higher preference                  │
│  • Boosts routing confidence (up to +20%)                │
│  • Improves routing accuracy over time                   │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│              Step 3: Session-End Analysis                 │
│  • pre-session-end hook triggers                        │
│  • vibe auto-analyze-session --quiet                     │
│  • Detects repeated patterns                             │
│  • Character-based similarity (supports CJK)              │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│              Step 4: AI-Enhanced Suggestions             │
│  • Optional: vibe analyze suggestions --ai               │
│  • LLM generates professional skill names                │
│  • Improves descriptions                                 │
│  • Categorizes and tags                                  │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│              Step 5: One-Click Creation                  │
│  • vibe create-suggested-skills session.jsonl            │
│  • Auto-generates .vibe/skills/*.md                     │
│  • vibe build to integrate                               │
│  • Next time: auto-routes to new skill                    │
└─────────────────────────────────────────────────────────┘
                        ↓
           Back to Step 1 - Continuous Improvement! ♻️
```

## 📚 Feature Breakdown

### Phase 1: Auto-Recording ✅
**Commit**: `f1e4915`

**What It Does**:
- Records every successful skill execution
- Tracks user selections in routing
- Saves to `.vibe/preferences.json`

**How To Use**:
```bash
# Just use skills normally - recording is automatic!
vibe route-select "review code" --auto
# → Auto-recorded ✅

# Skills are tracked automatically
# No manual vibe record needed!
```

**Storage**:
```json
.vibe/preferences.json
{
  "selections": [
    {
      "skill_id": "gstack/review",
      "query": "review my code",
      "timestamp": "2026-04-04T10:30:00",
      "was_helpful": true
    }
  ]
}
```

**Benefits**:
- ✅ Zero configuration
- ✅ Transparent to user
- ✅ Never breaks skill execution
- ✅ Continuous learning

### Phase 2: Pattern Detection ✅
**Commit**: `d18d4fe`

**What It Does**:
- Analyzes session history
- Detects repeated query patterns
- Clusters similar requests
- Identifies skill creation opportunities

**Algorithm**:
```python
# Character-based similarity (supports Chinese!)
similarity = intersection(set1, set2) / union(set1, set2)

# Clustering threshold: 35%
# Min frequency: 3 occurrences
# Min confidence: 30%
```

**How To Use**:
```bash
# Analyze a session
vibe analyze session session.jsonl

# Detect patterns
vibe analyze patterns .claude/projects/
```

### Phase 3: Auto-Suggestions ✅
**Commit**: `d18d4fe`

**What It Does**:
- Generates skill suggestions from patterns
- Estimates value (high/medium/low)
- Ranks by frequency and confidence

**Value Estimation**:
```python
if frequency >= 5 and confidence >= 0.7:
    value = "high"
elif frequency >= 3 and confidence >= 0.4:
    value = "medium"
else:
    value = "low"
```

**How To Use**:
```bash
# View suggestions
vibe analyze suggestions session.jsonl

# Auto-create
vibe analyze suggestions session.jsonl --auto-craft
```

### Phase 4: Session-End Integration ✅
**Commit**: `b091dd0`

**What It Does**:
- Hooks into session-end automatically
- Runs non-intrusive analysis
- Displays opportunities

**Hook Template**:
```bash
~/.claude/hooks/pre-session-end.sh

# When session ends:
vibe auto-analyze-session "$session_file" --quiet
# → Shows: [VibeSOP] Found 2 skill creation opportunities
```

**Output**:
```
[pre-session-end] Session ending at 2026-04-04
[pre-session-end] Analyzing session patterns...
[VibeSOP] Found 2 skill creation opportunities
```

### Phase 5: AI Enhancement ✅
**Commit**: `e0797c4`

**What It Does**:
- Uses LLM to improve skill quality
- Generates professional names
- Creates clear descriptions
- Categorizes and tags

**Before AI**:
```markdown
# 请帮我优化这段代码的性能

Automatically generated skill from 3 similar queries
```

**After AI**:
```markdown
# Code Performance Optimization

Optimize code execution efficiency and performance characteristics.

## Category
optimization

## Tags
Optimization, Performance, Code, Efficiency

## Trigger Conditions
- User asks about code performance
- User requests optimization help
- User mentions slow execution

## Steps
1. Profile the code to identify bottlenecks
2. Analyze performance characteristics
3. Implement optimization strategies
```

**How To Use**:
```bash
# Use AI enhancement
vibe analyze suggestions --ai

# Auto-create AI-enhanced skills
vibe analyze suggestions --ai --auto-craft
```

## 🚀 Quick Start

### 1. Normal Usage (Auto-Recording)

```bash
# Just use VibeSOP normally
$ vibe route-select "review my code" --auto
✓ Auto-selected: gstack/review
# → Automatically recorded to preferences! ✅

# Over time, routing improves based on your choices
```

### 2. Session-End Analysis

```bash
# When you end your session, it auto-analyzes
$ # Session ends...
[pre-session-end] Session ending
[VibeSOP] Found 2 skill creation opportunities

# Check what was detected
$ vibe analyze suggestions
💡 Found 2 opportunities

1. Code Optimization (4 queries, 45% confidence)
2. Security Scanning (3 queries, 38% confidence)
```

### 3. AI-Enhanced Creation

```bash
# Use AI to improve quality
$ vibe analyze suggestions --ai --auto-craft
🤖 Using AI to enhance suggestions...
✓ AI enhancement complete

Creating skill: Code Performance Optimization
✓ Created: .vibe/skills/code-performance-optimization.md
✓ Created 1 AI-enhanced skills

# Next time, VibeSOP auto-routes to this new skill!
```

## 📊 Data Flow

```
User Action
    ↓
Auto-Record (Step 1)
    ↓
preferences.json (47+ selections)
    ↓
PreferenceLearner
    ↓
Boosted Confidence (+20% max)
    ↓
Better Routing
    ↓
More Correct Usage
    ↓
More Learning Data
    ↓
Continuous Improvement ♻️
```

## 🎯 Key Benefits

### 1. Zero Configuration
- ✅ Works out of the box
- ✅ No manual setup needed
- ✅ Transparent operation

### 2. Continuous Learning
- ✅ Improves over time
- ✅ Adapts to your workflow
- ✅ Personalized routing

### 3. Smart Suggestions
- ✅ Detects real patterns
- ✅ Filters high-value opportunities
- ✅ AI-enhanced quality

### 4. Multi-Language Support
- ✅ Works with English
- ✅ Works with Chinese
- ✅ Works with mixed content

## 📁 Storage & Files

```
.vibe/
├── preferences.json          # Auto-recorded selections
├── instincts/
│   └── decisions.json       # Decision patterns
└── skills/                   # Auto-generated skills
    ├── code-review.md
    └── performance-optimization.md

.claude/
├── hooks/
│   └── pre-session-end.sh   # Auto-analysis trigger
└── memory/
    ├── project-knowledge.md # Lessons learned
    └── session.md            # Active tasks
```

## 🛠️ Commands Reference

### Analysis Commands

```bash
# Analyze session
vibe analyze session <file>

# Analyze patterns
vibe analyze patterns <dir>

# Generate suggestions
vibe analyze suggestions [source]

# AI-enhanced suggestions
vibe analyze suggestions --ai

# Auto-create skills
vibe analyze suggestions --auto-craft

# AI-enhanced + auto-create
vibe analyze suggestions --ai --auto-craft
```

### Auto-Analysis Commands

```bash
# Non-interactive (for hooks)
vibe auto-analyze-session <file> --quiet

# Create skills
vibe create-suggested-skills <file>
```

### Preference Commands

```bash
# View stats
vibe preferences

# Prune old data
vibe preferences --prune --days 30

# Manual recording (rarely needed)
vibe record /review "query"
```

## 📖 Examples

### Example 1: Development Workflow

```bash
# 1. You repeatedly ask to optimize code
$ vibe route-select "优化这段代码"
$ vibe route-select "帮我优化性能"
$ vibe route-select "请帮我优化一下"

# 2. Session ends
[pre-session-end] [VibeSOP] Found 1 skill creation opportunity

# 3. Check suggestions
$ vibe analyze suggestions --ai
🤖 Using AI to enhance...
✓ AI enhancement complete

1. Code Performance Optimization
   Category: optimization
   Tags: Optimization, Performance, Code
   Frequency: 3 queries
   Confidence: 45%

# 4. Create skill
$ vibe analyze suggestions --ai --auto-craft
✓ Created: .vibe/skills/code-performance-optimization.md

# 5. Build and use
$ vibe build
✓ Build complete

# 6. Next time, auto-routes!
$ vibe route-select "请优化性能"
✓ Auto-selected: code-performance-optimization
```

### Example 2: Mixed Language

```bash
# Mixed English and Chinese queries
"请帮我review代码"
"help me review"
"检查代码质量"

# All detected as same pattern
# AI generates skill: "Code Review"
# Works for both languages!
```

## 🔧 Configuration

### Thresholds

```bash
# Adjust sensitivity
vibe analyze session --min-frequency 2 --min-confidence 0.3
```

### Disable Features

**Disable auto-recording**:
```python
# Comment out in SkillManager._auto_record_selection()
```

**Disable session-end analysis**:
```bash
# Edit ~/.claude/hooks/pre-session-end.sh
# Comment out: analyze_session
```

## 📈 Performance Impact

| Operation | Time | Impact |
|-----------|------|--------|
| Auto-record | < 1ms | ✅ Negligible |
| Pattern detection | < 1s | ✅ Low |
| AI enhancement | ~5-10s | ✅ Optional |
| Skill creation | < 1s | ✅ Low |

**Total overhead**: Negligible for auto-features, ~5-10s for AI enhancement (optional)

## 🎓 Best Practices

### 1. Let It Learn
- ✅ Use VibeSOP normally
- ✅ Don't worry about recording
- ✅ Trust the system

### 2. Review Occasionally
```bash
# Check what's been learned
vibe preferences

# See top skills
vibe preferences --top 10
```

### 3. Use AI for Quality
```bash
# Basic suggestions (fast)
vibe analyze suggestions

# AI-enhanced (better quality)
vibe analyze suggestions --ai
```

### 4. Clean Up Periodically
```bash
# Remove old data
vibe preferences --prune --days 30
```

## 🆚 Comparison: Before vs After

### Before (Manual)

```bash
# After every session
vibe record /review "review code"
vibe record /debug "fix bug"
vibe record /test "test code"

# To find patterns
Manually review session history
Manually identify repetitions
Manually create skills

# Result: Most people don't do it ❌
```

### After (Automatic)

```bash
# Just use VibeSOP normally
vibe route-select "review code" --auto

# Session ends
→ Auto-analyzes ✅
→ Auto-suggests ✅
→ Auto-creates (optional) ✅

# Result: Continuous improvement with zero effort! ✅
```

## 🏆 Summary

VibeSOP-Py now has **industry-leading automatic learning and creation**:

| Feature | Status | Benefit |
|---------|--------|---------|
| **Auto-Recording** | ✅ Complete | Zero-effort tracking |
| **Pattern Detection** | ✅ Complete | Multilingual support |
| **Auto-Suggestions** | ✅ Complete | Smart value estimation |
| **Session-End Integration** | ✅ Complete | Non-intrusive |
| **AI Enhancement** | ✅ Complete | Professional quality |

**Result**: A self-improving workflow automation system that gets better the more you use it! 🚀

---

**Version**: 2.1.0+
**Status**: Production Ready
**Last Updated**: 2026-04-04
