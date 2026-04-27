# VibeSOP v5.2 Gap Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the four critical gaps identified in the v5.x roadmap audit: layered degradation, fallback configurability, per-skill recommendation, and market install flow.

**Architecture:** Three independent subsystems — DegradationManager (confidence-gated fallback), SkillRecommender (pattern-based discovery), and MarketInstaller (crawler-to-install bridge). Each can be built and tested in isolation.

**Tech Stack:** Python 3.12, Pydantic v2, Rich (CLI), ruamel.yaml (config)

---

## File Structure

```
New:
  src/vibesop/core/routing/degradation.py          # DegradationManager + DegradationLevel
  src/vibesop/integrations/skill_recommender.py     # Per-skill recommendation engine
  tests/core/routing/test_degradation.py            # Degradation unit tests
  tests/integrations/test_skill_recommender.py      # Recommender unit tests

Modify:
  src/vibesop/core/config/manager.py                # Add degradation thresholds, fallback config
  src/vibesop/core/routing/unified.py               # Integrate DegradationManager
  src/vibesop/core/models.py                        # Add DegradationLevel enum
  src/vibesop/core/orchestration/patterns.py        # Add intent-domain weighted keywords
  src/vibesop/cli/commands/market_cmd.py            # Add 'vibe market install' command
  src/vibesop/market/crawler.py                     # Add SkillRepo.to_install_source()
  src/vibesop/installer/pack_installer.py           # Accept SkillRepo as install source
  src/vibesop/cli/main.py                           # Show degradation info in output
```

---

### Task 1: DegradationLevel Enum and Config

**Files:**
- Modify: `src/vibesop/core/models.py:27-44`
- Modify: `src/vibesop/core/config/manager.py:117-185`
- Modify: `src/vibesop/core/config/manager.py:238-268`

- [ ] **Step 1: Add DegradationLevel enum to models.py**

```python
# Add after RoutingLayer enum in src/vibesop/core/models.py

class DegradationLevel(StrEnum):
    """Confidence-gated degradation levels for skill routing fallback.

    Replaces binary fallback (match/no-match) with layered degradation:
    - AUTO: high confidence, auto-select
    - SUGGEST: moderate confidence, show with alternatives
    - DEGRADE: low confidence, use skill but warn
    - FALLBACK: below threshold, raw LLM
    """

    AUTO = "auto"          # confidence >= 0.6, auto-select
    SUGGEST = "suggest"    # 0.4 <= confidence < 0.6, show + suggest alternatives
    DEGRADE = "degrade"    # 0.2 <= confidence < 0.4, use but warn
    FALLBACK = "fallback"  # confidence < 0.2, raw LLM
```

- [ ] **Step 2: Run test to verify enum works**

Run: `uv run python -c "from vibesop.core.models import DegradationLevel; print(list(DegradationLevel))"`
Expected: `[<DegradationLevel.AUTO: 'auto'>, <DegradationLevel.SUGGEST: 'suggest'>, <DegradationLevel.DEGRADE: 'degrade'>, <DegradationLevel.FALLBACK: 'fallback'>]`

- [ ] **Step 3: Add degradation config fields to RoutingConfig**

```python
# In src/vibesop/core/config/manager.py, add after fallback_mode field (line ~181)

    degradation_enabled: bool = Field(
        default=True,
        description="Enable confidence-gated layered degradation instead of binary fallback",
    )
    degradation_auto_threshold: float = Field(
        default=0.6, ge=0.0, le=1.0,
        description="Confidence threshold for auto-selection (>= this = auto)",
    )
    degradation_suggest_threshold: float = Field(
        default=0.4, ge=0.0, le=1.0,
        description="Confidence threshold for suggest mode (>= this but < auto = suggest)",
    )
    degradation_degrade_threshold: float = Field(
        default=0.2, ge=0.0, le=1.0,
        description="Confidence threshold for degrade mode (>= this but < suggest = degrade)",
    )
    degradation_fallback_always_ask: bool = Field(
        default=True,
        description="When in fallback mode, ask user before proceeding with raw LLM",
    )
```

- [ ] **Step 4: Add degradation defaults to DEFAULT_CONFIG**

```python
# In src/vibesop/core/config/manager.py, add to DEFAULT_CONFIG["routing"]:

            "degradation_enabled": True,
            "degradation_auto_threshold": 0.6,
            "degradation_suggest_threshold": 0.4,
            "degradation_degrade_threshold": 0.2,
            "degradation_fallback_always_ask": True,
```

- [ ] **Step 5: Run type check**

Run: `uv run python -c "from vibesop.core.config.manager import ConfigManager; c = ConfigManager(); r = c.get_routing_config(); print(r.degradation_enabled, r.degradation_fallback_always_ask)"`
Expected: `True True`

- [ ] **Step 6: Commit**

```bash
git add src/vibesop/core/models.py src/vibesop/core/config/manager.py
git commit -m "feat: add DegradationLevel enum and degradation routing config"
```

---

### Task 2: DegradationManager Implementation

**Files:**
- Create: `src/vibesop/core/routing/degradation.py`
- Create: `tests/core/routing/test_degradation.py`

- [ ] **Step 1: Write failing tests for DegradationManager**

```python
# tests/core/routing/test_degradation.py

import pytest
from vibesop.core.models import DegradationLevel, SkillRoute, RoutingLayer
from vibesop.core.routing.degradation import DegradationManager


class FakeConfig:
    degradation_enabled = True
    degradation_auto_threshold = 0.6
    degradation_suggest_threshold = 0.4
    degradation_degrade_threshold = 0.2
    degradation_fallback_always_ask = True
    fallback_mode = "transparent"
    min_confidence = 0.3


def make_route(skill_id: str, confidence: float) -> SkillRoute:
    return SkillRoute(
        skill_id=skill_id,
        confidence=confidence,
        layer=RoutingLayer.KEYWORD,
        source="builtin",
    )


class TestDegradationManager:
    def test_auto_level_high_confidence(self):
        mgr = DegradationManager(FakeConfig())
        route = make_route("systematic-debugging", 0.85)
        level, result_route = mgr.evaluate(route)
        assert level == DegradationLevel.AUTO
        assert result_route is route

    def test_suggest_level_moderate_confidence(self):
        mgr = DegradationManager(FakeConfig())
        route = make_route("superpowers/refactor", 0.55)
        level, result_route = mgr.evaluate(route)
        assert level == DegradationLevel.SUGGEST
        assert result_route is route

    def test_degrade_level_low_confidence(self):
        mgr = DegradationManager(FakeConfig())
        route = make_route("gstack/review", 0.35)
        level, result_route = mgr.evaluate(route)
        assert level == DegradationLevel.DEGRADE
        assert result_route is route
        assert result_route.metadata.get("degraded") is True

    def test_fallback_level_below_threshold(self):
        mgr = DegradationManager(FakeConfig())
        route = make_route("some-skill", 0.15)
        level, result_route = mgr.evaluate(route)
        assert level == DegradationLevel.FALLBACK
        assert result_route is None

    def test_no_primary_returns_fallback(self):
        mgr = DegradationManager(FakeConfig())
        level, result_route = mgr.evaluate(None)
        assert level == DegradationLevel.FALLBACK
        assert result_route is None

    def test_degradation_disabled_bypasses(self):
        config = FakeConfig()
        config.degradation_enabled = False
        mgr = DegradationManager(config)
        route = make_route("some-skill", 0.35)
        level, result_route = mgr.evaluate(route)
        assert level == DegradationLevel.AUTO
        assert result_route is route

    def test_boundary_confidence_exact_threshold(self):
        mgr = DegradationManager(FakeConfig())
        route = make_route("boundary-skill", 0.6)
        level, _ = mgr.evaluate(route)
        assert level == DegradationLevel.AUTO
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/core/routing/test_degradation.py -v`
Expected: FAIL with ModuleNotFoundError or ImportError

- [ ] **Step 3: Implement DegradationManager**

```python
# src/vibesop/core/routing/degradation.py

"""Confidence-gated layered degradation for skill routing.

Replaces binary fallback (match/no-match) with a 4-level degradation strategy:
- AUTO: confidence >= auto_threshold → auto-select
- SUGGEST: auto_threshold > confidence >= suggest_threshold → show with alternatives
- DEGRADE: suggest_threshold > confidence >= degrade_threshold → use but warn
- FALLBACK: confidence < degrade_threshold → raw LLM
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vibesop.core.models import DegradationLevel, RoutingLayer, SkillRoute

if TYPE_CHECKING:
    from vibesop.core.config.manager import RoutingConfig


class DegradationManager:
    """Evaluate routing match confidence and assign a degradation level."""

    def __init__(self, config: RoutingConfig) -> None:
        self._enabled = getattr(config, "degradation_enabled", True)
        self._auto_threshold = getattr(config, "degradation_auto_threshold", 0.6)
        self._suggest_threshold = getattr(config, "degradation_suggest_threshold", 0.4)
        self._degrade_threshold = getattr(config, "degradation_degrade_threshold", 0.2)
        self._always_ask = getattr(config, "degradation_fallback_always_ask", True)

    def evaluate(
        self, primary: SkillRoute | None
    ) -> tuple[DegradationLevel, SkillRoute | None]:
        """Evaluate a routing match and return (level, route).

        Returns (FALLBACK, None) when no route exists or confidence is below
        the degrade threshold.
        """
        if primary is None:
            return DegradationLevel.FALLBACK, None

        if not self._enabled:
            return DegradationLevel.AUTO, primary

        confidence = primary.confidence

        if confidence >= self._auto_threshold:
            return DegradationLevel.AUTO, primary

        if confidence >= self._suggest_threshold:
            return DegradationLevel.SUGGEST, primary

        if confidence >= self._degrade_threshold:
            degraded = SkillRoute(
                skill_id=primary.skill_id,
                confidence=primary.confidence,
                layer=primary.layer,
                source=primary.source,
                description=primary.description,
                metadata={**primary.metadata, "degraded": True, "degradation_level": "degrade"},
            )
            return DegradationLevel.DEGRADE, degraded

        return DegradationLevel.FALLBACK, None

    @property
    def always_ask_on_fallback(self) -> bool:
        return self._always_ask
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/core/routing/test_degradation.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/vibesop/core/routing/degradation.py tests/core/routing/test_degradation.py
git commit -m "feat: add DegradationManager with 4-level confidence-gated fallback"
```

---

### Task 3: Integrate DegradationManager into UnifiedRouter

**Files:**
- Modify: `src/vibesop/core/routing/unified.py:279-435`
- Modify: `src/vibesop/cli/main.py:194-220`

- [ ] **Step 1: Initialize DegradationManager in UnifiedRouter.__init__**

```python
# In src/vibesop/core/routing/unified.py, add after self._triage_service init (~line 247)

from vibesop.core.routing.degradation import DegradationManager

# In __init__, add:
self._degradation_manager = DegradationManager(self._config)
```

- [ ] **Step 2: Apply degradation evaluation in _route() after match is found**

In `_route()`, replace the current match-return logic with degradation-gated logic. After a primary match is found (at any layer), wrap the return with:

```python
# After any primary is assigned, before _build_match_result:
if primary and primary.layer not in (RoutingLayer.EXPLICIT, RoutingLayer.CUSTOM):
    degradation_level, degraded_primary = self._degradation_manager.evaluate(primary)
    if degradation_level == DegradationLevel.FALLBACK:
        primary = None
    elif degradation_level == DegradationLevel.DEGRADE:
        primary = degraded_primary
    primary.metadata["degradation_level"] = degradation_level.value
```

- [ ] **Step 3: Add degradation information to CLI output**

```python
# In src/vibesop/cli/main.py, in _handle_single_result, add after primary match:

if result.primary and result.primary.metadata.get("degraded"):
    degradation = result.primary.metadata.get("degradation_level", "unknown")
    console.print(
        f"  [yellow]Confidence is low ({result.primary.confidence:.0%}) — "
        f"degrading ({degradation}).[/yellow]"
    )
```

- [ ] **Step 4: Run existing router tests**

Run: `uv run pytest tests/test_router_layers.py -v`
Expected: All 11 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/vibesop/core/routing/unified.py src/vibesop/cli/main.py
git commit -m "feat: integrate DegradationManager into UnifiedRouter and CLI"
```

---

### Task 4: Skill Recommender Engine

**Files:**
- Create: `src/vibesop/integrations/skill_recommender.py`
- Create: `tests/integrations/test_skill_recommender.py`

- [ ] **Step 1: Write failing test for SkillRecommender**

```python
# tests/integrations/test_skill_recommender.py

from vibesop.integrations.skill_recommender import SkillRecommender, Recommendation


CANDIDATES = [
    {
        "id": "systematic-debugging",
        "namespace": "builtin",
        "intent": "Find root cause before attempting fixes",
        "triggers": ["error", "debug", "crash"],
        "priority": "P0",
    },
    {
        "id": "gstack/investigate",
        "namespace": "gstack",
        "intent": "Systematic debugging with root cause investigation",
        "triggers": ["error", "bug", "debug", "stack trace"],
        "priority": "P1",
    },
    {
        "id": "superpowers/optimize",
        "namespace": "superpowers",
        "intent": "Performance optimization and profiling guidance",
        "triggers": ["performance", "slow", "optimize"],
        "priority": "P1",
    },
    {
        "id": "gstack/office-hours",
        "namespace": "gstack",
        "intent": "Brainstorm new product ideas and evaluate whether to build",
        "triggers": ["brainstorm", "idea", "product"],
        "priority": "P2",
    },
]


class TestSkillRecommender:
    def test_recommend_by_query_keywords(self):
        recommender = SkillRecommender()
        results = recommender.recommend("I got a crash and need to debug", CANDIDATES, top_k=2)
        assert len(results) == 2
        assert results[0].skill_id in ("systematic-debugging", "gstack/investigate")
        assert results[0].score > 0.0

    def test_recommend_empty_candidates(self):
        recommender = SkillRecommender()
        results = recommender.recommend("anything", [], top_k=3)
        assert results == []

    def test_recommend_respects_top_k(self):
        recommender = SkillRecommender()
        results = recommender.recommend("debug", CANDIDATES, top_k=1)
        assert len(results) == 1

    def test_recommend_scores_are_sorted(self):
        recommender = SkillRecommender()
        results = recommender.recommend("debug performance", CANDIDATES, top_k=4)
        for i in range(len(results) - 1):
            assert results[i].score >= results[i + 1].score

    def test_recommend_from_patterns(self):
        recommender = SkillRecommender()
        pattern = "debug database connection error"
        results = recommender.recommend(pattern, CANDIDATES, top_k=2)
        assert any(r.skill_id in ("systematic-debugging", "gstack/investigate") for r in results)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integrations/test_skill_recommender.py -v`
Expected: FAIL with ModuleNotFoundError

- [ ] **Step 3: Implement SkillRecommender**

```python
# src/vibesop/integrations/skill_recommender.py

"""Per-skill recommendation engine based on query patterns and candidate similarity.

Unlike IntegrationRecommender (pack-level), this engine recommends individual skills
based on intent keyword overlap, trigger matching, and priority weighting.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from vibesop.core.orchestration.patterns import INTENT_DOMAIN_KEYWORDS


@dataclass
class Recommendation:
    """A single skill recommendation with a relevance score."""

    skill_id: str
    namespace: str
    score: float
    matched_keywords: list[str] = field(default_factory=list)
    intent: str = ""
    reason: str = ""


class SkillRecommender:
    """Recommend individual skills based on query-candidate similarity.

    Scoring dimensions:
    - Intent keyword overlap (40%): how many intent-domain keywords match
    - Trigger keyword match (30%): direct trigger word hits
    - Priority bonus (20%): P0 > P1 > P2
    - Namespace diversity boost (10%): avoid recommending all from same namespace
    """

    _PRIORITY_WEIGHTS: dict[str, float] = {"P0": 1.0, "P1": 0.7, "P2": 0.4}

    def __init__(self) -> None:
        self._keyword_index: dict[str, set[str]] = self._build_keyword_index()

    @staticmethod
    def _build_keyword_index() -> dict[str, set[str]]:
        """Flatten INTENT_DOMAIN_KEYWORDS into keyword -> intent domains."""
        index: dict[str, set[str]] = {}
        for domain, keywords in INTENT_DOMAIN_KEYWORDS.items():
            for kw in keywords:
                index.setdefault(kw.lower(), set()).add(domain)
        return index

    def recommend(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int = 3,
        exclude_namespaces: list[str] | None = None,
    ) -> list[Recommendation]:
        """Recommend skills that best match the query.

        Args:
            query: Natural language query
            candidates: Skill candidates (must have id, namespace, intent, triggers, priority)
            top_k: Number of recommendations to return
            exclude_namespaces: Namespaces to exclude from results

        Returns:
            Sorted list of Recommendation, highest score first
        """
        if not candidates:
            return []

        exclude = set(exclude_namespaces or [])
        query_lower = query.lower()

        # Extract matching intent domains from query keywords
        matched_domains: Counter[str] = Counter()
        for kw, domains in self._keyword_index.items():
            if kw in query_lower:
                for domain in domains:
                    matched_domains[domain] += 1

        scored: list[Recommendation] = []

        for candidate in candidates:
            if candidate.get("namespace", "") in exclude:
                continue

            skill_id = str(candidate.get("id", ""))
            namespace = str(candidate.get("namespace", "builtin"))
            intent = str(candidate.get("intent", ""))
            triggers = candidate.get("triggers", [])
            priority = str(candidate.get("priority", "P2"))
            intent_lower = intent.lower()

            score = 0.0
            matched_keywords: list[str] = []

            # Intent keyword overlap (40%)
            intent_overlap = 0
            for kw, domains in self._keyword_index.items():
                if kw in intent_lower:
                    intent_overlap += 1
                    matched_keywords.append(kw)
            score += min(intent_overlap / max(len(self._keyword_index) * 0.1, 1), 1.0) * 0.4

            # Trigger keyword match (30%)
            trigger_hits = sum(1 for t in triggers if t in query_lower)
            score += min(trigger_hits / max(len(triggers) * 0.3, 1), 1.0) * 0.3

            # Priority bonus (20%)
            score += self._PRIORITY_WEIGHTS.get(priority, 0.4) * 0.2

            # Namespace diversity bonus (10%): namespaces with fewer existing
            # recommendations get a small boost
            ns_count = sum(1 for r in scored if r.namespace == namespace)
            score += max(0, (1.0 - ns_count * 0.3)) * 0.1

            # Domain match bonus from query
            for kw in matched_keywords:
                if kw in matched_domains:
                    score += 0.05

            score = min(score, 1.0)

            reason_parts = []
            if intent_overlap:
                reason_parts.append(f"{intent_overlap} intent keyword matches")
            if trigger_hits:
                reason_parts.append(f"{trigger_hits} trigger hits")
            reason = "; ".join(reason_parts) if reason_parts else "priority-based match"

            scored.append(Recommendation(
                skill_id=skill_id,
                namespace=namespace,
                score=round(score, 4),
                matched_keywords=matched_keywords,
                intent=intent,
                reason=reason,
            ))

        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/integrations/test_skill_recommender.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/vibesop/integrations/skill_recommender.py tests/integrations/test_skill_recommender.py
git commit -m "feat: add SkillRecommender for per-skill pattern-based recommendation"
```

---

### Task 5: Market Install Flow

**Files:**
- Modify: `src/vibesop/market/crawler.py:12-77`
- Modify: `src/vibesop/cli/commands/market_cmd.py`

- [ ] **Step 1: Add install_source() method to SkillRepo**

```python
# In src/vibesop/market/crawler.py, add method to SkillRepo:

@dataclass
class SkillRepo:
    name: str
    description: str
    stars: int
    topics: list[str]
    quality_score: float
    html_url: str

    @property
    def install_source(self) -> str:
        """Return the installable source (git URL) for this repo."""
        return f"https://github.com/{self.name}"
```

- [ ] **Step 2: Add 'vibe market install' command**

```python
# In src/vibesop/cli/commands/market_cmd.py, add after existing commands:

@market_app.command(name="install")
def market_install(
    repo_name: str = typer.Argument(..., help="GitHub repo in 'owner/repo' format"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Install a skill pack from the market (GitHub repo)."""
    from vibesop.installer.pack_installer import PackInstaller
    from vibesop.constants import TRUSTED_PACKS

    console = Console()
    url = f"https://github.com/{repo_name}"

    if not yes:
        confirmed = questionary.confirm(
            f"Install skill pack from {url}?",
            default=True,
        ).ask()
        if not confirmed:
            console.print("[yellow]Installation cancelled.[/yellow]")
            raise typer.Exit(0)

    installer = PackInstaller()
    try:
        result = installer.install_pack(repo_name, url)
        console.print(f"[green]Successfully installed {result.pack_name} "
                      f"({result.skill_count} skills)[/green]")
    except Exception as e:
        console.print(f"[red]Installation failed: {e}[/red]")
        raise typer.Exit(1)
```

- [ ] **Step 3: Verify market_cmd.py imports are valid**

Run: `uv run python -c "from vibesop.cli.commands.market_cmd import app; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/vibesop/market/crawler.py src/vibesop/cli/commands/market_cmd.py
git commit -m "feat: add 'vibe market install' for installing skills from market search results"
```

---

### Task 6: Intent Domain Weighting for Better Decomposition

**Files:**
- Modify: `src/vibesop/core/orchestration/patterns.py`

- [ ] **Step 1: Add weighted intent domains for multi-intent detection**

Replace `INTENT_DOMAINS` with a weighted version that helps MultiIntentDetector distinguish between primary and secondary intents:

```python
# In src/vibesop/core/orchestration/patterns.py, add after INTENT_DOMAINS:

INTENT_DOMAIN_WEIGHTS: dict[str, float] = {
    "analyze": 0.9,
    "review": 0.8,
    "debug": 0.95,
    "optimize": 0.7,
    "refactor": 0.7,
    "test": 0.8,
    "implement": 0.85,
    "document": 0.5,
    "deploy": 0.6,
    "security": 0.9,
    "design": 0.8,
    "brainstorm": 0.6,
}
```

- [ ] **Step 2: Lower MultiIntentDetector thresholds for broader detection**

In `src/vibesop/core/orchestration/multi_intent_detector.py:37-41`, change defaults:

```python
def __init__(
    self,
    min_query_length: int = 15,          # was 20
    low_confidence_threshold: float = 0.7, # was 0.8
    alternative_threshold: float = 0.5,    # was 0.6
    confidence_gap_threshold: float = 0.2, # was 0.15
):
```

- [ ] **Step 3: Run existing orchestration tests**

Run: `uv run pytest tests/ -k "orchestrat" -v`
Expected: Any orchestration-related tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/vibesop/core/orchestration/patterns.py src/vibesop/core/orchestration/multi_intent_detector.py
git commit -m "feat: add intent domain weights and lower decomposition thresholds"
```

---

## Verification

After all tasks are complete, run the full test suite:

```bash
uv run pytest tests/ -x --ignore=tests/e2e/ -q
```

Expected: All tests pass. No regressions in existing routing, orchestration, or adapter tests.

Then verify end-to-end behavior:

```bash
# Test degradation config
uv run python -c "
from vibesop.core.config.manager import ConfigManager
c = ConfigManager()
r = c.get_routing_config()
print('degradation:', r.degradation_enabled, r.degradation_auto_threshold)
"

# Test recommender
uv run python -c "
from vibesop.integrations.skill_recommender import SkillRecommender
r = SkillRecommender()
recs = r.recommend('debug database error', [{'id':'test', 'namespace':'b','intent':'debug errors','triggers':['debug'],'priority':'P0'}])
print([(x.skill_id, x.score) for x in recs])
"

# Test market install command exists
uv run vibe market install --help
```
