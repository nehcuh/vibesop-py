# Design: oh-my-codex Integration + Skill Semantic Optimization

> **Version**: 1.0
> **Date**: 2026-04-05
> **Status**: Approved
> **Author**: vibesop-py team

## 1. Problem Statement

VibeSOP-Py v3.0.0 has 37 registered skills across 4 namespaces (builtin, superpowers, gstack, project). The project aims to fully integrate oh-my-codex's 7 core engineering methodologies (deep-interview, ralph, ralplan, team, ultrawork, autopilot, ultraqa) as first-class citizens.

Adding 7 skills → 44 total creates two challenges:
1. **Routing quality degradation**: Without optimization, more skills = more noise in matching results
2. **Execution gaps**: omx/ methodologies require real Python implementations, not just SKILL.md stubs

## 2. Architecture Overview

```
vibesop-py v3.1.0
├── src/vibesop/core/
│   ├── optimization/          ← NEW: Three-layer skill optimization
│   │   ├── __init__.py
│   │   ├── prefilter.py       ← Layer 1: Candidate pre-filtering
│   │   ├── preference_boost.py ← Layer 2: Preference learning integration
│   │   └── clustering.py      ← Layer 3: Semantic clustering
│   ├── interview/             ← NEW: deep-interview implementation
│   │   ├── __init__.py
│   │   ├── ambiguity.py       ← Mathematical ambiguity scoring
│   │   ├── stages.py          ← Interview stage management
│   │   ├── pressure.py        ← Pressure ladder + challenge modes
│   │   └── crystallizer.py    ← Artifact generation
│   ├── ralph/                 ← NEW: Persistent completion loop
│   │   ├── __init__.py
│   │   ├── loop.py            ← Main iteration loop
│   │   ├── deslop.py          ← AI slop cleaning
│   │   ├── verifier.py        ← Tiered verification
│   │   └── visual_verdict.py  ← UI scoring gate
│   ├── plan/                  ← NEW: Structured planning
│   │   ├── __init__.py
│   │   ├── deliberation.py    ← RALPLAN-DR deliberation
│   │   ├── architect.py       ← Architect review
│   │   ├── critic.py          ← Critic evaluation
│   │   └── gate.py            ← Pre-execution gate
│   ├── team/                  ← NEW: Multi-agent runtime (Python asyncio)
│   │   ├── __init__.py
│   │   ├── runtime.py         ← Async parallel runtime
│   │   ├── mailbox.py         ← File-based mailbox/dispatch
│   │   ├── worker.py          ← Worker protocol
│   │   └── monitor.py         ← Status monitoring
│   ├── pipeline/              ← NEW: Pipeline components
│   │   ├── __init__.py
│   │   ├── ultrawork.py       ← Tier-aware parallel execution
│   │   ├── autopilot.py       ← Full lifecycle pipeline
│   │   └── ultraqa.py         ← Autonomous QA cycling
│   └── state/                 ← NEW: Unified state management
│       ├── __init__.py
│       ├── manager.py         ← State read/write/clear
│       ├── schema.py          ← Pydantic state models
│       └── migration.py       ← Legacy data migration
│
├── core/skills/omx/           ← NEW: omx/ skill definitions
│   ├── deep-interview/SKILL.md
│   ├── ralph/SKILL.md
│   ├── ralplan/SKILL.md
│   ├── team/SKILL.md
│   ├── ultrawork/SKILL.md
│   ├── autopilot/SKILL.md
│   └── ultraqa/SKILL.md
│
├── core/registry.yaml         ← UPDATED: Add omx/ namespace + 7 skills
├── .vibe/                     ← EXTENDED: New state directories
│   ├── interviews/            ← deep-interview transcripts
│   ├── plans/                 ← Approved plans (ralplan output)
│   ├── specs/                 ← Execution-ready specs
│   ├── context/               ← Context snapshots
│   └── state/                 ← Runtime state
│       ├── ralph/
│       ├── team/
│       └── sessions/
│
└── src/vibesop/core/routing/
    └── unified.py             ← UPDATED: Integrate 3-layer optimization
```

## 3. Layer 1: Candidate Pre-filtering

### 3.1 Problem

Current `UnifiedRouter` scores ALL candidates against EVERY query. With 44+ skills, this creates noise — unrelated skills compete for the same query.

### 3.2 Design

Add a pre-filtering stage BEFORE the matcher pipeline:

```python
# Pseudocode
def route(query, candidates):
    candidates = prefilter(query, candidates)  # 44 → 8-15
    for layer, matcher in self._matchers:
        matches = matcher.match(query, candidates, ...)
        if good_match: return matches
```

### 3.3 Pre-filtering Strategy (3-stage cascade)

**Stage A: Priority Tier Filter**
- P0 skills (systematic-debugging, verification-before-completion, session-end) ALWAYS included
- P1 skills included for queries with complexity indicators (multiple concepts, "复杂", "很多文件")
- P2 skills only included if query contains their namespace or explicit override keywords

**Stage B: Namespace Relevance Filter**
- Build a namespace→intent index from `registry.yaml`
- For each query, compute namespace relevance score using keyword overlap
- Keep namespaces with relevance > 0.3, or top-2 if none exceed threshold

**Stage C: Intent Cluster Filter**
- Pre-compute intent clusters from skill descriptions (see Layer 3)
- Map query to most relevant cluster(s)
- Include all skills in matched cluster + P0 skills

### 3.4 Expected Reduction

| Query Type | Before | After | Reduction |
|-----------|--------|-------|-----------|
| "帮我调试数据库错误" | 44 | 6 | 86% |
| "发布新版本" | 44 | 8 | 82% |
| "这个功能怎么设计" | 44 | 12 | 73% |
| "review 这个 PR" | 44 | 7 | 84% |

### 3.5 File: `src/vibesop/core/optimization/prefilter.py`

```python
class CandidatePrefilter:
    """Pre-filter skill candidates before matching.

    Reduces candidate set from N to ~8-15 using:
    1. Priority tier filtering (P0 always included)
    2. Namespace relevance filtering
    3. Intent cluster filtering
    """

    def __init__(self, registry_path: str, cluster_index: SkillClusterIndex):
        ...

    def filter(self, query: str, candidates: list[dict]) -> list[dict]:
        """Filter candidates for a query.

        Returns filtered candidate list (8-15 items typically).
        """
        # Stage A: Priority tier
        tier_filtered = self._filter_by_priority(query, candidates)

        # Stage B: Namespace relevance
        ns_filtered = self._filter_by_namespace(query, tier_filtered)

        # Stage C: Intent cluster
        return self._filter_by_cluster(query, ns_filtered)
```

## 4. Layer 2: Preference Learning Integration

### 4.1 Problem

`PreferenceLearner` exists but is NEVER called by `UnifiedRouter`. User preferences have zero impact on routing decisions.

### 4.2 Design

Integrate preference scoring into the final ranking stage:

```python
# In UnifiedRouter.route(), after matcher returns results:
def _apply_preference_boost(self, matches, query):
    preference_learner = PreferenceLearner()
    skill_ids = [m.skill_id for m in matches]
    boosted_rankings = preference_learner.get_personalized_rankings(skill_ids, query)

    # Re-rank matches by combining matcher confidence + preference
    for match, (_, pref_score) in zip(matches, boosted_rankings):
        match.confidence = match.confidence * 0.7 + pref_score * 0.3

    return sorted(matches, key=lambda m: m.confidence, reverse=True)
```

### 4.3 Configuration

```yaml
# In routing config
optimization:
  preference_boost:
    enabled: true
    weight: 0.3          # Preference weight in final score
    min_samples: 2       # Minimum selections before trusting preference
    decay_days: 30       # Days before old preferences decay
```

### 4.4 File: `src/vibesop/core/optimization/preference_boost.py`

Thin wrapper that connects `PreferenceLearner` to `UnifiedRouter`'s ranking pipeline.

## 5. Layer 3: Semantic Clustering + Conflict Resolution

### 5.1 Problem

Conflict resolution in `registry.yaml` is manually maintained (6 scenarios). Adding 7 omx/ skills requires manual updates for every overlap.

### 5.2 Design

Auto-compute skill clusters from TF-IDF vectors of skill descriptions:

```python
class SkillClusterIndex:
    """Automatically cluster skills by intent similarity.

    Uses TF-IDF + KMeans on skill descriptions.
    Produces clusters like:
    - "debugging": [systematic-debugging, gstack/investigate, superpowers/debug]
    - "planning": [planning-with-files, ralplan, gstack/plan-eng-review]
    - "execution": [riper-workflow, ralph, team, ultrawork]
    - "qa": [gstack/qa, gstack/qa-only, ultraqa]
    """

    def build(self, skills: list[dict]) -> dict[str, list[str]]:
        """Build cluster index from skill definitions."""
        # TF-IDF on descriptions
        # KMeans clustering (k determined by silhouette score)
        # Return cluster_id → [skill_ids]

    def get_cluster(self, skill_id: str) -> str:
        """Get cluster for a skill."""

    def get_cluster_members(self, cluster_id: str) -> list[str]:
        """Get all skills in a cluster."""

    def resolve_conflicts(self, query: str, matched_skills: list[str]) -> dict:
        """Auto-generate conflict resolution for matched skills.

        If multiple skills from same cluster match:
        1. Keep highest confidence match
        2. Add 2nd best as alternative
        3. Record conflict for manual review if confidence gap < 0.1
        """
```

### 5.3 Conflict Resolution Integration

The auto-generated conflicts supplement (not replace) manual rules in `registry.yaml`:

```
Manual rules (registry.yaml) → High priority, explicit overrides
Auto rules (clustering)      → Default behavior for unhandled overlaps
```

### 5.4 File: `src/vibesop/core/optimization/clustering.py`

## 6. omx/ Skill Definitions

### 6.1 omx/deep-interview

```yaml
# core/registry.yaml addition
- id: omx/deep-interview
  namespace: omx
  entrypoint: skills/omx/deep-interview/SKILL.md
  intent: Socratic requirements clarification with mathematical ambiguity scoring.
  trigger_mode: suggest
  priority: P1
  supported_targets:
    claude-code: native-skill
    opencode: native-skill
  safety_level: trusted_builtin
```

**SKILL.md workflow**:
1. Preflight: Parse task, create context snapshot in `.vibe/context/`
2. Detect greenfield vs brownfield
3. Interview loop: Ask ONE question at a time, re-score ambiguity after each answer
4. Challenge modes (round 2+: contrarian, round 4+: simplifier, round 5+: ontologist)
5. Crystallize: Write `.vibe/interviews/` transcript + `.vibe/specs/` execution spec
6. Handoff: Offer ralplan, ralph, team, or further refinement

**Ambiguity formula**:
```
ambiguity = 1.0 - (intent×0.30 + outcome×0.25 + scope×0.20 + constraints×0.15 + success×0.10)
```

### 6.2 omx/ralph

```yaml
- id: omx/ralph
  namespace: omx
  entrypoint: skills/omx/ralph/SKILL.md
  intent: Persistent completion loop with mandatory deslop pass and tiered architect verification.
  trigger_mode: suggest
  priority: P1
  supported_targets:
    claude-code: native-skill
    opencode: native-skill
  safety_level: trusted_builtin
```

**SKILL.md workflow**:
1. Pre-context: Load `.vibe/context/` snapshot, run deep-interview if ambiguity high
2. Loop (max 10 iterations):
   - Review progress, continue from last state
   - Delegate to specialists in parallel (LOW/STANDARD/THOROUGH tiers)
   - Verify with fresh evidence (tests, build, lint)
   - Architect verification (tiered by change size)
   - Mandatory deslop pass on ALL changed files
   - Regression re-verification
3. On approval: clean exit. On rejection: fix → re-verify → loop

### 6.3 omx/ralplan

```yaml
- id: omx/ralplan
  namespace: omx
  entrypoint: skills/omx/ralplan/SKILL.md
  intent: Consensus planning with RALPLAN-DR structured deliberation and ADR output.
  trigger_mode: suggest
  priority: P1
  supported_targets:
    claude-code: native-skill
    opencode: native-skill
  safety_level: trusted_builtin
```

**SKILL.md workflow**:
1. Pre-context: Load snapshot, run deep-interview if ambiguity high
2. Planner creates initial plan + RALPAN-DR summary (Principles, Decision Drivers, Viable Options)
3. Architect review: Steelman antithesis against favored option
4. Critic evaluation: Verify principle-option consistency, simulate tasks
5. Re-review loop (max 5 iterations)
6. Apply improvements, add ADR section
7. User approval → handoff to ralph or team

### 6.4 omx/team

```yaml
- id: omx/team
  namespace: omx
  entrypoint: skills/omx/team/SKILL.md
  intent: Multi-agent parallel execution with Python asyncio runtime and file-based coordination.
  trigger_mode: manual
  priority: P1
  supported_targets:
    claude-code: native-skill
    opencode: native-skill
  safety_level: trusted_builtin
```

**SKILL.md workflow**:
1. Pre-context gate
2. Start team: Parse args, initialize state, launch workers via asyncio
3. Monitor loop: Status checks, auto-nudge stalled workers
4. Shutdown: Verify evidence, cleanup

### 6.5 omx/ultrawork

```yaml
- id: omx/ultrawork
  namespace: omx
  entrypoint: skills/omx/ultrawork/SKILL.md
  intent: Tier-aware parallel execution engine for independent tasks.
  trigger_mode: manual
  priority: P2
  supported_targets:
    claude-code: native-skill
    opencode: native-skill
  safety_level: trusted_builtin
```

### 6.6 omx/autopilot

```yaml
- id: omx/autopilot
  namespace: omx
  entrypoint: skills/omx/autopilot/SKILL.md
  intent: Full autonomous lifecycle from idea to verified code.
  trigger_mode: manual
  priority: P1
  supported_targets:
    claude-code: native-skill
    opencode: native-skill
  safety_level: trusted_builtin
```

### 6.7 omx/ultraqa

```yaml
- id: omx/ultraqa
  namespace: omx
  entrypoint: skills/omx/ultraqa/SKILL.md
  intent: Autonomous QA cycling with architect diagnosis before fix.
  trigger_mode: manual
  priority: P1
  supported_targets:
    claude-code: native-skill
    opencode: native-skill
  safety_level: trusted_builtin
```

## 7. Unified State Management

### 7.1 Directory Structure

```
.vibe/
├── memory/              ← Existing: session memory
├── instincts/           ← Existing: cross-project patterns
├── experiments/         ← Existing: autonomous experiment data
├── cache/               ← Existing: routing cache
├── interviews/          ← NEW: deep-interview transcripts
├── plans/               ← NEW: approved plans (ralplan output)
├── specs/               ← NEW: execution-ready specs
├── context/             ← NEW: context snapshots
└── state/               ← NEW: runtime state
    ├── ralph/
    │   └── {scope}/ralph-state.json
    ├── team/
    │   └── {team-name}/
    │       ├── config.json
    │       ├── mailbox/
    │       └── workers/
    └── sessions/
        └── {session-id}/
```

### 7.2 State Manager API

```python
class StateManager:
    """Unified state management for all modes."""

    def write(self, mode: str, scope: str, data: dict) -> Path:
        """Write state for a mode."""

    def read(self, mode: str, scope: str) -> dict | None:
        """Read state for a mode."""

    def clear(self, mode: str, scope: str) -> None:
        """Clear state for a mode."""

    def list_active(self) -> list[dict]:
        """List all active state entries."""
```

## 8. UnifiedRouter Integration

### 8.1 Updated Route Pipeline

```
Query
  ↓
[NEW] Pre-filter (Priority + Namespace + Cluster) → 44 → 8-15 candidates
  ↓
[EXISTING] Keyword / TF-IDF / Embedding / Levenshtein matching
  ↓
[NEW] Preference boost → Re-rank by (0.7 × matcher + 0.3 × preference)
  ↓
[NEW] Cluster conflict resolution → Keep best, add alternatives
  ↓
RoutingResult
```

### 8.2 Configuration

```yaml
# In RoutingConfig
optimization:
  enabled: true
  prefilter:
    enabled: true
    min_candidates: 5
    max_candidates: 15
  preference_boost:
    enabled: true
    weight: 0.3
  clustering:
    enabled: true
    auto_resolve: true
    confidence_gap_threshold: 0.1
```

## 9. Conflict Resolution Updates

Add new conflict scenarios to `registry.yaml`:

```yaml
conflict_resolution:
  strategies:
    # ... existing 6 scenarios ...

    # Requirements clarification: omx/deep-interview is primary
    - scenario: requirements_clarification
      primary: omx/deep-interview
      primary_source: omx
      alternatives:
        - skill: gstack/office-hours
          source: gstack
          trigger: "产品头脑风暴"
        - skill: superpowers/brainstorm
          source: superpowers
          trigger: "设计细化"

    # Persistent execution: omx/ralph is primary
    - scenario: persistent_execution
      primary: omx/ralph
      primary_source: omx
      alternatives:
        - skill: riper-workflow
          source: builtin
          trigger: "5 阶段开发"

    # Structured planning: omx/ralplan is primary
    - scenario: structured_planning
      primary: omx/ralplan
      primary_source: omx
      alternatives:
        - skill: planning-with-files
          source: builtin
          trigger: "文件规划"
        - skill: gstack/plan-eng-review
          source: gstack
          trigger: "架构审查"

    # Parallel execution: omx/team is primary
    - scenario: parallel_execution
      primary: omx/team
      primary_source: omx
      alternatives:
        - skill: omx/ultrawork
          source: omx
          trigger: "纯并行执行"
        - skill: using-git-worktrees
          source: builtin
          trigger: "工作树隔离"

    # QA cycling: omx/ultraqa is primary
    - scenario: qa_cycling
      primary: omx/ultraqa
      primary_source: omx
      alternatives:
        - skill: gstack/qa
          source: gstack
          trigger: "浏览器测试"
        - skill: gstack/qa-only
          source: gstack
          trigger: "仅报告"
```

## 10. Implementation Phases

### Phase 1: Foundation (Week 1)
- [ ] `core/state/` — Unified state manager
- [ ] `core/optimization/` — Three-layer optimization engine
- [ ] Update `UnifiedRouter` to integrate optimization
- [ ] Add omx/ namespace to `registry.yaml`

### Phase 2: Core omx/ Skills (Week 2)
- [ ] `core/interview/` — deep-interview implementation
- [ ] `core/plan/` — ralplan implementation
- [ ] `core/ralph/` — ralph implementation
- [ ] SKILL.md files for all 3

### Phase 3: Pipeline omx/ Skills (Week 3)
- [ ] `core/team/` — asyncio multi-agent runtime
- [ ] `core/pipeline/` — ultrawork, autopilot, ultraqa
- [ ] SKILL.md files for all 4

### Phase 4: Integration & Testing (Week 4)
- [ ] End-to-end routing tests with 44 skills
- [ ] Prefilter effectiveness tests
- [ ] Preference learning integration tests
- [ ] Cluster conflict resolution tests
- [ ] Performance benchmarks (P95 < 50ms)

## 11. Success Criteria

1. **Routing quality**: 44 skills routed with same or better accuracy as 37 skills
2. **Performance**: P95 routing latency < 50ms (vs current ~16ms)
3. **Candidate reduction**: Pre-filter reduces candidates by 70%+ on average
4. **Preference impact**: User preferences visibly affect routing after 3+ selections
5. **Conflict auto-resolution**: 90% of skill overlaps resolved without manual rules
6. **All 7 omx/ skills**: Functional with real implementations (no stubs)
