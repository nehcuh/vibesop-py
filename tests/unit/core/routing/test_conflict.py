"""Tests for conflict resolution strategies and ConflictResolver."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vibesop.core.matching.base import MatchResult, MatcherType
from vibesop.core.routing.conflict import (
    ConfidenceGapStrategy,
    ConflictResolution,
    ConflictResolver,
    ExplicitOverrideStrategy,
    FallbackStrategy,
    NamespacePriorityStrategy,
    RecencyStrategy,
    ResolutionStrategy,
)


def _make_match(skill_id: str, confidence: float, namespace: str = "builtin") -> MatchResult:
    """Factory for test MatchResult objects."""
    return MatchResult(
        skill_id=skill_id,
        confidence=confidence,
        matcher_type=MatcherType.KEYWORD,
        metadata={"namespace": namespace},
    )


class TestConfidenceGapStrategy:
    """Test confidence-gap-based conflict resolution."""

    def test_insufficient_matches(self) -> None:
        """Less than 2 matches → no resolution."""
        strategy = ConfidenceGapStrategy(gap_threshold=0.15)
        assert strategy.resolve([_make_match("a", 0.9)], "query") is None

    def test_gap_below_threshold(self) -> None:
        """Gap smaller than threshold → no resolution."""
        strategy = ConfidenceGapStrategy(gap_threshold=0.15)
        matches = [
            _make_match("a", 0.90),
            _make_match("b", 0.80),
        ]
        assert strategy.resolve(matches, "query") is None

    def test_gap_at_threshold(self) -> None:
        """Gap exactly at threshold → resolution."""
        strategy = ConfidenceGapStrategy(gap_threshold=0.125)
        matches = [
            _make_match("a", 0.750),
            _make_match("b", 0.625),
        ]
        result = strategy.resolve(matches, "query")
        assert result is not None
        assert result.primary == "a"
        assert result.needs_review is False
        assert result.metadata["gap"] == pytest.approx(0.125)

    def test_gap_above_threshold(self) -> None:
        """Gap above threshold → clear winner."""
        strategy = ConfidenceGapStrategy(gap_threshold=0.15)
        matches = [
            _make_match("a", 0.95),
            _make_match("b", 0.70),
            _make_match("c", 0.60),
        ]
        result = strategy.resolve(matches, "query")
        assert result is not None
        assert result.primary == "a"
        assert "b" in result.alternatives
        assert "c" in result.alternatives

    def test_priority_value(self) -> None:
        assert ConfidenceGapStrategy().priority() == 90


class TestNamespacePriorityStrategy:
    """Test namespace-priority-based conflict resolution."""

    def test_insufficient_matches(self) -> None:
        strategy = NamespacePriorityStrategy()
        assert strategy.resolve([_make_match("a", 0.9, "builtin")], "query") is None

    def test_no_clear_winner(self) -> None:
        """Namespaces with similar priorities → no resolution."""
        strategy = NamespacePriorityStrategy()
        matches = [
            _make_match("a", 0.9, "builtin"),
            _make_match("b", 0.8, "superpowers"),
        ]
        # builtin=60, superpowers=80 → diff=20 which is >5, so there IS a winner
        result = strategy.resolve(matches, "query")
        assert result is not None
        assert result.primary == "b"  # superpowers has higher priority

    def test_clear_winner(self) -> None:
        """One namespace clearly dominates."""
        strategy = NamespacePriorityStrategy()
        matches = [
            _make_match("a", 0.9, "project"),  # priority 100
            _make_match("b", 0.8, "builtin"),  # priority 60
        ]
        result = strategy.resolve(matches, "query")
        assert result is not None
        assert result.primary == "a"
        assert result.metadata["namespace"] == "project"
        assert result.metadata["priority"] == 100

    def test_unknown_namespace(self) -> None:
        """Unknown namespace defaults to priority 50."""
        strategy = NamespacePriorityStrategy()
        matches = [
            _make_match("a", 0.9, "unknown"),
            _make_match("b", 0.8, "builtin"),
        ]
        result = strategy.resolve(matches, "query")
        assert result is not None
        assert result.primary == "b"  # builtin=60 > unknown=50

    def test_custom_priorities(self) -> None:
        """Custom priority mapping overrides defaults."""
        strategy = NamespacePriorityStrategy(priorities={"custom": 200})
        matches = [
            _make_match("a", 0.9, "custom"),
            _make_match("b", 0.8, "project"),
        ]
        result = strategy.resolve(matches, "query")
        assert result is not None
        assert result.primary == "a"

    def test_priority_value(self) -> None:
        assert NamespacePriorityStrategy().priority() == 80

    def test_tie_within_margin(self) -> None:
        """Difference of exactly 5 → not > 5, so no resolution."""
        strategy = NamespacePriorityStrategy(priorities={"high": 55, "low": 50})
        matches = [
            _make_match("a", 0.9, "high"),
            _make_match("b", 0.8, "low"),
        ]
        # 55 > 50 + 5 → 55 > 55 is False
        assert strategy.resolve(matches, "query") is None

    def test_best_in_winning_namespace(self) -> None:
        """When namespace wins, pick highest-confidence match within it."""
        strategy = NamespacePriorityStrategy()
        matches = [
            _make_match("a", 0.6, "project"),  # lower conf in winning ns
            _make_match("b", 0.9, "project"),  # higher conf in winning ns
            _make_match("c", 0.8, "builtin"),
        ]
        result = strategy.resolve(matches, "query")
        assert result is not None
        assert result.primary == "b"


class TestRecencyStrategy:
    """Test recency-based conflict resolution."""

    def test_insufficient_matches(self) -> None:
        strategy = RecencyStrategy()
        assert strategy.resolve([_make_match("a", 0.9)], "query") is None

    def test_no_recent_skills(self) -> None:
        """Empty recent skills cache → no resolution."""
        strategy = RecencyStrategy()
        matches = [
            _make_match("a", 0.9),
            _make_match("b", 0.8),
        ]
        assert strategy.resolve(matches, "query") is None

    def test_recent_skill_wins(self, tmp_path: Path) -> None:
        """Most recently used skill within 7 days wins."""
        prefs = {
            "selections": {
                "a": [{"timestamp": 9999999999.0}],
                "b": [{"timestamp": 9999999998.0}],
            }
        }
        prefs_file = tmp_path / "prefs.json"
        prefs_file.write_text(json.dumps(prefs))

        strategy = RecencyStrategy(storage_path=str(prefs_file))
        matches = [
            _make_match("a", 0.6),
            _make_match("b", 0.9),
        ]
        result = strategy.resolve(matches, "query")
        assert result is not None
        assert result.primary == "a"
        assert result.metadata["strategy"] == "recency"

    def test_only_one_recent_match(self, tmp_path: Path) -> None:
        """Need at least 2 recent matches to resolve."""
        prefs = {"selections": {"a": [{"timestamp": 9999999999.0}]}}
        prefs_file = tmp_path / "prefs.json"
        prefs_file.write_text(json.dumps(prefs))

        strategy = RecencyStrategy(storage_path=str(prefs_file))
        matches = [
            _make_match("a", 0.6),
            _make_match("b", 0.9),
        ]
        assert strategy.resolve(matches, "query") is None

    def test_stale_recent_skills(self, tmp_path: Path) -> None:
        """Skills older than 7 days don't win."""
        prefs = {
            "selections": {
                "a": [{"timestamp": 1000.0}],
                "b": [{"timestamp": 500.0}],
            }
        }
        prefs_file = tmp_path / "prefs.json"
        prefs_file.write_text(json.dumps(prefs))

        strategy = RecencyStrategy(storage_path=str(prefs_file))
        matches = [
            _make_match("a", 0.6),
            _make_match("b", 0.9),
        ]
        assert strategy.resolve(matches, "query") is None

    def test_caching(self, tmp_path: Path) -> None:
        """Recent skills are cached after first load."""
        prefs = {
            "selections": {
                "a": [{"timestamp": 9999999999.0}],
                "b": [{"timestamp": 9999999998.0}],
            }
        }
        prefs_file = tmp_path / "prefs.json"
        prefs_file.write_text(json.dumps(prefs))

        strategy = RecencyStrategy(storage_path=str(prefs_file))
        strategy._load_recent_skills()
        assert strategy._recent_skills is not None

        # Delete file — cached data should still work
        prefs_file.unlink()
        matches = [
            _make_match("a", 0.6),
            _make_match("b", 0.9),
        ]
        result = strategy.resolve(matches, "query")
        assert result is not None

    def test_load_failure(self, tmp_path: Path) -> None:
        """Invalid JSON returns empty dict and caches it."""
        prefs_file = tmp_path / "prefs.json"
        prefs_file.write_text("not json")

        strategy = RecencyStrategy(storage_path=str(prefs_file))
        assert strategy._load_recent_skills() == {}
        assert strategy._recent_skills == {}

    def test_priority_value(self) -> None:
        assert RecencyStrategy().priority() == 70


class TestExplicitOverrideStrategy:
    """Test explicit user override detection."""

    def test_slash_command(self) -> None:
        """/skill_id pattern matches."""
        strategy = ExplicitOverrideStrategy()
        matches = [
            _make_match("gstack/review", 0.9),
            _make_match("other", 0.8),
        ]
        result = strategy.resolve(matches, "/review")
        assert result is not None
        assert result.primary == "gstack/review"
        assert result.metadata["override_type"] == "slash"

    def test_use_command(self) -> None:
        """use skill_id pattern matches."""
        strategy = ExplicitOverrideStrategy()
        matches = [
            _make_match("tdd", 0.9),
            _make_match("other", 0.8),
        ]
        result = strategy.resolve(matches, "use tdd")
        assert result is not None
        assert result.primary == "tdd"
        assert result.metadata["override_type"] == "use"

    def test_run_command(self) -> None:
        """run skill_id pattern matches."""
        strategy = ExplicitOverrideStrategy()
        matches = [
            _make_match("review", 0.9),
            _make_match("other", 0.8),
        ]
        result = strategy.resolve(matches, "run review")
        assert result is not None
        assert result.primary == "review"
        assert result.metadata["override_type"] == "run"

    def test_suffix_match(self) -> None:
        """Partial suffix match works."""
        strategy = ExplicitOverrideStrategy()
        matches = [
            _make_match("gstack/review", 0.9),
            _make_match("other", 0.8),
        ]
        result = strategy.resolve(matches, "use review")
        assert result is not None
        assert result.primary == "gstack/review"

    def test_no_match(self) -> None:
        """No override pattern → no resolution."""
        strategy = ExplicitOverrideStrategy()
        matches = [
            _make_match("a", 0.9),
            _make_match("b", 0.8),
        ]
        assert strategy.resolve(matches, "help me debug") is None

    def test_skill_not_found(self) -> None:
        """Override pattern matches but skill not in candidates."""
        strategy = ExplicitOverrideStrategy()
        matches = [
            _make_match("a", 0.9),
            _make_match("b", 0.8),
        ]
        assert strategy.resolve(matches, "/nonexistent") is None

    def test_priority_value(self) -> None:
        assert ExplicitOverrideStrategy().priority() == 100


class TestFallbackStrategy:
    """Test fallback conflict resolution."""

    def test_empty_matches(self) -> None:
        """Empty matches returns None primary."""
        strategy = FallbackStrategy()
        result = strategy.resolve([], "query")
        assert result is not None
        assert result.primary is None
        assert result.reason == "No matches found"

    def test_single_match(self) -> None:
        """Single match is selected."""
        strategy = FallbackStrategy()
        matches = [_make_match("a", 0.75)]
        result = strategy.resolve(matches, "query")
        assert result.primary == "a"
        assert result.alternatives == []
        assert result.needs_review is False

    def test_close_call(self) -> None:
        """Top two within 0.1 → needs_review=True."""
        strategy = FallbackStrategy()
        matches = [
            _make_match("a", 0.85),
            _make_match("b", 0.80),
        ]
        result = strategy.resolve(matches, "query")
        assert result.primary == "a"
        assert result.needs_review is True

    def test_clear_winner(self) -> None:
        """Top two differ by >= 0.1 → needs_review=False."""
        strategy = FallbackStrategy()
        matches = [
            _make_match("a", 0.90),
            _make_match("b", 0.70),
        ]
        result = strategy.resolve(matches, "query")
        assert result.primary == "a"
        assert result.needs_review is False

    def test_priority_value(self) -> None:
        assert FallbackStrategy().priority() == 0


class TestConflictResolver:
    """Test the main ConflictResolver orchestrator."""

    def test_empty_matches(self) -> None:
        resolver = ConflictResolver()
        result = resolver.resolve([], "query")
        assert result.primary is None
        assert result.reason == "No matches to resolve"

    def test_strategy_priority_order(self) -> None:
        """Higher-priority strategies are tried first."""
        resolver = ConflictResolver()
        strategies = resolver._strategies
        priorities = [s.priority() for s in strategies]
        assert priorities == sorted(priorities, reverse=True)

    def test_explicit_override_wins(self) -> None:
        """ExplicitOverrideStrategy (priority 100) wins over others."""
        resolver = ConflictResolver()
        resolver.add_strategy(ExplicitOverrideStrategy())
        matches = [
            _make_match("review", 0.6),
            _make_match("other", 0.9),
        ]
        result = resolver.resolve(matches, "/review")
        assert result.primary == "review"
        assert "Explicit override" in result.reason

    def test_confidence_gap_wins_when_no_override(self) -> None:
        """ConfidenceGapStrategy resolves when no explicit override."""
        resolver = ConflictResolver()
        matches = [
            _make_match("a", 0.95),
            _make_match("b", 0.70),
        ]
        result = resolver.resolve(matches, "debug this")
        assert result.primary == "a"
        assert "confidence gap" in result.reason

    def test_fallback_always_works(self) -> None:
        """FallbackStrategy ensures resolver never returns None."""
        resolver = ConflictResolver()
        matches = [
            _make_match("a", 0.55),
            _make_match("b", 0.54),
        ]
        result = resolver.resolve(matches, "vague query")
        assert result is not None
        assert result.primary == "a"

    def test_add_strategy(self) -> None:
        """Adding a strategy maintains priority sort order."""
        resolver = ConflictResolver()
        custom = ConfidenceGapStrategy(gap_threshold=0.01)
        resolver.add_strategy(custom)
        # Should still be sorted by priority descending
        priorities = [s.priority() for s in resolver._strategies]
        assert priorities == sorted(priorities, reverse=True)

    def test_custom_strategy_can_win(self) -> None:
        """A custom high-priority strategy can win."""
        resolver = ConflictResolver()

        class AlwaysPickFirst(ResolutionStrategy):
            def resolve(self, matches, _query, _context=None):
                if matches:
                    return ConflictResolution(
                        primary=matches[0].skill_id,
                        alternatives=[m.skill_id for m in matches[1:]],
                        reason="always first",
                    )
                return None

            def priority(self) -> int:
                return 200

        resolver.add_strategy(AlwaysPickFirst())
        matches = [
            _make_match("first", 0.1),
            _make_match("second", 0.9),
        ]
        result = resolver.resolve(matches, "query")
        assert result.primary == "first"
        assert result.reason == "always first"
