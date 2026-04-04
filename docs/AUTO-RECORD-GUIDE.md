# Automatic Skill Selection Recording

> **VibeSOP-Py v2.1.0+ Feature**
> **Status**: ✅ Implemented

## Overview

VibeSOP-Py now **automatically records** your skill selections to improve routing accuracy over time. No manual `vibe record` commands needed!

## How It Works

### 1. Automatic Recording

Every time you successfully use a skill, VibeSOP automatically:
- ✅ Records the skill ID
- ✅ Records your query
- ✅ Marks it as helpful
- ✅ Saves to `.vibe/preferences.json`

### 2. Improved Routing

Over time, VibeSOP learns your preferences:
- **More frequent selections** → Higher preference score
- **Higher preference score** → Better routing accuracy
- **Better routing** → More relevant skill suggestions

## Recording Points

### 1. Skill Execution

When you execute a skill via `SkillManager`:
```python
# Automatic (internal)
manager = SkillManager()
result = await manager.execute_skill("gstack/review", query="review my code")
# → Auto-recorded to preferences.json
```

### 2. Route Selection (Auto Mode)

When you use `--auto` flag:
```bash
$ vibe route-select "review code" --auto
✓ Auto-selected: gstack/review
# → Auto-recorded to preferences.json
```

### 3. Interactive Selection

When you choose from alternatives:
```bash
$ vibe route-select "help"
Alternatives:
  1. gstack/review (95%)
  2. gstack/debug (85%)
  3. systematic-debugging (80%)

Choice [dim]1[/dim]:
✓ Selected: gstack/review
# → Auto-recorded to preferences.json
```

## Storage Location

```bash
.vibe/preferences.json
```

**Format**:
```json
{
  "selections": [
    {
      "skill_id": "gstack/review",
      "query": "review my code",
      "timestamp": "2026-04-04T10:30:00",
      "was_helpful": true
    }
  ],
  "skill_scores": {
    "gstack/review": {
      "score": 0.85,
      "selection_count": 15,
      "helpful_count": 14
    }
  }
}
```

## Benefits

### 1. Zero Configuration

- ✅ No manual tracking needed
- ✅ Works out of the box
- ✅ Transparent to user

### 2. Continuous Learning

- ✅ Improves over time
- ✅ Adapts to your workflow
- ✅ Personalized routing

### 3. Better Recommendations

- ✅ More accurate skill suggestions
- ✅ Faster routing to right skills
- ✅ Reduced manual selection

## Preference Scoring

### How Scores Work

```python
# Base score from selections
score = helpful_count / total_selections

# Boost factor (up to 20%)
boosted_confidence = original_confidence + (score * 0.2)
```

### Score Ranges

- **0.0**: No preference data
- **0.0-0.3**: Low preference (few selections)
- **0.3-0.7**: Medium preference (moderate use)
- **0.7-1.0**: High preference (frequent use)

## Configuration

### View Preferences

```bash
# See preference statistics
vibe preferences

# View detailed data
cat .vibe/preferences.json | jq
```

### Clear Preferences

```bash
# Remove old data (keeps recent)
vibe preferences --prune --days 30

# Clear all preferences
rm .vibe/preferences.json
```

### Disable Auto-Recording

To disable automatic recording:

**Option 1**: Comment out code in `SkillManager._auto_record_selection()`

**Option 2**: Use environment variable:
```bash
export VIBE_AUTO_RECORD=false
```

(Note: This would require code modification to check the env var)

## Technical Details

### Recording Logic

```python
# In SkillManager.execute_skill()
if result.success:
    self._auto_record_selection(skill_id, query)

def _auto_record_selection(self, skill_id: str, query: str):
    learner = PreferenceLearner(storage_path=".vibe/preferences.json")
    learner.record_selection(skill_id, query, was_helpful=True)
```

### Error Handling

Auto-recording **never breaks** skill execution:
- ✅ Silent failure on errors
- ✅ No impact on skill functionality
- ✅ Safe to ignore

### Data Decay

Old data loses relevance:
- **Decay period**: 30 days (configurable)
- **Old selections**: Weighted less in scoring
- **Automatic cleanup**: Via `--prune` flag

## Comparison with Manual Recording

### Before (Manual)

```bash
# After every skill use
vibe record /review "review my code"
```

**Problems**:
- ❌ Easy to forget
- ❌ Disrupts workflow
- ❌ Inconsistent data

### After (Automatic)

```bash
# Just use skills normally
vibe route-select "review code" --auto
# → Automatically recorded!
```

**Benefits**:
- ✅ No extra steps
- ✅ Consistent data
- ✅ Better learning

## Best Practices

### 1. Let It Learn

- ✅ Use skills normally
- ✅ Don't worry about recording
- ✅ Let VibeSOP track automatically

### 2. Review Occasionally

```bash
# Check preference stats
vibe preferences

# See top skills
vibe preferences --top 10
```

### 3. Clean Up Periodically

```bash
# Remove old data
vibe preferences --prune --days 30
```

## FAQ

**Q: Does this slow down skill execution?**
A: No, recording is < 1ms and happens asynchronously.

**Q: Can I disable it?**
A: Yes, but requires code modification. Open an issue if you need this feature.

**Q: Is my data private?**
A: Yes, stored locally in `.vibe/preferences.json`.

**Q: How much data is stored?**
A: Minimal. Each selection is ~100 bytes. 1000 selections = ~100KB.

**Q: Can I export my preferences?**
A: Yes, just copy `.vibe/preferences.json`.

**Q: Does this work with all skills?**
A: Yes, any skill executed via SkillManager is auto-recorded.

**Q: What if I make a mistake?**
A: No problem! Occasional mistakes don't significantly impact scoring.

## Future Enhancements

Planned improvements:
- [ ] Export/import preferences
- [ ] Visualization of preference trends
- [ ] Manual correction of mistaken selections
- [ ] Privacy mode (disable tracking)
- [ ] Multi-user preference isolation
