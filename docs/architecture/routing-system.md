# Routing System Architecture

> **Version**: 8.1.3
> **Last Updated**: 2026-09-02
>
> 对外「技能路由是什么、实验说明了什么」见 **[给 AI 找对说明书](../skill-routing-explained.md)**。  
> 本文只保留实现：级联、置信度、代码入口。不要用本文当产品宣传稿。

## Overview

The routing system is VibeSOP's core component. It takes user queries and returns the most appropriate skill(s) to handle them.

```
Query → UnifiedRouter → 4-Stage Cascade → RoutingResult
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

## 4-Stage Routing Cascade

> **Redesigned in v8.0**: the routing model is a **4-stage branched cascade**,
> not the serial 10-layer pipeline of v4. `RoutingLayer.SEMANTIC_INDEX` (Stage 2)
> was split out from `AI_TRIAGE` so the Skill Semantic Index is no longer
> mislabeled. The `Layer N` headings in **Layer Details** below are now
> per-mechanism reference, not strict execution order. See `_try_layers()` in
> `unified.py` for the real control flow.

Stages are branched by query length (≤ ~15 chars → keyword/short path, else
LLM path), not a flat priority loop:

| Stage | Mechanism | Notes |
|-------|-----------|-------|
| 1. Explicit Override | exact skill ID (`/skill`, `use skill`) | short-circuits on hit |
| 2. Scenario + Semantic Index | predefined scenario patterns + Skill Semantic Index (token-overlap + embedding), best-of-N | the short-query path; `SEMANTIC_INDEX` enum |
| 3. AI Triage | LLM semantic classification | the long-query path; `AI_TRIAGE` enum |
| 4. Matcher Aggregation | keyword + TF-IDF + embedding + Levenshtein run **in parallel**; highest confidence wins (not serial fallback) | + custom plugins |

**Terminal states** (not routing layers): **No Match** (all candidates below
the minimum confidence threshold), **Fallback LLM** (last-resort raw LLM).

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

### Semantic Index Layer (Stage 2) — Acceptance Gates (M9)

**Implementation**: `try_index_layer()` / `_try_embedding_fallback()` in `_layers.py`

The index layer matches against LLM-generated skill profiles (token bigram
overlap first, embedding cosine as fallback). Because profile catalogs are
large and pack-generated, a match must clear ALL of these gates, in order:

1. **Installed-only ranking** — profiles for uninstalled skills never compete
   (a stale winner would otherwise dead-end the layer).
2. **Trusted token bar** (`index_match_threshold`, 0.20) — builtin/project/
   custom/cross-cutting namespaces.
3. **External token bar** (`index_external_match_threshold`, 0.30) — pack
   profiles are LLM-generated dozens at a time with overlapping vocabulary,
   so marginal overlap with them is weaker evidence.
4. **Embedding floor** (`index_embedding_threshold`, 0.45) — absolute cosine
   floor, just above the model's noise band for unrelated pairs.
5. **Margin gate** (`index_embedding_min_margin`, 0.05) — top-1 must beat
   top-2 by a clear gap; argmax over a big catalog otherwise always accepts
   noise. Deliberately namespace-blind: abstaining defers to AI triage,
   which is the intended escalation for ambiguous semantic matches.
6. **Guarded-skill signal** — guarded skills (session-end, riper-workflow)
   additionally need an explicit user-intent signal.

**Pack-vs-trusted arbitration (M10)**: separate from the per-match gates
above, the embedding fallback arbitrates between namespaces: an external
pack winner is accepted only when no trusted-namespace profile reaches
`index_external_trusted_floor` (0.35, just above the model's noise band).
A trusted profile above the floor means the query has trusted-catalog
content and the pack win is crowd-out — the layer abstains to AI triage.
Below the floor, the query simply isn't about anything curated and a clear
pack win is legitimately routable (this is what keeps e.g. git-workflow
pack skills reachable for genuine git queries).

**Design story**: the cheap layers stay strict on weak evidence and defer to
AI triage (or a clean no-match) instead of accepting marginal hits. This
trades a little recall for a large precision win on machines with many
installed packs (M9: 67→76/107 on routing_eval_extended, zero regressions).

### Layer 3: Keyword Matching

**Implementation**: `KeywordMatcher`

**Flow**:
1. **Prefilter**: Exclude irrelevant namespaces
2. **Exact Match**: Direct token matching
3. **Confidence Threshold**: Default 0.6 (configurable)

**Evidence-based scoring (M11)**: once warmed with the candidate pool,
`KeywordMatcher` scores with evidence gating instead of purely additive
bonuses — see `core/matching/idf.py` and the calibration record in
`.omx/artifacts/m11-design-a.md`:

- **IDF-weighted coverage gate**: additive bonuses (partial + name/keyword
  hits) are scaled by `g = min(1, cov / keyword_coverage_ref)`, where `cov`
  is the pool-IDF-weighted share of meaningful query tokens that hit the
  candidate. Generic tokens ("review", "design", "workflow") contribute
  almost nothing; a long query with 1-2 incidental hits can no longer reach
  0.9.
- **Anchor gate**: without an anchor — a non-stopword, high-specificity
  (`w ≥ keyword_anchor_idf_min`) query token with exact/name/keyword
  evidence — the score is capped at `keyword_anchor_cap` (0.25, below the
  matcher floor). English function words (`ANCHOR_STOPWORDS` in
  `core/matching/idf.py`) contribute no bonus/coverage/anchor evidence at
  all: in a skill-catalog corpus, words like "get"/"not" are *rare* (high
  IDF) yet semantically empty. (They still count in the Jaccard `base_score`
  and whole-name containment — bounded inputs that cannot lift a score past
  the anchorless cap; do not raise `keyword_anchor_cap` above the matcher
  floor without revisiting this.) Note the gate gets STRICTER on small pools
  (normalized IDF weights compress as N shrinks, so fewer tokens clear the
  bar) — small-pool deployments should lower `keyword_anchor_idf_min`
  (see its config field description).
- **Multi-anchor exemption**: ≥2 anchors in the curated name/keywords
  fields plus non-trivial coverage saturate the gate, keeping genuine
  focused queries routable even when verbose.
- **Name bonus guard**: the 0.4 name bonus now requires a multi-token name
  or a distinctive single-token name (`w ≥ keyword_name_idf_min`).
- **Per-token-best partial**: each query token contributes only its best
  prefix/substring hit, not one per candidate token.

The same anchor definition gates `TFIDFMatcher` results
(`tfidf_anchor_gate_enabled`). All knobs live in `RoutingConfig` with
calibration notes in their field descriptions.

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

After the 4-stage cascade, optimization is applied:

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
  index_match_threshold: 0.20    # SEMANTIC_INDEX token bar, curated namespaces
  index_external_match_threshold: 0.30  # Token bar for external pack profiles
  index_embedding_threshold: 0.45       # Embedding-fallback cosine floor
  index_embedding_min_margin: 0.05      # Embedding top1-top2 gap (0 disables)
  index_external_trusted_floor: 0.35    # Pack-vs-trusted arbitration floor (0 disables)
```

## Degradation System (v5.2.0+)

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


## Skill Recommendation & Discovery (v5.2.0+)

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

## Interception Modes (v7.0)

Before the cascade runs, `IntentInterceptor.should_intercept()`
decides *whether* to route and *how*. The decision tree below is the
single entry point for both the CLI (`vibe route`) and the hook path
(`vibesop-route.sh` → `AgentRuntime.handle_query_for_hook`).

### 5 InterceptionModes

| Mode | When | Output |
|:---|:---|:---|
| `SLASH_COMMAND` | Query starts with `/vibe-*` | Built-in slash execution |
| `SINGLE` | Explicit skill override (`use gstack/review`) **or** short focused query | `router.route()` → primary skill |
| `SINGLE_AGENT` | Single complex role in short query (e.g. architect, red_team) | Route + role prompt + per-agent skill allowlist |
| `MULTI_AGENT_SQUAD` | ≥ 2 distinct professional roles detected | Per-role squad steps (see [Squad Decision Tree](#squad-decision-tree)) |
| `ORCHESTRATE` | Multi-intent markers (`然后`/`最后`/`and then`) without multi-role | Decompose + PlanBuilder sequential/parallel plan |

### Squad Decision Tree

```
                   ┌─────────────────────────────────┐
                   │ IntentInterceptor.should_intercept │
                   └─────────────┬───────────────────┘
                                 │
       ┌─────────────────────────┼──────────────────────────┐
       │                         │                          │
   /vibe-*                  query ≥ 10 chars           < 10 chars
       │                         │                          │
       ▼                         ▼                          ▼
  SLASH_COMMAND      ┌────────────────────┐         no_route (passthrough)
                     │ 1. extract_explicit_skill (ASCII-only)
                     │    + _detect_roles  │
                     └────────┬───────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
        ≥ 2 roles        1 role +        multi-intent
        detected         multi_intent       markers only
              │           marker            │
              ▼               │             ▼
       MULTI_AGENT_SQUAD      │        ORCHESTRATE
                              ▼
                          SINGLE_AGENT (if role ∈ {architect, red_team})
                          or SINGLE
```

### Role Keyword Fast Path

`IntentInterceptor.ROLE_KEYWORDS` is a static dictionary mapping 6
professional roles (architect / implementer / reviewer / tester /
red_team / debater) to Chinese + English keyword tuples. ≥ 2 distinct
roles in the query short-circuit to `MULTI_AGENT_SQUAD` without
consulting the LLM. The fast path covers ≥ 80% of real squad-worthy
queries observed in container e2e tests.

When the fast path doesn't fire (single role or no role detected),
queries longer than 50 chars fall through to
`SemanticIntentAnalyzer.analyze()`, which uses an LLM when configured
or a heuristic facet detector otherwise.

### Orchestrate → Squad Bridge

`Orchestrator.orchestrate` (the path used by both CLI and hook)
reads `context.metadata["intent_analysis"]` and, when
`_interception_mode == "multi_agent_squad"`, forces the workflow
pattern to `AGENT_SQUAD` / `DEBATE` / `RED_TEAM` regardless of what
the rule classifier would otherwise pick. This bridges the
IntentInterceptor's commitment with PlanBuilder's `_build_squad_steps`
branch.

### Hook Path Parity (v7.0 fix)

Before v7.0, `AgentRuntime.handle_query` only handled
`InterceptionMode.ORCHESTRATE`; `MULTI_AGENT_SQUAD` silently fell
through to single-route, dropping the analysis. v7.0 unifies both
modes through the same orchestrate path so the hook JSON matches the
CLI output.

---

*For system overview, see [overview.md](overview.md)*
*For layer details, see [three-layers.md](three-layers.md)*
