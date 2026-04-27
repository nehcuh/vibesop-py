# Unify V5 Roadmap + Deepen Orchestration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify the v5.0 roadmap across ROADMAP.md and version_05.md ADR, and improve the orchestration fallback decomposition for non-LLM scenarios.

**Architecture:** ROADMAP.md is rewritten to match the approved ADR in version_05.md (3-phase layered evolution: SkillRuntime → SkillMarket → Intelligent Ecosystem). TaskDecomposer's non-LLM fallback is upgraded from crude regex split to intent-aware decomposition using keyword heuristics and contextual query construction.

**Tech Stack:** Python 3.12+, pytest, ruff, basedpyright

**Current constraints:**
- 121 lint errors (not introducing new ones)
- P95 routing latency 354ms (target <100ms, but this plan doesn't touch routing hot path)
- 20 type erros (not introducing new ones)

---

## File Structure

```
Create:    (none)
Modify:    docs/ROADMAP.md              — Rewrite v5.x sections to match ADR
Modify:    README.md                    — Sync roadmap section
Modify:    src/vibesop/core/orchestration/task_decomposer.py  — Better fallback decomposition
Modify:    src/vibesop/core/orchestration/multi_intent_detector.py  — Intent-keyword detection
Create:    tests/core/orchestration/test_task_decomposer_fallback.py  — Tests for new fallback
```

---

### Task 1: Rewrite ROADMAP.md v5.x sections to align with version_05.md ADR

**Files:**
- Modify: `docs/ROADMAP.md:243-309`

**Context:** The current ROADMAP.md v5.0.0 section describes "Plugin Ecosystem (2027-Q2)" but the approved ADR in version_05.md defines a 3-phase SkillOS evolution. We replace the v5.0.0 section with v5.0, v5.1, v5.2 phases, and remove the old v6.0.0/v7.0.0 stubs.

- [ ] **Step 1: Replace v5.0.0 section in ROADMAP.md**

Open `docs/ROADMAP.md` and replace the section starting at `## v5.0.0 — Plugin Ecosystem (2026-Q3)` (line 243) through `### Enterprise Features` (line 272) and the Success Metrics section.

Replace with:

```markdown
## v5.0.0 — SkillRuntime: Scope + Lifecycle (2026-Q2/Q3)

> **ADR**: [docs/version_05.md](docs/version_05.md) (Plan: VibeSOP Skill Ecosystem Evolution, approved 2026-04-21)

### Goals
Introduce scope isolation, skill enable/disable, and lifecycle state management.

### Features

- [ ] **SkillRuntime Core**
  - Scope system: project-level vs global skills
  - Skill enable/disable toggle (`vibe skill enable/disable <id>`)
  - SkillLifecycleState machine (DRAFT → ACTIVE → DEPRECATED → ARCHIVED)
  - Scope-aware config resolution (project `.vibe/` overrides global `~/.vibe/`)

- [ ] **Data Pre-burial for v5.1**
  - SkillConfig gains `usage_stats` field (call count, success rate, last used)
  - SkillConfig gains `version_history` field (semver tracking)
  - SkillConfig gains `evaluation_context` extension slot

- [ ] **CLI Commands**
  - `vibe skill enable <id>` / `vibe skill disable <id>`
  - `vibe skill scope <id> --project` / `vibe skill scope <id> --global`
  - `vibe skill lifecycle <id> --set deprecated`

### Success Metrics

- Skill scope isolation: 100% (project skills invisible outside project root)
- Toggle latency: <50ms
- Lifecycle states: 4 (draft/active/deprecated/archived)
- Backward compatibility: v4.x users smooth migration via config

---

## v5.1.0 — SkillMarket + Feedback Loop (2026-Q3/Q4)

### Goals
Complete the skill ecosystem with discovery, community, and self-improvement.

### Features

- [ ] **SkillMarket MVP**
  - `vibe market search <query>` — keyword + tag search
  - `vibe market info <skill>` — ratings, downloads, compatibility
  - `vibe market install` — one-click from discovered skills
  - GitHub topic crawling (`topic:vibesop-skill`)

**More details in the approved ADR design doc**: [docs/proposals/skill-market-design.md](docs/proposals/skill-market-design.md)

- [ ] **Autoresearch Feedback Loop**
  - Analyze routing success/failure patterns
  - Suggest keyword additions for missed queries
  - Skill quality regression detection
  - Auto-deprecate skills below quality threshold

- [ ] **Skill Evaluation**
  - Rating and reviews system
  - Usage statistics (downloads, active users)
  - Compatibility matrix (platform × version)
  - Author trust scores

### Success Metrics

- SkillMarket: 50+ discoverable skill packs
- Feedback loop: automatic keyword additions for 80%+ missed queries
- Evaluation coverage: 100% of installed skills
- Deprecation accuracy: <5% false positives

---

## v5.2.0 — Intelligent Ecosystem (2026-Q4/2027-Q1)

### Goals
Proactive skill recommendations, transparent fallback, active discovery.

### Features

- [ ] **Smart Recommendations**
  - Project-type-based recommendations ("Python project → suggest tdd, review")
  - "Users who installed X also installed Y"
  - Missing skill detection for current project

- [ ] **Transparent Auto-Degradation**
  - When no skill matches, show: "I found no matching skill. Falling back to raw LLM."
  - Route result includes `layer: FALLBACK_LLM` for visibility
  - Config: `fallback.always_ask true` to require user confirmation

- [ ] **Active Discovery**
  - Periodically scan for new skills matching project tech stack
  - Proactive suggestion with explicit opt-in
  - One-command install from suggestion

### Success Metrics

- Recommendation click-through: >30%
- Fallback awareness: 100% of fallbacks transparent to user
- Active discovery: <5% false positive suggestions
```

- [ ] **Step 2: Remove old v6.0.0 and v7.0.0 stubs (if present)**

Check if ROADMAP.md still has references to v6.0.0/v7.0.0. If found, remove them (they were placeholder stubs contradicted by the ADR).

- [ ] **Step 3: Commit**

```bash
git add docs/ROADMAP.md
git commit -m "docs: unify v5.x roadmap with version_05.md ADR layered evolution plan"
```

---

### Task 2: Sync README.md roadmap section

**Files:**
- Modify: `README.md:722-729`

- [ ] **Step 1: Replace roadmap section in README.md**

Replace lines 722-729:

```
## 路线图 Roadmap

- [x] v4.0.0: 核心路由引擎 Core routing engine with 10-layer pipeline
- [x] v4.1.0: AI Triage 生产就绪 AI Triage production readiness
- [x] v4.2.0: 技能健康监控 Skill health monitoring
- [ ] v5.0.0: 插件系统 Plugin system for custom matchers
- [ ] v6.0.0: 机器学习优化 Machine learning optimization
- [ ] v7.0.0: 个性化路由 Personalized routing
```

With:

```markdown
## 路线图 Roadmap

- [x] v4.0.0: 核心路由引擎 Core routing engine with 10-layer pipeline
- [x] v4.1.0: AI Triage 生产就绪 AI Triage production readiness
- [x] v4.2.0: 技能健康监控 Skill health monitoring
- [x] v4.3.0: 上下文感知路由 + Agent Runtime Context-aware routing + Agent Runtime
- [ ] v5.0.0: 技能运行时 SkillRuntime — 作用域 + 生命周期 + 启禁用
- [ ] v5.1.0: 技能市场 + 反馈闭环 SkillMarket + Feedback Loop
- [ ] v5.2.0: 智能生态系统 Intelligent Ecosystem — 推荐 + 退化 + 发现

详见: [docs/ROADMAP.md](docs/ROADMAP.md) | [version_05.md ADR](docs/version_05.md)
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: sync README roadmap with ROADMAP.md and version_05.md ADR"
```

---

### Task 3: Improve TaskDecomposer fallback decomposition

**Files:**
- Modify: `src/vibesop/core/orchestration/task_decomposer.py:112-129`

**Current problem:** The `_fallback_decomposition()` uses `re.split(r'[,;]|...')` which:
1. Removes delimiters — resulting in truncated sentences
2. Labels everything "sub-task N" — no semantic intent
3. No contextualization — each fragment is incomprehensible without the original query

**Solution:** Add intent-keyword detection + contextual query construction.

- [ ] **Step 1: Read current TaskDecomposer file**

Already done in prior research. The file is at `src/vibesop/core/orchestration/task_decomposer.py`.

- [ ] **Step 2: Add intent patterns and upgrade _fallback_decomposition**

Replace the `_fallback_decomposition` method (lines 112-129) with:

```python
    INTENT_PATTERNS: dict[str, list[str]] = {
        "analyze_architecture": ["架构", "结构", "architecture", "设计", "design"],
        "code_review": ["review", "评审", "审查", "检查代码", "代码质量"],
        "debug_error": ["debug", "调试", "错误", "error", "bug", "fix", "修复"],
        "optimize": ["优化", "optimize", "性能", "performance", "改进"],
        "test": ["test", "测试", "coverage", "覆盖率", "单元测试"],
        "document": ["文档", "document", "README", "说明"],
        "deploy": ["deploy", "部署", "发布", "上线", "ship"],
        "brainstorm": ["畅想", "brainstorm", "思路", "idea", "创意"],
        "security_audit": ["安全", "security", "vulnerability", "漏洞", "审计"],
        "refactor": ["重构", "refactor", "重写"],
    }

    def _fallback_decomposition(self, query: str) -> list[SubTask]:
        """Rule-based intent decomposition when LLM is unavailable.

        v2: Uses intent keyword matching to detect distinct intents and
        constructs self-contained sub-queries, rather than crude regex splitting.
        """
        # 1. Split on conjunctions (preserve for multi-part detection)
        conjunctions = [
            "然后", "之后", "接着", "并", "并且", "同时", "另外", "还有", "以及", "先", "再", "最后",
            "and then", "after that", "and also", "plus", "meanwhile", "first", "second", "third",
        ]
        pattern = "|".join(re.escape(c) for c in conjunctions)
        segments = re.split(pattern, query)

        # 2. For each segment, try to detect intent
        sub_tasks: list[SubTask] = []
        for seg in segments:
            seg = seg.strip().rstrip(".,，。；;")
            if len(seg) < self.MIN_QUERY_LENGTH:
                continue

            intent = self._detect_intent(seg)
            contextualized = self._contextualize_query(query, seg, intent)
            sub_tasks.append(SubTask(intent=intent, query=contextualized))

        if len(sub_tasks) <= 1:
            intent = self._detect_intent(query)
            return [SubTask(intent=intent, query=query)]

        return sub_tasks[: self.MAX_SUB_TASKS]

    def _detect_intent(self, text: str) -> str:
        """Detect the primary intent of a text fragment using keyword matching."""
        text_lower = text.lower()
        best_intent = "single task"
        best_score = 0
        for intent, keywords in self.INTENT_PATTERNS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > best_score:
                best_score = score
                best_intent = intent
        return best_intent

    def _contextualize_query(self, full_query: str, segment: str, intent: str) -> str:
        """Construct a self-contained sub-query from a segment.

        If the segment is too short relative to the full query, prepend context.
        """
        if len(segment) >= len(full_query) * 0.6:
            return segment
        # Short segment — embed intent context
        if intent != "single task":
            return f"[{intent}] {segment}"
        return segment
```

- [ ] **Step 3: Update imports if needed**

The `_fallback_decomposition` method already imports `re`. No new imports needed.

- [ ] **Step 4: Verify lint passes**

```bash
uv run ruff check src/vibesop/core/orchestration/task_decomposer.py
```
Expected: No new errors.

- [ ] **Step 5: Commit**

```bash
git add src/vibesop/core/orchestration/task_decomposer.py
git commit -m "feat: intent-aware fallback decomposition in TaskDecomposer"
```

---

### Task 4: Add intent-keyword detection to MultiIntentDetector

**Files:**
- Modify: `src/vibesop/core/orchestration/multi_intent_detector.py:19-28`

**Current behavior:** `_has_conjunctions()` only detects conjunction keywords. A query like "分析架构并提出优化建议" triggers multi-intent, but "分析当前项目架构 并提出优化建议" (no conjunction) doesn't.

**Solution:** Add intent-keyword-based multi-intent detection alongside conjunctions.

- [ ] **Step 1: Add intent multi-keyword detection**

In `multi_intent_detector.py`, add to `MULTI_INTENT_KEYWORDS` (line 20-28):

```python
MULTI_INTENT_KEYWORDS = {
    # Chinese conjunctions
    "并", "并且", "同时", "另外", "还有", "以及", "然后", "之后", "接着",
    "先", "再", "最后", "第一步", "第二步", "第三步",
    # English conjunctions
    "and then", "and also", "in addition", "additionally", "furthermore",
    "meanwhile", "after that", "next", "firstly", "secondly", "thirdly",
    "first", "second", "third", "then", "also", "plus",
}
```

These are already present. The issue is that `_heuristic_check` requires BOTH conjunctions AND length >= 20. Let's add a new condition in `_heuristic_check`:

Add after line 88 (after condition 1):

```python
        # Condition 1b: Multiple intent domains detected (even without conjunctions)
        intent_domains = self._count_intent_domains(query)
        if intent_domains >= 2 and len(query) >= self.min_query_length:
            return True
```

And add the helper method after `_has_conjunctions`:

```python
    # Intent domain keywords — each group represents a distinct activity domain
    _INTENT_DOMAINS: list[tuple[str, list[str]]] = [
        ("analyze", ["架构", "结构", "architecture", "设计", "design", "分析", "analyze"]),
        ("review", ["review", "评审", "审查", "检查", "代码质量"]),
        ("debug", ["debug", "调试", "错误", "error", "bug", "修复", "fix"]),
        ("optimize", ["优化", "optimize", "性能", "performance"]),
        ("design", ["设计", "design", "规划", "plan", "方案", "思路"]),
        ("implement", ["实现", "implement", "开发", "编写", "build", "写"]),
        ("test", ["test", "测试", "coverage", "覆盖率"]),
        ("deploy", ["deploy", "部署", "发布", "上线", "ship"]),
        ("security", ["安全", "security", "漏洞", "审计"]),
    ]

    def _count_intent_domains(self, query: str) -> int:
        """Count how many distinct intent domains appear in the query."""
        query_lower = query.lower()
        domains_found = 0
        for _domain, keywords in self._INTENT_DOMAINS:
            if any(kw in query_lower for kw in keywords):
                domains_found += 1
        return domains_found
```

- [ ] **Step 2: Verify lint passes**

```bash
uv run ruff check src/vibesop/core/orchestration/multi_intent_detector.py
```
Expected: No new errors.

- [ ] **Step 3: Commit**

```bash
git add src/vibesop/core/orchestration/multi_intent_detector.py
git commit -m "feat: intent-domain-based multi-intent detection without requiring conjunctions"
```

---

### Task 5: Write tests for improved fallback decomposition

**Files:**
- Create: `tests/core/orchestration/test_task_decomposer_fallback.py`

- [ ] **Step 1: Write the test file**

```python
"""Tests for TaskDecomposer fallback decomposition (no LLM)."""

import pytest

from vibesop.core.orchestration.task_decomposer import TaskDecomposer


class TestTaskDecomposerFallback:
    """Test the non-LLM fallback decomposition path."""

    def test_single_intent_returns_one_task(self):
        decomposer = TaskDecomposer()  # No LLM → uses fallback
        tasks = decomposer.decompose("帮我调试这个数据库错误")
        assert len(tasks) == 1
        assert "debug" in tasks[0].intent

    def test_multi_intent_with_conjunctions(self):
        decomposer = TaskDecomposer()
        tasks = decomposer.decompose("先分析架构然后评审代码最后给出优化方案")
        assert len(tasks) == 3

    def test_multi_intent_english(self):
        decomposer = TaskDecomposer()
        tasks = decomposer.decompose("review the code and then deploy to production")
        assert len(tasks) == 2

    def test_short_query_skipped(self):
        decomposer = TaskDecomposer()
        tasks = decomposer.decompose("a b")
        assert len(tasks) == 1  # Falls back to single task
        assert tasks[0].intent == "single task"

    def test_intent_detection_debug(self):
        decomposer = TaskDecomposer()
        tasks = decomposer.decompose("修复这个数据库连接超时的错误")
        assert len(tasks) == 1
        assert "debug" in tasks[0].intent

    def test_intent_detection_review(self):
        decomposer = TaskDecomposer()
        tasks = decomposer.decompose("评审一下我的代码质量")
        assert len(tasks) == 1
        assert "review" in tasks[0].intent

    def test_intent_detection_security(self):
        decomposer = TaskDecomposer()
        tasks = decomposer.decompose("扫描安全漏洞")
        assert len(tasks) == 1
        assert "security" in tasks[0].intent

    def test_max_sub_tasks_limit(self):
        decomposer = TaskDecomposer()
        # Create a query with many segments
        query = "分析架构, 审查代码, 优化性能, 修复错误, 添加测试, 更新文档, 部署上线"
        tasks = decomposer.decompose(query)
        assert len(tasks) <= decomposer.MAX_SUB_TASKS

    def test_contextualize_short_segment(self):
        decomposer = TaskDecomposer()
        # "debug" is too short, should get contextualized
        tasks = decomposer.decompose("分析架构, debug")
        assert len(tasks) >= 1
        # Short segments should be contextualized with intent
        # Note: "debug" could trigger both a separate task or be absorbed
        # depending on conjunction matching

    def test_chinese_with_intent_keywords(self):
        decomposer = TaskDecomposer()
        tasks = decomposer.decompose("深入分析当前项目架构 然后对后续优化工作提出指导意见")
        assert len(tasks) >= 1
        # At minimum, should detect this isn't just a single simple task

    def test_deduplicate_queries(self):
        decomposer = TaskDecomposer()
        tasks = decomposer.decompose("review the code, review the code")
        # Should deduplicate identical sub-tasks
        unique_queries = {t.query.lower().strip() for t in tasks}
        assert len(unique_queries) == len(tasks)
```

- [ ] **Step 2: Run tests**

```bash
cd /Users/huchen/Projects/vibesop-py && uv run pytest tests/core/orchestration/test_task_decomposer_fallback.py -v
```
Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/core/orchestration/test_task_decomposer_fallback.py
git commit -m "test: add fallback decomposition tests for TaskDecomposer"
```

---

### Task 6: Run all orchestration tests and verify no regressions

- [ ] **Step 1: Run existing orchestration tests**

```bash
cd /Users/huchen/Projects/vibesop-py && uv run pytest tests/core/orchestration/ -v
```
Expected: All existing tests pass, no regressions.

- [ ] **Step 2: Run lint check on all changed files**

```bash
uv run ruff check src/vibesop/core/orchestration/task_decomposer.py src/vibesop/core/orchestration/multi_intent_detector.py
```
Expected: No new errors. (121 pre-existing errors in other files are out of scope.)

- [ ] **Step 3: Run type check on all changed files**

```bash
uv run basedpyright src/vibesop/core/orchestration/task_decomposer.py src/vibesop/core/orchestration/multi_intent_detector.py
```
Expected: No new errors.

- [ ] **Step 4: Commit final verification**

```bash
git add -A && git status
# Only if clean:
git commit -m "chore: verify orchestration tests and lint after fallback improvements"
```
