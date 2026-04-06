# Phase 2: Core omx/ Skills — SKILL.md Definitions

> **Status**: Revised for v4.0 - Router Engine Only
> **Updated**: 2026-04-06
> **Goal**: Create pure SKILL.md definitions for omx/ methodologies

---

## Overview

**v4.0 定位调整**: VibeSOP 是**路由引擎**，不执行技能。

Phase 2 专注于：
1. **算法库** (`algorithms/`) - 纯数学/检测算法，可复用
2. **SKILL.md** - 纯提示词定义，供 AI Agent 执行

**不再包含**（已删除）:
- ❌ 状态管理 (stages, loop, crystallizer)
- ❌ 执行逻辑 (verifier subprocess 调用)
- ❌ 工作流 pipeline

---

## File Structure

### 算法库 (已实现)

| 文件 | 状态 | 说明 |
|------|------|------|
| `src/vibesop/core/algorithms/__init__.py` | ✅ | 公共导出，@experimental |
| `src/vibesop/core/algorithms/interview/__init__.py` | ✅ | 包导出 |
| `src/vibesop/core/algorithms/interview/ambiguity.py` | ✅ | 数学公式，测试覆盖 |
| `src/vibesop/core/algorithms/ralph/__init__.py` | ✅ | 包导出 |
| `src/vibesop/core/algorithms/ralph/deslop.py` | ✅ | AI slop 检测，测试覆盖 |
| `tests/test_interview_ambiguity.py` | ✅ | 测试 |
| `tests/test_ralph_deslop.py` | ✅ | 测试 |

### SKILL.md 定义 (待创建)

| 文件 | 状态 | 说明 |
|------|------|------|
| `core/skills/omx/deep-interview/SKILL.md` | ⏳ | Socratic 需求澄清 |
| `core/skills/omx/ralph/SKILL.md` | ⏳ | 持久完成循环 |
| `core/skills/omx/ralplan/SKILL.md` | ⏳ | 结构化规划 |

---

## 算法库 API

### interview/ambiguity.py

数学公式计算需求模糊度：

```python
from vibesop.core.algorithms import compute_ambiguity, DimensionScore

result = compute_ambiguity(
    DimensionScore(score=0.8, evidence=["clear goal"]),
    DimensionScore(score=0.5),
    DimensionScore(score=0.6),
    DimensionScore(score=0.4),
    DimensionScore(score=0.7),
)

print(f"Ambiguity: {result.ambiguity:.2f}")
print(f"Weakest: {result.weakest_dimension()}")
```

**权重**:
- Intent: 30%
- Outcome: 25%
- Scope: 20%
- Constraints: 15%
- Success: 10%

### ralph/deslop.py

AI slop 模式检测：

```python
from vibesop.core.algorithms import scan_file

report = scan_file("path/to/code.py")

if report.has_slop:
    print(f"Found {len(report.findings)} slop patterns")
    for finding in report.findings:
        print(f"  - {finding['pattern']}: line {finding['line']}")
```

**检测模式**:
- 过度注释
- 冗余解释
- 不必要的抽象
- Boilerplate docstring
- 过度工程化的导入

---

## SKILL.md 模板

### deep-interview/SKILL.md

```markdown
---
id: omx/deep-interview
name: Deep Interview
description: Socratic requirements clarification with mathematical ambiguity scoring
intent: requirements
namespace: omx
version: 1.0.0
type: prompt
trigger_when: asked to clarify requirements, understand a task, or figure out what to build
---

# Deep Interview

Socratic requirements clarification. Ask ONE question at a time.

## Ambiguity Scoring

Calculate initial ambiguity using 5 dimensions:

1. **Intent** (30%): What problem? For whom? Why now?
2. **Outcome** (25%): What does success look like?
3. **Scope** (20%): What's in? What's out?
4. **Constraints** (15%): Deadlines? Tech limits?
5. **Success** (10%): What would make you say "this worked"?

Formula: `ambiguity = 1.0 - (intent×0.30 + outcome×0.25 + scope×0.20 + constraints×0.15 + success×0.10)`

## Interview Loop

1. Ask question targeting weakest dimension
2. Re-score after each answer
3. When ambiguity ≤ 0.2, crystallize and handoff

## Challenge Modes (Round 2+)

- **Contrarian**: "What if the opposite is true?"
- **Simplifier**: "Can this be done in half the steps?"
- **Ontologist**: "What category of problem is this really?"

## Output

Write execution spec to `.vibe/specs/` with:
- Clarity score
- Dimension breakdown
- Recommended next step (ralph/ralplan)
```

### ralph/SKILL.md

```markdown
---
id: omx/ralph
name: Ralph
description: Persistent completion loop with mandatory deslop pass
intent: execution
namespace: omx
version: 1.0.0
type: prompt
trigger_when: asked to implement something with guaranteed completion
---

# Ralph — "Never Give Up" Execution

Persistent completion loop. Iterate until the work is truly done.

## Pre-flight

1. Load `.vibe/specs/` if available
2. If ambiguity > 0.3, run deep-interview first
3. Identify what needs to be done

## Loop (max 10 iterations)

Each iteration:

1. **Review**: What's done? What's left?
2. **Delegate**: Split work, do in parallel
3. **Verify**: Run tests → must pass
4. **Architect Review**: Large changes need review
5. **Deslop Pass**: Remove AI slop patterns
6. **Re-verify**: Tests must still pass

## Deslop Patterns

Check for:
- Excessive comments explaining obvious code
- Redundant docstrings repeating implementation
- Unnecessary abstractions
- Boilerplate template code
- Over-engineered imports

## Exit Criteria

- **Approve**: All tests pass, user satisfied
- **Reject**: Any failure → fix → loop

## State Persistence

Save iteration state to `.vibe/state/ralph/` after each iteration.
```

### ralplan/SKILL.md

```markdown
---
id: omx/ralplan
name: Ralplan
description: Structured planning with consensus-driven deliberation
intent: planning
namespace: omx
version: 1.0.0
type: prompt
trigger_when: asked to plan, architect, or design a feature
---

# Ralplan — Consensus Planning

Structured deliberation with architect review and critic evaluation.

## Pre-flight

1. Load `.vibe/specs/` if available
2. If ambiguity > 0.3, run deep-interview first

## Deliberation (RALPLAN-DR)

1. **Principles**: What principles guide this decision?
2. **Decision Drivers**: What factors matter most?
3. **Viable Options**: List 2-3 viable approaches (no strawmen)

## Architect Review

- Steelman the antithesis: argue AGAINST the favored option
- Identify risks, trade-offs, hidden costs

## Critic Evaluation

- Verify principle-option consistency
- Simulate each task mentally
- Flag violations

## Re-review Loop (max 5 iterations)

Apply improvements from architect and critic. Re-evaluate.

## Output

Write plan to `.vibe/plans/` with ADR section:

```yaml
Plan: <name>
Date: <date>
Status: approved | needs_revision
ADR:
  Context: <what decision needed>
  Decision: <what was decided>
  Consequences: <what follows>
```

## Handoff

User approval → handoff to ralph (execute).
```

---

## Registry Updates

Add to `core/registry.yaml`:

```yaml
skills:
  # ... existing skills ...

  # omx/ skills
  - id: omx/deep-interview
    namespace: omx
    entrypoint: skills/omx/deep-interview/SKILL.md
    intent: requirements
    trigger_mode: suggest
    priority: P1

  - id: omx/ralph
    namespace: omx
    entrypoint: skills/omx/ralph/SKILL.md
    intent: execution
    trigger_mode: suggest
    priority: P1

  - id: omx/ralplan
    namespace: omx
    entrypoint: skills/omx/ralplan/SKILL.md
    intent: planning
    trigger_mode: suggest
    priority: P1
```

---

## Success Criteria

| Criterion | Target |
|-----------|--------|
| 算法库测试覆盖 | > 80% |
| SKILL.md 创建 | 3 个 |
| Registry 注册 | 3 个技能 |
| 与 v4.0 定位一致 | ✅ 只路由，不执行 |

---

*Revised for v4.0 Router Engine定位*
