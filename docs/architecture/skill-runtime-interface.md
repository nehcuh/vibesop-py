# Skill Runtime Interface (v5.0)

> **Status**: Approved  
> **Date**: 2026-04-21  
> **Scope**: VibeSOP v5.0 — v5.2  skill ecosystem architecture contract  
> **Related**: [v5.x Roadmap](../../docs/version_05.md)

## 1. Overview

This document defines the **Skill Runtime Interface** — the architectural contract between VibeSOP's skill discovery, routing, configuration, and evaluation subsystems. It is produced during v5.0 (Phase 1: Scope + Enablement) to ensure v5.1 (Evaluation + Retention) and v5.2 (Discovery + Community) can evolve without breaking the data model.

**Core principle**: *预埋不启用，启用不返工* (pre-wire without activation; activation without rework).

## 2. Core Concepts

```
┌─────────────────────────────────────────────────────────────────┐
│                        Skill Runtime                             │
├─────────────┬─────────────┬─────────────┬───────────────────────┤
│  Discovery  │   Routing   │   Config    │      Evaluation       │
│  (Loader)   │  (Router)   │  (Manager)  │      (Evaluator)      │
├─────────────┼─────────────┼─────────────┼───────────────────────┤
│ discover_all│   route()   │ get_config  │   evaluate_skill()    │
│  → filter   │  → filter   │  → SkillCfg │   → SkillEvaluation   │
│ by scope    │ by scope    │             │   → RetentionSuggest  │
│ by lifecycle│ by enabled  │             │                       │
└─────────────┴─────────────┴─────────────┴───────────────────────┘
```

## 3. Data Model

### 3.1 SkillConfig (Extended)

The canonical skill configuration struct. **All fields listed here are stable across v5.x.**

```python
@dataclass
class SkillConfig:
    # --- Identity & Control (v5.0 active) ---
    skill_id: str
    enabled: bool = True              # Routing on/off switch
    priority: int = 50                # Routing priority override
    scope: str = "global"             # "global" | "project" | "session"

    # --- Lifecycle (v5.0 pre-wired, v5.1 active) ---
    lifecycle: str = "active"         # "draft" | "active" | "deprecated" | "archived"

    # --- Usage Statistics (v5.0 reserved, v5.1 populated) ---
    usage_stats: dict[str, Any] = field(default_factory=dict)
    # Expected keys (v5.1):
    #   - total_invocations: int
    #   - last_invoked_at: str (ISO timestamp)
    #   - avg_execution_time_ms: float
    #   - failure_count: int
    #   - daily_histogram: dict[str, int]

    # --- Version History (v5.0 reserved, v5.1 populated) ---
    version_history: list[dict[str, Any]] = field(default_factory=list)
    # Expected shape (v5.1):
    #   [{"version": "1.2.0", "updated_at": "...", "changelog": "..."}]

    # --- Evaluation Context (v5.0 reserved, v5.1 populated) ---
    evaluation_context: dict[str, Any] = field(default_factory=dict)
    # Expected keys (v5.1):
    #   - composite_score: float        # 0.0-1.0
    #   - grade: str                    # "A" | "B" | "C" | "D" | "F"
    #   - last_evaluated_at: str
    #   - evaluator_version: str
    #   - dimension_scores: dict[str, float]

    # --- LLM Config (v4.x legacy, stable) ---
    requires_llm: bool = False
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_temperature: float | None = None

    # --- Routing Config (v4.x legacy, stable) ---
    routing_patterns: list[str] | None = None

    # --- Metadata (v4.x legacy, stable) ---
    auto_configured: bool = False
    confidence: float = 0.5
```

**Storage**: `.vibe/skills/auto-config.yaml` (YAML, human-editable).

### 3.2 SkillLifecycleState

```python
class SkillLifecycleState(str, Enum):
    DRAFT      = "draft"       # New skill, not yet validated
    ACTIVE     = "active"      # Normal operation (default)
    DEPRECATED = "deprecated"  # Still routable, but warns user
    ARCHIVED   = "archived"    # Excluded from routing entirely
```

**State transitions** (v5.1 enforcement):
```
DRAFT ──[validate]──► ACTIVE ──[evaluate]──► DEPRECATED ──[retention]──► ARCHIVED
       ▲                │                           │
       │                └──[manual]──► ARCHIVED     └──[improve]──► ACTIVE
       │
       └──[create]
```

**Filtering rules**:
- `SkillLoader.discover_all()`: excludes `ARCHIVED`, excludes `enabled=False`
- `UnifiedRouter._get_candidates()`: double-checks `enabled` + `scope` (defense in depth)
- `UnifiedRouter.route()`: may warn if `DEPRECATED` skill is selected

### 3.3 SkillEvaluation (v5.1 contract)

The output of `RoutingEvaluator.evaluate_skill()`. **5-dimension composite score**.

```python
@dataclass
class SkillEvaluation:
    skill_id: str
    total_routes: int = 0

    # 5 dimensions (weights fixed in v5.1)
    routing_accuracy:  float = 0.0   # 25%  — FeedbackCollector.was_correct
    user_satisfaction: float = 0.0   # 25%  — ExecutionFeedbackCollector.was_helpful
    execution_success: float = 0.0   # 25%  — ExecutionFeedbackCollector.execution_success
    usage_frequency:   float = 0.0   # 15%  — normalized invocation count
    health_score:      float = 0.0   # 10%  — HealthMonitor.check_local_health()

    # Derived
    quality_score: float = property(...)   # weighted composite
    grade: str = property(...)             # "A"-"F" mapping
```

**Grade thresholds** (stable):
| Grade | Score Range | Action |
|-------|-------------|--------|
| A | 90-100 | Highlight as recommended |
| B | 75-89  | Good standing |
| C | 60-74  | Acceptable |
| D | 40-59  | Warn, suggest improvement |
| F | 0-39   | Suggest removal if stale |

### 3.4 RetentionSuggestion (v5.1 contract)

```python
@dataclass
class RetentionSuggestion:
    skill_id: str
    action: str          # "remove" | "warn" | "highlight" | "none"
    reason: str
    grade: str
    days_since_last_use: int | None
    total_uses: int
```

**Policy rules** (advisory only, no automatic removal):
- `action="remove"`: Grade F + 30+ days since use + < 3 total uses
- `action="warn"`: Grade D + 60+ days since use
- `action="highlight"`: Grade A + used within last 7 days

## 4. Interface Contracts

### 4.1 SkillLoader → SkillConfigManager

```python
class SkillLoader:
    def discover_all(self, force_reload: bool = False) -> dict[str, LoadedSkill]:
        """
        Contract:
        1. Discover skills from all search paths.
        2. For each discovered skill, call SkillConfigManager.get_skill_config(skill_id).
        3. Filter OUT if config.enabled == False.
        4. Filter OUT if config.lifecycle == "archived".
        5. Include DEPRECATED skills (warning handled at routing layer).
        6. Cache result; invalidate cache on force_reload.
        """
```

### 4.2 UnifiedRouter → SkillLoader

```python
class UnifiedRouter:
    def _get_candidates(self, _query: str = "") -> list[dict[str, Any]]:
        """
        Contract:
        1. Call SkillLoader.discover_all() (or use cached result).
        2. Attach metadata from SkillConfigManager to each candidate dict:
           - "enabled": bool
           - "scope": str
           - "source_file": str | None
           - "lifecycle": str          # v5.0 pre-wired
        3. Do NOT filter here; filtering happens in route() to allow
           external callers to bypass with custom candidates.
        """

    def route(self, query, candidates=None, context=None) -> RoutingResult:
        """
        Contract:
        1. If candidates is None, load from _get_cached_candidates().
        2. Filter by enabled == False → exclude.
        3. Filter by scope == "project" and source_file outside project_root → exclude.
        4. Execute routing layers (explicit → scenario → ai_triage → matchers).
        5. If selected skill has lifecycle == "deprecated", include warning
           in RoutingResult.metadata["lifecycle_warning"].
        6. Return RoutingResult with full layer_details for transparency.
        """
```

### 4.3 SkillConfigManager → Storage

```python
class SkillConfigManager:
    # --- v5.0 active ---
    @classmethod
    def set_enabled(cls, skill_id: str, enabled: bool) -> None
    @classmethod
    def set_scope(cls, skill_id: str, scope: str) -> None

    # --- v5.0 pre-wired, v5.1 active ---
    @classmethod
    def set_lifecycle(cls, skill_id: str, state: str) -> None
        # Validates state against SkillLifecycleState enum.

    # --- v5.0 reserved, v5.1 active ---
    @classmethod
    def update_usage_stats(cls, skill_id: str, stats_delta: dict[str, Any]) -> None
        # Atomically merges stats_delta into usage_stats.

    @classmethod
    def append_version(cls, skill_id: str, version_record: dict[str, Any]) -> None
        # Appends to version_history list.

    @classmethod
    def update_evaluation_context(cls, skill_id: str, context: dict[str, Any]) -> None
        # Overwrites evaluation_context with new evaluation results.
```

### 4.4 RoutingEvaluator → FeedbackCollectors

```python
class RoutingEvaluator:
    def evaluate_skill(self, skill_id: str) -> SkillEvaluation:
        """
        Contract:
        1. Read routing feedback (FeedbackCollector) for routing_accuracy.
        2. Read execution feedback (ExecutionFeedbackCollector) for
           user_satisfaction and execution_success.
        3. Compute usage_frequency by normalizing against max usage.
        4. Query HealthMonitor for health_score.
        5. Query PreferenceLearner for user preference score.
        6. Return SkillEvaluation with composite quality_score and grade.
        """
```

## 5. Extension Points for v5.1 / v5.2

### 5.1 v5.1: Evaluation + Retention

**No data model changes required** — all fields are pre-wired in v5.0.

Tasks:
- Implement `ExecutionFeedbackCollector` usage tracking
- Populate `SkillConfig.usage_stats` after each skill invocation
- Run `RoutingEvaluator` as a background cron/scheduled task
- Write evaluation results back to `SkillConfig.evaluation_context`
- Trigger `RetentionPolicy.analyze_all()` weekly
- Render retention suggestions in `vibe skills report`

### 5.2 v5.2: Discovery + Community

**Minimal data model changes** — only `version_history` will be actively used.

New additions (not yet in v5.0):
- `SkillRegistry` class for remote skill discovery
- `SkillMarket` class for install/update/share
- `SkillManifest.remote_source` field for registry URL

Migration: `version_history` already has the shape needed for registry sync.

## 6. Backward Compatibility

| Version | Behavior |
|---------|----------|
| v4.x | `lifecycle`, `usage_stats`, `version_history`, `evaluation_context` are ignored. Skills default to `ACTIVE`. No breaking changes. |
| v5.0 | New fields stored in `auto-config.yaml` but mostly empty. `ARCHIVED` skills filtered at discovery time. |
| v5.1 | `usage_stats` and `evaluation_context` populated by runtime. `DEPRECATED` skills show warnings. |
| v5.2 | `version_history` used for registry sync. `SkillMarket` leverages pre-wired metadata. |

## 7. Migration Guide

### From v4.x to v5.0

No action required. Existing `.vibe/skills/auto-config.yaml` will be read normally; missing fields use defaults.

### From v5.0 to v5.1

When `RoutingEvaluator` runs for the first time:
1. Read all skills from `SkillLoader.discover_all()`
2. For each skill, compute `SkillEvaluation`
3. Write `evaluation_context` to `auto-config.yaml`
4. No user-facing migration needed

### Data format evolution

```yaml
# v5.0 auto-config.yaml
skills:
  my-skill:
    enabled: true
    scope: project
    lifecycle: active           # ← new in v5.0
    usage_stats: {}             # ← reserved
    version_history: []         # ← reserved
    evaluation_context: {}      # ← reserved

# v5.1 auto-config.yaml (same file, populated)
skills:
  my-skill:
    enabled: true
    scope: project
    lifecycle: active
    usage_stats:
      total_invocations: 42
      last_invoked_at: "2026-04-21T10:00:00"
      avg_execution_time_ms: 1250.0
    version_history: []
    evaluation_context:
      composite_score: 0.82
      grade: "B"
      last_evaluated_at: "2026-04-21T00:00:00"
      evaluator_version: "1.0"
```

## 8. File Locations

| Component | Path |
|-----------|------|
| SkillConfig + SkillLifecycleState | `src/vibesop/core/skills/config_manager.py` |
| SkillLoader | `src/vibesop/core/skills/loader.py` |
| UnifiedRouter | `src/vibesop/core/routing/unified.py` |
| RoutingEvaluator | `src/vibesop/core/skills/evaluator.py` |
| RetentionPolicy | `src/vibesop/core/skills/retention.py` |
| ExecutionFeedbackCollector | `src/vibesop/core/feedback.py` |
| This Interface Document | `docs/architecture/skill-runtime-interface.md` |

---

*This document is a living contract. Changes must be approved via ADR review and backward-compatible for at least one minor version.*
