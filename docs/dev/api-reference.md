# API Reference

This document provides detailed API documentation for VibeSOP's core routing and skill-loading components.

---

## UnifiedRouter

**Module:** `vibesop.core.routing.unified`

The `UnifiedRouter` is the single entry point for all skill routing. It executes a cascading pipeline of matching layers and returns the best-matching skill for a given user query.

### Constructor

```python
class UnifiedRouter:
    def __init__(
        self,
        project_root: str | Path = ".",
        config: RoutingConfig | ConfigManager | None = None,
    ) -> None
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `project_root` | `str \| Path` | `"."` | Project root directory. Used to resolve `.vibe/` configuration and local skills. |
| `config` | `RoutingConfig \| ConfigManager \| None` | `None` | Routing configuration. If `None`, loads from `project_root`. If `ConfigManager`, uses it directly. If `RoutingConfig`, wraps it in a `ConfigManager`. |

### Primary Method: `route()`

```python
def route(
    self,
    query: str,
    candidates: list[dict[str, Any]] | None = None,
    context: RoutingContext | None = None,
) -> RoutingResult
```

Routes a query through the layer pipeline and returns the best match.

**Args:**
- `query` — The user's natural-language query.
- `candidates` — Optional override list of skill candidates. If omitted, candidates are discovered automatically.
- `context` — Optional routing context (conversation history, recent queries, etc.).

**Returns:** `RoutingResult` containing the primary match, alternatives, routing path, and timing.

**Example:**

```python
from vibesop.core.routing import UnifiedRouter

router = UnifiedRouter(project_root=".")
result = router.route("帮我调试这个 bug")

if result.has_match:
    print(result.primary.skill_id)      # "systematic-debugging"
    print(result.primary.confidence)    # 0.9
    print(result.primary.layer.value)   # "scenario"
```

### Routing Layers

The router executes layers in the following priority order. The first layer that produces a confident match wins.

| Order | Layer | Mechanism | Confidence |
|-------|-------|-----------|------------|
| 0 | `EXPLICIT` | Slash commands (`/review`) and override patterns | 1.0 |
| 1 | `SCENARIO` | Predefined scenario keyword mappings from `core/registry.yaml` | 0.9 |
| 2 | `AI_TRIAGE` | LLM-based semantic triage (optional, cost-controlled) | Varies |
| 3 | `KEYWORD` | Token-based keyword matching with CJK support | Varies |
| 4 | `TFIDF` | TF-IDF cosine similarity across candidate corpus | Varies |
| 5 | `EMBEDDING` | Sentence-transformer embeddings (optional) | Varies |
| 6 | `LEVENSHTEIN` | Fuzzy matching for typos and near-matches | Varies |

### Utility Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `score()` | `score(query, skill_id, candidate, context=None) -> float` | Score a specific candidate against a query using the matcher pipeline. |
| `get_candidates()` | `get_candidates(query="") -> list[dict]` | Discover and return all available skill candidates. |
| `reload_candidates()` | `reload_candidates() -> int` | Clear the candidate cache and rediscover skills. Returns the new candidate count. |
| `get_stats()` | `get_stats() -> dict[str, Any]` | Return routing statistics including layer distribution. |

---

## MatcherPipeline

**Module:** `vibesop.core.routing.matcher_pipeline`

The `MatcherPipeline` executes matchers for routing layers 3–6 (keyword, TF-IDF, embedding, levenshtein). It aggregates scores across all matchers and applies optimizations.

### Constructor

```python
class MatcherPipeline:
    def __init__(
        self,
        matchers: list[tuple[RoutingLayer, IMatcher]],
        config: RoutingConfig,
        optimization_config: OptimizationConfig,
        prefilter: CandidatePrefilter,
        optimization_service: OptimizationService,
        get_skill_source: Callable[[str, str], str],
    ) -> None
```

### Primary Method: `try_matcher_pipeline()`

```python
def try_matcher_pipeline(
    self,
    query: str,
    candidates: list[dict[str, Any]],
    context: RoutingContext | None,
) -> LayerResult | None
```

Runs all matchers, aggregates scores per candidate (taking the maximum confidence across matchers), and returns the best match after applying optimizations.

**Score Aggregation Behavior:**
- Each matcher produces its own confidence scores.
- For each candidate, the pipeline keeps the **maximum** confidence across all matchers.
- This prevents a weak keyword match from blocking a strong TF-IDF match.

**Example:**

```python
from vibesop.core.routing.matcher_pipeline import MatcherPipeline

pipeline = MatcherPipeline(
    matchers=router._matchers,
    config=router._config,
    optimization_config=router._optimization_config,
    prefilter=router._prefilter,
    optimization_service=router._optimization_service,
    get_skill_source=router._get_skill_source,
)

result = pipeline.try_matcher_pipeline("debug error", candidates, context)
```

---

## SkillLoader

**Module:** `vibesop.core.skills.loader`

The `SkillLoader` discovers and loads skills from the filesystem. It supports markdown files with YAML frontmatter (`SKILL.md`), YAML files, and Python modules.

### Constructor

```python
class SkillLoader:
    def __init__(
        self,
        project_root: str | Path = ".",
        search_paths: Sequence[str | Path] | None = None,
        enable_external: bool = True,
        require_audit: bool = True,
    ) -> None
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `project_root` | `str \| Path` | `"."` | Project root directory. |
| `search_paths` | `Sequence[str \| Path] \| None` | `None` | Additional paths to search for skills. |
| `enable_external` | `bool` | `True` | Whether to load external skills from `~/.claude/skills/` and `~/.config/skills/`. |
| `require_audit` | `bool` | `True` | Whether to require security audit for external skills. |

### Primary Method: `discover_all()`

```python
def discover_all(self, force_reload: bool = False) -> dict[str, LoadedSkill]
```

Discovers all available skills and returns a mapping of skill ID → `LoadedSkill`.

**Search Order:**
1. `{project_root}/skills/`
2. `{project_root}/.vibe/skills/`
3. Additional `search_paths`
4. External packs (`~/.claude/skills/`, `~/.config/skills/`) — if `enable_external=True`

Earlier paths take precedence. A skill discovered in step 1 will not be overwritten by the same skill ID in step 4.

### Primary Method: `get_skill()`

```python
def get_skill(self, skill_id: str) -> LoadedSkill | None
```

Returns a single skill by ID, or `None` if not found.

### Example

```python
from vibesop.core.skills import SkillLoader

loader = SkillLoader(project_root=".")
skills = loader.discover_all()

for skill_id, definition in skills.items():
    print(f"{skill_id}: {definition.metadata.name}")
    print(f"  tags: {definition.metadata.tags}")
    print(f"  intent: {definition.metadata.intent}")
```

---

## MatchResult

**Module:** `vibesop.core.matching.base`

Represents the result of a single matcher execution.

```python
@dataclass
class MatchResult:
    skill_id: str
    confidence: float
    score_breakdown: dict[str, float]
    matcher_type: MatcherType
    matched_keywords: list[str]
    metadata: dict[str, Any]
```

| Field | Type | Description |
|-------|------|-------------|
| `skill_id` | `str` | The matched skill identifier. |
| `confidence` | `float` | Overall confidence score (0.0–1.0). |
| `score_breakdown` | `dict[str, float]` | Per-metric scores (e.g., `{"keyword_match": 0.85}`). |
| `matcher_type` | `MatcherType` | Which matcher produced this result. |
| `matched_keywords` | `list[str]` | Keywords that triggered the match. |
| `metadata` | `dict[str, Any]` | Additional matcher-specific metadata. |

---

## RoutingResult

**Module:** `vibesop.core.models`

The final output of the routing process.

```python
@dataclass
class RoutingResult:
    primary: SkillRoute | None
    alternatives: list[SkillRoute]
    routing_path: list[RoutingLayer]
    query: str
    duration_ms: float
```

| Field | Type | Description |
|-------|------|-------------|
| `primary` | `SkillRoute \| None` | The best-matching skill, or `None` if no match. |
| `alternatives` | `list[SkillRoute]` | Other skills that were considered. |
| `routing_path` | `list[RoutingLayer]` | Ordered list of layers that were evaluated. |
| `query` | `str` | The original query string. |
| `duration_ms` | `float` | Total routing time in milliseconds. |

### Property: `has_match`

```python
@property
def has_match(self) -> bool
```

Returns `True` if `primary` is not `None`.

---

## SkillRoute

**Module:** `vibesop.core.models`

Represents a single routed skill selection.

```python
@dataclass
class SkillRoute:
    skill_id: str
    confidence: float
    layer: RoutingLayer
    source: str
    metadata: dict[str, Any]
```

| Field | Type | Description |
|-------|------|-------------|
| `skill_id` | `str` | The skill identifier. |
| `confidence` | `float` | Match confidence (0.0–1.0). |
| `layer` | `RoutingLayer` | Which routing layer produced this match. |
| `source` | `str` | Skill source (`builtin`, `project`, `external`). |
| `metadata` | `dict[str, Any]` | Extra context (e.g., scenario name, override flag). |

---

## Configuration Classes

### RoutingConfig

**Module:** `vibesop.core.config`

```python
class RoutingConfig(BaseModel):
    min_confidence: float = 0.3
    auto_select_threshold: float = 0.6
    enable_ai_triage: bool = True
    enable_embedding: bool = False
    max_candidates: int = 3
    use_cache: bool = True
    ai_triage_budget_monthly: float = 5.0
    ai_triage_circuit_breaker_enabled: bool = True
    ai_triage_circuit_breaker_failure_threshold: int = 3
    ai_triage_circuit_breaker_latency_ms: float = 500.0
    ai_triage_circuit_breaker_cooldown_seconds: float = 60.0
```

---

## Type Stability Notes

- All public methods are fully type-annotated.
- `RoutingContext` accepts optional `conversation_id` and `recent_queries` for context-aware routing.
- The `candidates` parameter in `route()` accepts a list of dictionaries with keys: `id`, `name`, `description`, `intent`, `keywords`, `triggers`, `namespace`, `priority`.
