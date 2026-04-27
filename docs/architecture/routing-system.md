# Routing System Architecture

> **Version**: 5.2.0
> **Last Updated**: 2026-04-28

## Overview

The routing system is VibeSOP's core component. It takes user queries and returns the most appropriate skill(s) to handle them.

```
Query → UnifiedRouter → 10-Layer Pipeline → RoutingResult
```

## UnifiedRouter

**Location**: `src/vibesop/core/routing/unified.py`

**Purpose**: Single entry point for all routing operations

**Interface**:
```python
class UnifiedRouter:
    def route(
        self,
        query: str,
        candidates: list[dict] | None = None,
        context: RoutingContext | None = None,
    ) -> RoutingResult:
        """Route query to best matching skill."""
```

## 10-Layer Pipeline

Layers are tried in priority order. First match wins (except for alternatives).

> **v4.4.0**: Layers 7 (Custom plugins), 8 (No Match), and 9 (Fallback LLM) added. Keyword routing is bypassed for queries exceeding `keyword_match_max_chars` (default 5), falling directly to AI Triage.

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 0: Explicit Override                                  │
│ • Detects /skill or "use skill" patterns                    │
│ • Latency: <0.1ms                                           │
│ • Use when: User explicitly chooses a skill                 │
├─────────────────────────────────────────────────────────────┤
│ Layer 1: Scenario Patterns                                  │
│ • Predefined situation → skill mappings                     │
│ • Latency: <0.1ms                                           │
│ • Use when: Common scenarios (debug, review, deploy)        │
├─────────────────────────────────────────────────────────────┤
│ Layer 2: AI Triage (LLM)                                    │
│ • Uses LLM for semantic classification                      │
│ • Cost: ~$0.001/call                                        │
│ • Latency: ~100-500ms                                      │
│ • Use when: High-stakes decisions, complex intent           │
├─────────────────────────────────────────────────────────────┤
│ Layer 3: Keyword Matching                                   │
│ • Exact token-based matching                                │
│ • Latency: <0.1ms                                           │
│ • Use when: Direct keyword matches                          │
├─────────────────────────────────────────────────────────────┤
│ Layer 4: TF-IDF Semantic Matching                           │
│ • Cosine similarity on term vectors                         │
│ • Latency: ~5-10ms                                          │
│ • Use when: General queries                                 │
├─────────────────────────────────────────────────────────────┤
│ Layer 5: Embedding-Based Matching                           │
│ • Vector similarity for semantic understanding              │
│ • Latency: ~10-20ms                                         │
│ • Use when: Semantic meaning > exact keywords               │
├─────────────────────────────────────────────────────────────┤
│ Layer 6: Fuzzy Fallback (Levenshtein)                       │
│ • Edit distance for typos and misspellings                  │
│ • Latency: ~10-20ms                                         │
│ • Use when: No matches in upper layers                      │
├─────────────────────────────────────────────────────────────┤
│ Layer 7: Custom Matcher Plugins                             │
│ • User-defined matchers in .vibe/matchers/                  │
│ • Latency: varies                                           │
│ • Use when: Specialized matching logic needed               │
├─────────────────────────────────────────────────────────────┤
│ Layer 8: No Match                                           │
│ • All layers failed to find a confident match               │
│ • Latency: N/A                                              │
│ • Use when: Query doesn't match any skill                   │
├─────────────────────────────────────────────────────────────┤
│ Layer 9: Fallback LLM                                       │
│ • Raw LLM fallback when no skill matches                    │
│ • Configurable: transparent / silent / disabled             │
│ • Use when: Last-resort routing for unmatched queries       │
└─────────────────────────────────────────────────────────────┘
```

## Layer Details

### Layer 0: Explicit Override

**Implementation**: `check_explicit_override()` in `explicit_layer.py`

**Patterns Detected**:
- `/review` → `gstack/review`
- `use tdd` → `superpowers/tdd`
- `调用 debug` → `systematic-debugging`

**Returns**: confidence=1.0 (user's explicit choice)

### Layer 1: Scenario Patterns

**Implementation**: `match_scenario()` in `scenario_layer.py`

**Loaded From**: `core/registry.yaml`

**Example Scenarios**:
```yaml
scenarios:
  - trigger: "test failure"
    primary: "systematic-debugging"
    alternatives:
      - skill: "gstack/investigate"
```

**Returns**: confidence=0.8

### Layer 2: AI Triage

**Implementation**: `_ai_triage()` method

**Flow**:
1. Check if enabled (`enable_ai_triage` config)
2. Build prompt with top 20 candidates
3. Call LLM (Haiku or GPT)
4. Validate response is a valid skill_id
5. Return with confidence=0.95

**When to Enable**:
- High-stakes routing decisions
- Complex, multi-part queries
- When accuracy > latency

**When to Disable**:
- CLI usage (latency matters)
- Cost-sensitive environments
- Simple queries

### Layer 3: Keyword Matching

**Implementation**: `KeywordMatcher`

**Flow**:
1. **Prefilter**: Exclude irrelevant namespaces
2. **Exact Match**: Direct token matching
3. **Confidence Threshold**: Default 0.6 (configurable)

**Performance**:
- P50: 0.03ms
- P95: 0.05ms

### Layer 4: TF-IDF Semantic Matching

**Implementation**: `TFIDFMatcher`

**Flow**:
1. **Vectorize**: Convert query and candidates to TF-IDF vectors
2. **Similarity**: Cosine similarity computation
3. **Confidence Threshold**: Default 0.6 (configurable)

**Performance**:
- P50: 6.0ms
- P95: 7.0ms (with cache)

### Layer 5: Embedding-Based Matching

**Implementation**: `EmbeddingMatcher` (optional)

**Flow**:
1. **Encode**: Convert query to vector embedding
2. **Similarity**: Vector similarity computation
3. **Confidence Threshold**: Default 0.6 (configurable)

**Use When**:
- Semantic understanding needed
- Cross-language queries
- Concept-based matching

### Layer 6: Fuzzy Fallback

**Implementation**: `LevenshteinMatcher`

**Algorithm**: Levenshtein distance with normalized threshold

**Use Case**: Typos and misspellings
- "reviwe code" → `gstack/review`
- "dubug" → `systematic-debugging`

## Optimization Layer

After the 10-layer matching pipeline, optimization is applied:

### Preference Boost

**Location**: `core/routing/optimization_service.py`

**Purpose**: Learn from user's past choices

**Factors**:
- **Consistency** (40%): How often user chooses same skill
- **Satisfaction** (30%): Implicit feedback
- **Context** (20%): Working directory, file types
- **Recency** (10%): Recent choices weighted more

**Formula**:
```
boosted_confidence = base_confidence × (1 + preference_weight × score)
```

### Session Stickiness (v4.2.1+)

**Location**: `core/routing/optimization_service.py:_apply_session_stickiness()`

**Purpose**: Maintain continuity across multi-turn conversations

- Default boost: `0.03` (configurable `0.0–0.2`)
- Applied when `routing.session_aware: true`
- Disabled with `--no-session` CLI flag

### Quality Boost (v4.2.1+)

**Location**: `core/routing/optimization_service.py:_apply_quality_boost()`

**Purpose**: Promote well-performing skills, demote poor ones

| Grade | Adjustment | Condition |
|-------|-----------|-----------|
| A | +0.05 | `total_routes >= 3` |
| B | +0.02 | `total_routes >= 3` |
| C | 0 | `total_routes >= 3` |
| D | -0.02 | `total_routes >= 3` |
| F | -0.05 | `total_routes >= 3` |

> **Protection**: Only applies when `total_routes >= 3` to avoid early misjudgment.
> Disable with `routing.enable_quality_boost: false`.

### Habit Boost (v4.2.1+)

**Location**: `core/sessions/context.py:get_habit_boost()`

**Purpose**: Recognize repeated query patterns and reinforce them

- Pattern forms after **3 repetitions** of the same query → skill mapping
- Boost: `0.08` confidence increase
- Patterns tracked in last 50 route decisions
- Embedding-based semantic similarity for pattern matching

### Candidate Prefilter

**Purpose**: Reduce search space before matching

**Strategy**:
- Priority filtering (P0 skills always included)
- Namespace filtering (exclude unless mentioned)
- Intent clustering (only include relevant clusters)

## Caching Strategy

**Candidate Cache**:
- Loaded on first `route()` call
- Thread-safe (double-checked locking)
- Invalidated by `reload_candidates()`

**Result Cache**:
- AI Triage results cached for 1 hour
- File-based in `.vibe/cache/`
- Reduces LLM costs

## Performance

| Layer | P50 Latency | P95 Latency | Hit Rate |
|-------|-------------|-------------|----------|
| AI Triage | 100ms | 500ms | 0% (optional) |
| Explicit | 0.03ms | 0.05ms | ~20% |
| Scenario | 0.03ms | 0.05ms | ~28% |
| Keyword | 0.06ms | 0.07ms | ~72% |
| TF-IDF | 6.0ms | 7.0ms | ~72% |
| Fuzzy | 10ms | 15ms | <5% |

**Overall P95**: <1ms (without AI Triage)

## Routing Result

```python
@dataclass
class RoutingResult:
    primary: SkillRoute | None    # Best match
    alternatives: list[SkillRoute]  # Other options
    routing_path: list[RoutingLayer]  # Layers tried
    query: str                     # Original query
    duration_ms: float             # Routing time

@dataclass
class SkillRoute:
    skill_id: str
    confidence: float              # 0.0-1.0
    layer: RoutingLayer            # Which layer matched
    source: str                    # Where skill was found
    description: str               # Skill description for CLI display (v4.2.1+)
    metadata: dict                 # Additional info
```

## Configuration

**Key Config Options**:
```yaml
routing:
  enable_ai_triage: false        # Enable Layer 2
  min_confidence: 0.6            # Minimum for match
  max_candidates: 3              # Alternatives to return
  use_cache: true                # Enable caching
  session_aware: true            # Enable session-state-aware routing
  session_stickiness_boost: 0.03 # Continuity boost (0.0–0.2)
  fallback_mode: transparent     # transparent / silent / disabled
  enable_quality_boost: true     # Grade-based confidence adjustment
  keyword_match_max_chars: 5     # Max chars for keyword routing (0=always LLM, 200=always keyword)
```

## Degradation System (v5.2.0)

After a skill match is found, the `DegradationManager` evaluates confidence and applies a 4-level degradation:

| Level | Confidence Range | Behavior |
|-------|-----------------|----------|
| **AUTO** | >= 0.6 (configurable) | Auto-select, no user prompt |
| **SUGGEST** | >= 0.4 | Show primary + alternatives for user confirmation |
| **DEGRADE** | >= 0.2 | Use matched skill but warn about low confidence |
| **FALLBACK** | < 0.2 | Drop match entirely, use raw LLM fallback |

**Configuration**:
```yaml
routing:
  degradation_enabled: true
  degradation_auto_threshold: 0.6
  degradation_suggest_threshold: 0.4
  degradation_degrade_threshold: 0.2
  degradation_fallback_always_ask: true  # Ask user before fallback
```

Explicit user-specified skills (Layer 0 EXPLICIT, Layer 7 CUSTOM) bypass degradation.

**Implementation**: `src/vibesop/core/routing/degradation.py`


## Skill Recommendation & Discovery (v5.2.0)

The `SkillRecommender` enriches routing results with two strategies:

### Recommendation
After a primary match, scores all installed skills by intent keyword overlap (40%), trigger matching (30%), priority (20%), and namespace diversity (10%). Top matches are injected as `[RECOMMENDED]` alternatives.

### Proactive Discovery
Scores all skills but **penalizes already-used skills** (×0.2 weight), favoring undiscovered skills matching the current query domain. These appear as `[DISCOVER]` alternatives.

**Implementation**: `src/vibesop/integrations/skill_recommender.py`

**Scoring dimensions**:
- Intent keyword overlap: 40% (via `INTENT_DOMAIN_KEYWORDS`)
- Trigger keyword match: 30% (from skill's `triggers` field)
- Priority bonus: 20% (P0=1.0, P1=0.7, P2=0.4)
- Namespace diversity: 10% (avoid same-namespace crowding)

## Extending the Router

### Adding a New Layer

1. Implement detection logic
2. Return `SkillRoute` or `None`
3. Add to pipeline in `route()` method
4. Update `RoutingLayer` enum

### Adding a New Matcher

1. Implement `IMatcher` interface
2. Register in `UnifiedRouter.__init__()`
3. Add configuration option

---

*For system overview, see [overview.md](overview.md)*
*For layer details, see [three-layers.md](three-layers.md)*
