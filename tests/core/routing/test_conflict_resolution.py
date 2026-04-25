"""Tests for conflict resolution framework."""


from vibesop.core.matching.base import MatchResult, MatcherType
from vibesop.core.routing.conflict import (
    ConflictResolver,
    NamespacePriorityStrategy,
)


class TestNamespacePriorityStrategy:
    """Test namespace priority conflict resolution."""

    def test_builtin_beats_unknown_external(self):
        """Unknown external namespaces should not outrank builtin skills."""
        strategy = NamespacePriorityStrategy()
        matches = [
            MatchResult(
                skill_id="systematic-debugging",
                confidence=0.85,
                matcher_type=MatcherType.KEYWORD,
                metadata={"namespace": "builtin"},
            ),
            MatchResult(
                skill_id="suspicious/skill",
                confidence=0.90,
                matcher_type=MatcherType.KEYWORD,
                metadata={"namespace": "unknown_pack"},
            ),
        ]
        resolution = strategy.resolve(matches, "debug this")
        assert resolution is not None
        assert resolution.primary == "systematic-debugging"
        assert "Namespace priority: builtin" in resolution.reason

    def test_project_beats_builtin(self):
        """Project skills should outrank builtin skills."""
        strategy = NamespacePriorityStrategy()
        matches = [
            MatchResult(
                skill_id="systematic-debugging",
                confidence=0.85,
                matcher_type=MatcherType.KEYWORD,
                metadata={"namespace": "builtin"},
            ),
            MatchResult(
                skill_id="my-project-skill",
                confidence=0.80,
                matcher_type=MatcherType.KEYWORD,
                metadata={"namespace": "project"},
            ),
        ]
        resolution = strategy.resolve(matches, "debug this")
        assert resolution is not None
        assert resolution.primary == "my-project-skill"

    def test_single_match_returns_none(self):
        """Strategy should not activate with only one match."""
        strategy = NamespacePriorityStrategy()
        matches = [
            MatchResult(
                skill_id="systematic-debugging",
                confidence=0.85,
                matcher_type=MatcherType.KEYWORD,
                metadata={"namespace": "builtin"},
            ),
        ]
        resolution = strategy.resolve(matches, "debug this")
        assert resolution is None


class TestConflictResolverDefaults:
    """Test default conflict resolver configuration."""

    def test_no_explicit_override_strategy_in_defaults(self):
        """ExplicitOverrideStrategy should not be in default strategies."""
        resolver = ConflictResolver()
        strategy_names = {type(s).__name__ for s in resolver._strategies}
        assert "ExplicitOverrideStrategy" not in strategy_names
