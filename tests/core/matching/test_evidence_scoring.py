"""Tests for M11 evidence-based scoring (KeywordMatcher._score_evidence,
TFIDFMatcher anchor gate, warm-up lifecycle).

All queries/candidates are synthetic and intentionally unrelated to the
routing eval sets — the mechanisms must hold for unseen text, not just for
the calibration samples.
"""

from __future__ import annotations

from vibesop.core.matching.strategies import KeywordMatcher, MatcherConfig, TFIDFMatcher
from vibesop.core.matching.tokenizers import tokenize


def _cand(skill_id, name="", description="", intent="", keywords=None):
    return {
        "id": skill_id,
        "name": name,
        "description": description,
        "intent": intent,
        "keywords": keywords or [],
    }


def _pool(n_filler=20):
    """20 generic fillers + 1 distinctive skill.

    In this pool (N=21): w(commonword)=0.256 (df=20, generic),
    w(quilting)=w(zephyrloom)=0.830 (df=1, distinctive) — the distinctive
    terms clear the 0.78 anchor bar, the generic ones do not.
    """
    pool = [
        _cand(f"filler-{i}", name=f"Filler {i}", keywords=["commonword", "plainstuff"])
        for i in range(n_filler)
    ]
    pool.append(
        _cand(
            "rare-skill",
            name="zephyrloom",
            description="weaves looms",
            keywords=["quilting", "zephyrloom"],
        )
    )
    return pool


def _warmed_matcher(**cfg_overrides):
    m = KeywordMatcher(MatcherConfig(**cfg_overrides))
    m.warm_up(_pool())
    return m


class TestAnchorGate:
    """Mechanism 1: no anchor → score capped at keyword_anchor_cap."""

    def test_generic_only_hit_capped(self):
        m = _warmed_matcher()
        c = _cand("filler-0", name="Filler 0", keywords=["commonword", "plainstuff"])
        # "commonword" hits keywords but is pool-generic; "please" has no
        # evidence against this candidate. No anchor exists.
        assert m.score("commonword please", c) <= m._config.keyword_anchor_cap

    def test_distinctive_hit_lifts_cap(self):
        m = _warmed_matcher()
        c = _cand("rare-skill", name="zephyrloom", keywords=["quilting", "zephyrloom"])
        # "quilting" is a distinctive keyword hit → anchor → cap lifted.
        assert m.score("quilting please", c) > m._config.keyword_anchor_cap


class TestCoverageGate:
    """Mechanism 2: bonuses scale with idf-weighted query coverage."""

    def test_same_hit_lower_score_when_diluted(self):
        m = _warmed_matcher()
        c = _cand("rare-skill", name="zephyrloom", keywords=["quilting"])
        focused = m.score("quilting please", c)
        diluted = m.score(
            "quilting umbrella vortex lattice nebula tundra osprey falcon heron juniper",
            c,
        )
        assert diluted < focused


class TestMultiAnchorExemption:
    """Mechanism 3: >=2 distinctive NAME/KEYWORD hits + non-trivial coverage
    saturate the coverage gate (g=1)."""

    def test_two_keyword_anchors_exempt_from_gate(self):
        m = _warmed_matcher()
        c = _cand("rare-skill", name="zephyrloom", keywords=["quilting", "zephyrloom"])
        two_anchors = m.score(
            "quilting zephyrloom umbrella vortex lattice nebula tundra osprey falcon",
            c,
        )
        one_anchor = m.score(
            "quilting umbrella vortex lattice nebula tundra osprey falcon heron",
            c,
        )
        assert two_anchors > one_anchor
        # Exemption saturates g=1, so the diluted two-anchor query scores
        # like a focused one.
        focused = m.score("quilting zephyrloom", c)
        assert two_anchors >= focused - 0.05


class TestNameBonusGuard:
    """Mechanism 4: single-token generic names earn no name bonus."""

    def test_generic_single_token_name_gets_no_bonus(self):
        m = _warmed_matcher()
        c = _cand("generic-named", name="commonword", keywords=[])
        # name "commonword" appears verbatim in the query, but w=0.256 <
        # keyword_name_idf_min → no 0.4 bonus, and no anchor → capped.
        assert m.score("please commonword thing", c) <= m._config.keyword_anchor_cap

    def test_distinctive_single_token_name_keeps_bonus(self):
        m = _warmed_matcher()
        c = _cand("rare-skill", name="zephyrloom", keywords=["quilting"])
        # w(zephyrloom)=0.830 ≥ keyword_name_idf_min → name bonus applies.
        assert m.score("please zephyrloom thing", c) >= 0.4


class TestPerTokenBestPartial:
    """Mechanism 5: a query token earns its BEST partial hit once, not one
    contribution per candidate token."""

    def test_no_cross_pair_accumulation(self):
        c = _cand(
            "rare-skill",
            name="zephyrloom",
            description="tester testing testify",
            keywords=["quilting"],
        )
        warmed = _warmed_matcher()
        legacy = KeywordMatcher()  # unwarmed → legacy additive formula
        query = "quilting test"  # "test" prefix-matches 3 candidate tokens
        legacy_score = legacy.score(query, c)
        new_score = warmed.score(query, c)
        # Legacy accumulates 3 x 0.15 = 0.45 (capped 0.4); new takes 0.15.
        assert legacy_score - new_score > 0.2


class TestLegacyFallback:
    """Unwarmed matcher (no candidate pool seen) keeps the pre-M11 formula."""

    def test_unwarmed_dispatches_to_legacy(self):
        m = KeywordMatcher()
        assert m._idf is None
        c = _cand("x", name="Test Skill", keywords=["test", "testing"])
        query = "test something"
        expected = m._score_legacy(set(tokenize(query)), c)
        assert m.score(query, c) == expected

    def test_warm_up_empty_keeps_legacy(self):
        m = KeywordMatcher()
        m.warm_up([])
        assert m._idf is None


class TestWarmUpLifecycle:
    def test_warm_up_builds_table_and_clears_cache(self):
        m = KeywordMatcher()
        m.match("hello there", _pool())
        assert m._cache  # populated by the match call
        m.warm_up(_pool())
        assert m._idf is not None
        assert m._cache == {}

    def test_warm_up_empty_resets_to_legacy(self):
        """Empty pool = explicit reset back to the unwarmed legacy formula."""
        m = _warmed_matcher()
        assert m._idf is not None
        m.warm_up([])
        assert m._idf is None
        assert m._cache == {}


class TestCoverageFloorRejectsExemption:
    """pi nit: 2+ anchors but coverage below the floor must NOT exempt."""

    def test_diluted_multi_anchor_stays_gated(self):
        m = _warmed_matcher()
        # Name kept OUT of the query terms so the (ungated) name bonus
        # doesn't mask the coverage-gate behavior under test.
        c = _cand("rare-skill", name="loomcraft", keywords=["quilting", "zephyrloom"])
        # Two nk anchors, but 25 unmatched rare tokens dilute coverage below
        # keyword_multi_anchor_cov_floor (0.08) → exemption must not fire.
        diluted = m.score(
            "quilting zephyrloom umbrella vortex lattice nebula tundra osprey falcon "
            "heron juniper willow birch maple cedar ember garnet opal topaz onyx ruby "
            "coral amber ivory pearl sable umber",
            c,
        )
        focused = m.score("quilting zephyrloom", c)
        assert diluted < 0.3, f"exemption leaked through cov floor: {diluted}"
        assert focused > diluted


class TestConfigGuards:
    def test_zero_coverage_ref_does_not_divide_by_zero(self):
        # MatcherConfig is a plain dataclass (no field validation); the
        # scorer must guard the division itself. ref=0 degrades to
        # "coverage gating off" (gate saturates).
        m = _warmed_matcher(keyword_coverage_ref=0.0)
        c = _cand("rare-skill", name="zephyrloom", keywords=["quilting"])
        score = m.score("quilting please", c)
        assert 0.0 <= score <= 1.0


class TestTFIDFAnchorGate:
    """TF-IDF results without anchor evidence are dropped (M11)."""

    def test_anchorless_result_dropped(self):
        m = TFIDFMatcher(MatcherConfig(min_confidence=0.0))
        m.fit(_pool())
        results = m.match("commonword please", _pool())
        assert results == []

    def test_anchored_result_kept(self):
        m = TFIDFMatcher(MatcherConfig(min_confidence=0.0))
        m.fit(_pool())
        # Extra tokens dilute the tiny-pool TF-IDF cosine below 1.0
        # (MatchResult validates confidence <= 1).
        results = m.match("quilting umbrella vortex lattice", _pool())
        assert [r.skill_id for r in results] == ["rare-skill"]

    def test_gate_disabled_restores_results(self):
        m = TFIDFMatcher(MatcherConfig(min_confidence=0.0, tfidf_anchor_gate_enabled=False))
        m.fit(_pool())
        results = m.match("commonword please", _pool())
        assert results  # gate off: surface overlap is enough again
