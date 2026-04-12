"""Tests for the production ConflictResolver framework."""

import pytest

from vibesop.core.matching import MatchResult, MatcherType
from vibesop.core.routing.conflict import (
    ConfidenceGapStrategy,
    ConflictResolver,
    ExplicitOverrideStrategy,
    FallbackStrategy,
    NamespacePriorityStrategy,
    RecencyStrategy,
)


def _make_match(skill_id: str, confidence: float, namespace: str = "builtin") -> MatchResult:
    return MatchResult(
        skill_id=skill_id,
        confidence=confidence,
        matcher_type=MatcherType.KEYWORD,
        metadata={"namespace": namespace},
    )


def test_explicit_override_strategy():
    strategy = ExplicitOverrideStrategy()
    matches = [
        _make_match("review", 0.8),
        _make_match("debug", 0.9),
    ]
    result = strategy.resolve(matches, "use review")
    assert result is not None
    assert result.primary == "review"
    assert result.metadata["strategy"] == "explicit_override"


def test_confidence_gap_strategy_resolves_when_gap_is_clear():
    strategy = ConfidenceGapStrategy(gap_threshold=0.15)
    matches = [
        _make_match("debug", 0.9),
        _make_match("review", 0.7),
    ]
    result = strategy.resolve(matches, "debug this")
    assert result is not None
    assert result.primary == "debug"


def test_confidence_gap_strategy_returns_none_when_gap_is_small():
    strategy = ConfidenceGapStrategy(gap_threshold=0.15)
    matches = [
        _make_match("debug", 0.81),
        _make_match("review", 0.80),
    ]
    result = strategy.resolve(matches, "debug this")
    assert result is None


def test_namespace_priority_strategy():
    strategy = NamespacePriorityStrategy()
    matches = [
        _make_match("external_debug", 0.85, namespace="superpowers"),
        _make_match("builtin_debug", 0.80, namespace="builtin"),
    ]
    result = strategy.resolve(matches, "debug")
    assert result is not None
    # External packs (default 80) are preferred over builtin fallback (60)
    assert result.primary == "external_debug"


def test_namespace_priority_strategy_no_clear_winner():
    strategy = NamespacePriorityStrategy()
    matches = [
        _make_match("a", 0.8, namespace="pack1"),
        _make_match("b", 0.8, namespace="pack2"),
    ]
    # Both external packs default to 80, gap is 0 -> no resolution
    result = strategy.resolve(matches, "debug")
    assert result is None


def test_fallback_strategy():
    strategy = FallbackStrategy()
    matches = [
        _make_match("debug", 0.85),
        _make_match("review", 0.80),
    ]
    result = strategy.resolve(matches, "debug")
    assert result is not None
    assert result.primary == "debug"
    assert result.needs_review  # gap 0.05 < 0.1


def test_fallback_strategy_needs_review_on_close_call():
    strategy = FallbackStrategy()
    matches = [
        _make_match("debug", 0.81),
        _make_match("review", 0.80),
    ]
    result = strategy.resolve(matches, "debug")
    assert result is not None
    assert result.needs_review is True


def test_conflict_resolver_uses_explicit_override_first():
    resolver = ConflictResolver()
    matches = [
        _make_match("debug", 0.95),
        _make_match("review", 0.90),
    ]
    result = resolver.resolve(matches, "use review")
    assert result.primary == "review"


def test_conflict_resolver_uses_confidence_gap_when_no_explicit():
    resolver = ConflictResolver()
    matches = [
        _make_match("debug", 0.95),
        _make_match("review", 0.70),
    ]
    result = resolver.resolve(matches, "help me debug")
    assert result.primary == "debug"


def test_conflict_resolver_uses_namespace_priority_for_close_call():
    # When confidence gap is small, namespace priority should break the tie
    resolver = ConflictResolver()
    matches = [
        _make_match("external_debug", 0.81, namespace="superpowers"),
        _make_match("builtin_debug", 0.80, namespace="builtin"),
    ]
    result = resolver.resolve(matches, "help me debug")
    # Namespace priority picks external over builtin
    assert result.primary == "external_debug"


def test_conflict_resolver_empty_matches():
    resolver = ConflictResolver()
    result = resolver.resolve([], "help")
    assert result.primary is None
