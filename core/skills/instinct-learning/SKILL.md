---
id: builtin/instinct-learning
name: instinct-learning
description: Automatic pattern learning system - extract reusable instincts from sessions
tags: [instinct, pattern, learn, extract, habit, 本能, 模式, 学习]
version: 1.1.0
commands:
  - learn
  - learn-eval
  - instinct-status
  - instinct-export
  - instinct-import
  - evolve
intent: learning
namespace: builtin
type: prompt
---

# Instinct Learning System

> Extract reusable patterns from your work, build instincts, and evolve them into formal skills.

## Core Principle

**Memory > Intelligence.** Instead of reasoning from scratch every time, remember what worked and reuse it.

---

## `/learn` — Record a Pattern

Records a successful workflow pattern as an instinct candidate.

### Execution

```bash
python3 -c "
from pathlib import Path
from vibesop.core.instinct.learner import InstinctLearner

learner = InstinctLearner(Path.cwd() / '.vibe' / 'instincts.jsonl')
learner.learn(
    pattern='<DESCRIBE_THE_PATTERN_IN_ONE_SENTENCE>',
    action='<WHAT_ACTION_TO_TAKE>',
    context='<WHEN_THIS_APPLIES>',
    tags=['<comma_separated_tags>'],
)
instinct = list(learner._instincts.values())[-1]
print(f'Learned: {instinct.pattern} (confidence: {instinct.confidence:.0%})')
"
```

### When to Use

- After solving a complex problem successfully
- After establishing a new workflow that worked well
- At the end of a productive session

### Pattern Writing Guidelines

| Good Pattern | Bad Pattern |
|-------------|------------|
| "Before deploying, run `pytest --cov` and check coverage > 80%" | "Test before deploy" |
| "When fixing lint errors, run `ruff check --fix` before manual edits" | "Fix lint" |
| "For Django migrations, always run `makemigrations --dry-run` first" | "Migrations" |

### Auto-Record from Session

After a successful tool sequence (3+ consecutive successes), automatically record it:

```bash
python3 -c "
from pathlib import Path
from vibesop.core.instinct.learner import InstinctLearner

learner = InstinctLearner(Path.cwd() / '.vibe' / 'instincts.jsonl')

steps = ['<step1>', '<step2>', '<step3>']  # e.g. ['Bash:ruff check', 'Edit:fix.py', 'Bash:ruff check']
success = True  # Set based on whether the sequence succeeded

candidate = learner.record_sequence(steps, success)
if candidate:
    print(f'New pattern candidate: {\" → \".join(candidate.steps)}')
    print(f'  Occurrences: {candidate.total_count}, Success rate: {candidate.success_rate:.0%}')
else:
    print('No candidate yet (need 5+ occurrences with 80%+ success)')
"
```

---

## `/learn-eval` — Evaluate and Save Candidates

Reviews detected sequence patterns and saves approved ones.

### View Candidates

```bash
python3 -c "
from pathlib import Path
from vibesop.core.instinct.learner import InstinctLearner

learner = InstinctLearner(Path.cwd() / '.vibe' / 'instincts.jsonl')
candidates = learner.get_sequence_candidates()

if not candidates:
    print('No pattern candidates ready yet.')
else:
    for i, c in enumerate(candidates):
        print(f'{i+1}. {\" → \".join(c.steps)}')
        print(f'   Occurrences: {c.total_count} | Success: {c.success_rate:.0%} | Tags: {c.context_tags}')
        print()
"
```

### Approve and Convert to Skill Suggestion

For each candidate you want to keep:

```bash
python3 -c "
from pathlib import Path
from vibesop.core.instinct.learner import InstinctLearner
from vibesop.core.skills.suggestion_collector import SkillSuggestionCollector

learner = InstinctLearner(Path.cwd() / '.vibe' / 'instincts.jsonl')
collector = SkillSuggestionCollector()

# Get all candidates and convert the ones you approve
candidates = learner.get_sequence_candidates()
# Add the candidate at <INDEX> (0-based) as a skill suggestion
collector.add_from_pattern(candidates[<INDEX>])

pending = collector.get_pending()
print(f'Pending suggestions: {len(pending)}')
for s in pending:
    print(f'  {s.name}: {s.description}')
"
```

### Apply to Routing

Approved instincts automatically boost matching skills in the router via `OptimizationService.apply_instinct_boost()`. No manual step needed.

---

## `/instinct-status` — View All Instincts

### Show All Active Instincts

```bash
python3 -c "
from pathlib import Path
from vibesop.core.instinct.learner import InstinctLearner

learner = InstinctLearner(Path.cwd() / '.vibe' / 'instincts.jsonl')

instincts = learner.get_reliable_instincts()
if not instincts:
    print('No reliable instincts yet. Use /learn to build your knowledge base.')
else:
    print(f'Active Instincts ({len(instincts)} total)')
    print()
    high = [i for i in instincts if i.confidence >= 0.8]
    mid = [i for i in instincts if 0.6 <= i.confidence < 0.8]
    low = [i for i in instincts if i.confidence < 0.6]

    if high:
        print('High Confidence (>= 0.8):')
        for i in high:
            print(f'  {i.pattern}')
            print(f'    Action: {i.action}  |  Uses: {i.total_applications}  |  Tags: {i.tags}')
    if mid:
        print('Medium Confidence (0.6-0.8):')
        for i in mid:
            print(f'  {i.pattern}')
    if low:
        print('Low Confidence (<0.6):')
        for i in low:
            print(f'  {i.pattern}')
"
```

### Filter by Tag

Add `tag_filter = '<tag>'` before the `get_reliable_instincts()` call:

```bash
python3 -c "
from pathlib import Path
from vibesop.core.instinct.learner import InstinctLearner

learner = InstinctLearner(Path.cwd() / '.vibe' / 'instincts.jsonl')
tag = '<TAG>'
instincts = [i for i in learner.get_reliable_instincts() if tag.lower() in [t.lower() for t in i.tags]]
print(f'Instincts tagged \"{tag}\": {len(instincts)}')
for i in instincts:
    print(f'  {i.pattern} ({i.confidence:.0%})')
"
```

### Show Statistics

```bash
python3 -c "
from pathlib import Path
from vibesop.core.instinct.learner import InstinctLearner

learner = InstinctLearner(Path.cwd() / '.vibe' / 'instincts.jsonl')
stats = learner.get_stats()
print(f'Total instincts: {stats.get(\"total\", 0)}')
print(f'Reliable: {stats.get(\"reliable\", 0)}')
print(f'Sequence candidates: {len(learner.get_sequence_candidates())}')
"
```

---

## `/instinct-export` — Export Instincts

Export all reliable instincts (or filtered by tag/confidence) to YAML for backup or team sharing.

```bash
python3 -c "
from pathlib import Path
import json
from vibesop.core.instinct.learner import InstinctLearner

learner = InstinctLearner(Path.cwd() / '.vibe' / 'instincts.jsonl')
instincts = learner.get_reliable_instincts()

# Optional: filter by tag or confidence
# instincts = [i for i in instincts if i.confidence >= 0.8]
# instincts = [i for i in instincts if 'python' in [t.lower() for t in i.tags]]

data = {
    'version': '1.0',
    'exported_at': __import__('datetime').datetime.now().isoformat(),
    'instincts': [i.to_dict() for i in instincts],
}

output_path = Path.cwd() / 'instincts-export.json'
output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str))
print(f'Exported {len(instincts)} instincts to {output_path}')
"
```

Replace `instincts-export.json` with the desired filename. The agent can then share this file.

---

## `/instinct-import` — Import Instincts

Import instincts from a shared JSON export file.

### Import (Skip Duplicates — Safe Default)

```bash
python3 -c "
from pathlib import Path
import json
from vibesop.core.instinct.learner import InstinctLearner, Instinct

input_path = Path('<PATH_TO_EXPORT_FILE>')
if not input_path.exists():
    print(f'File not found: {input_path}')
    exit(1)

data = json.loads(input_path.read_text())
incoming = [Instinct.from_dict(i) for i in data.get('instincts', [])]

learner = InstinctLearner(Path.cwd() / '.vibe' / 'instincts.jsonl')
imported = 0
skipped = 0
for instinct in incoming:
    if instinct.id not in learner._instincts:
        learner._instincts[instinct.id] = instinct
        # Persist to storage
        with learner.storage_path.open('a') as f:
            f.write(json.dumps(instinct.to_dict(), default=str) + '\n')
        imported += 1
    else:
        skipped += 1

print(f'Imported: {imported} | Skipped (duplicates): {skipped}')
"
```

### Import with Overwrite

To overwrite existing instincts with the same ID, change `skipped` logic:

```python
# Instead of "if instinct.id not in learner._instincts", use:
learner._instincts[instinct.id] = instinct  # Always overwrite
```

---

## `/evolve` — Upgrade Instinct to Skill

Convert a high-quality instinct (confidence >= 0.8, 10+ uses) into a formal VibeSOP skill.

### Step 1: Identify Candidate

```bash
python3 -c "
from pathlib import Path
from vibesop.core.instinct.learner import InstinctLearner

learner = InstinctLearner(Path.cwd() / '.vibe' / 'instincts.jsonl')
reliable = [i for i in learner.get_reliable_instincts() if i.confidence >= 0.8 and i.total_applications >= 10]
for j, ins in enumerate(reliable):
    print(f'{j+1}. [{ins.confidence:.0%}] {ins.pattern} ({ins.total_applications} uses)')
if not reliable:
    print('No instincts ready for evolution (need confidence >= 0.8 and 10+ uses)')
"
```

### Step 2: Generate SKILL.md

Pick the instinct to evolve and run:

```bash
python3 -c "
from pathlib import Path
from vibesop.core.instinct.learner import InstinctLearner

learner = InstinctLearner(Path.cwd() / '.vibe' / 'instincts.jsonl')
reliable = [i for i in learner.get_reliable_instincts() if i.confidence >= 0.8 and i.total_applications >= 10]

ins = reliable[<INDEX>]  # 0-based index from step 1

skill_id = 'custom/' + ins.pattern.lower().replace(' ', '-').replace(',', '')[:50]
skill_dir = Path.cwd() / '.vibe' / 'skills' / skill_id
skill_dir.mkdir(parents=True, exist_ok=True)

skill_md = f'''---
id: {skill_id}
name: {skill_id}
description: {ins.pattern} (evolved from instinct)
tags: {ins.tags}
intent: workflow
namespace: custom
version: 1.0.0
type: prompt
source: instinct-evolution
instinct_id: {ins.id}
---

# {ins.pattern}

## Overview

Pattern evolved from instinct with {ins.confidence:.0%} confidence ({ins.total_applications} uses).

## When to Apply

{ins.context}

## Steps

When this pattern matches, {ins.action}.

## Metrics

- **Confidence**: {ins.confidence:.0%}
- **Success rate**: {ins.success_rate:.0%} ({ins.success_count}/{ins.total_applications})
- **Evolved from**: instinct #{ins.id[:8]}
'''

(skill_dir / 'SKILL.md').write_text(skill_md)
print(f'Skill created: {skill_dir}/SKILL.md')
print(f'Skill ID: {skill_id}')
print()
print('Next: run \"vibe skills suggestions\" to register it formally.')
"
```

### Step 3: Register the Skill

After generating the SKILL.md, register it with VibeSOP so it becomes routable:

```bash
vibe skills suggestions
```

The new skill will appear in the routing pipeline on the next `vibe route` call.

---

## Storage

All instincts are stored in `.vibe/instincts.jsonl` (JSONL, one instinct per line). Sequence patterns in `.vibe/sequences.jsonl`. Skill suggestions in `.vibe/instincts/skill_candidates.jsonl`.

---

## Best Practices

- Use `/learn` immediately after a successful workflow (while context is fresh)
- Run `/learn-eval` at session end to review accumulated patterns
- Export high-confidence instincts (>= 0.8) for team sharing
- Evolve instincts to skills after 10+ successful uses
- Keep instinct descriptions specific and actionable (not vague)
