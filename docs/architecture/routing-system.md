# Routing System Architecture

> **Version**: 4.0.0
> **Last Updated**: 2026-04-06

## Overview

The routing system is VibeSOP's core component. It takes user queries and returns the most appropriate skill(s) to handle them.

```
Query → UnifiedRouter → 7-Layer Pipeline → RoutingResult
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

## 7-Layer Pipeline

Layers are tried in priority order. First match wins (except for alternatives).

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
│ Layer 2: AI Triage (Optional)                               │
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
│ Layer 6: Fuzzy Fallback                                     │
│ • Levenshtein distance for typos                            │
│ • Latency: ~10-20ms                                         │
│ • Use when: No matches in upper layers                      │
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

After the 7-layer matching pipeline, optimization is applied:

### Preference Boost

**Location**: `core/optimization/`

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
    metadata: dict                 # Additional info
```

## Configuration

**Key Config Options**:
```yaml
routing:
  enable_ai_triage: false        # Enable Layer 0
  min_confidence: 0.6            # Minimum for match
  max_candidates: 3              # Alternatives to return
  use_cache: true                # Enable caching
```

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
