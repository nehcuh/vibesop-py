"""Tests for cold start strategy."""

from pathlib import Path

from vibesop.core.optimization.cold_start import (
    ColdStartStrategy,
    QuerySkillMapping,
    get_cold_start_strategy,
)


class TestColdStartStrategy:
    """Test suite for ColdStartStrategy."""

    def test_init_with_string(self) -> None:
        """Test initialization with string path."""
        strategy = ColdStartStrategy(".")
        assert isinstance(strategy.project_root, Path)

    def test_get_builtin_mappings(self) -> None:
        """Test built-in mappings retrieval."""
        strategy = ColdStartStrategy()
        mappings = strategy.get_builtin_mappings()
        assert len(mappings) > 0
        assert all(isinstance(m, QuerySkillMapping) for m in mappings)

    def test_get_mapping_for_query_pattern_match(self) -> None:
        """Test query mapping by pattern."""
        strategy = ColdStartStrategy()
        mapping = strategy.get_mapping_for_query("I need to debug this")
        assert mapping is not None
        assert mapping.skill_id == "systematic-debugging"

    def test_get_mapping_for_query_keyword_match(self) -> None:
        """Test query mapping by keyword."""
        strategy = ColdStartStrategy()
        mapping = strategy.get_mapping_for_query("修复一个 bug")
        assert mapping is not None
        assert mapping.skill_id == "systematic-debugging"

    def test_get_mapping_for_query_no_match(self) -> None:
        """Test query mapping returns None for unknown query."""
        strategy = ColdStartStrategy()
        mapping = strategy.get_mapping_for_query("xyzabc123")
        assert mapping is None

    def test_get_default_weights(self) -> None:
        """Test default matcher weights."""
        strategy = ColdStartStrategy()
        weights = strategy.get_default_weights()
        assert "keyword" in weights
        assert weights["keyword"] == 1.0

    def test_get_p0_skills(self) -> None:
        """Test priority skills retrieval."""
        strategy = ColdStartStrategy()
        skills = strategy.get_p0_skills()
        assert "systematic-debugging" in skills

    def test_get_namespace_priority_known(self) -> None:
        """Test namespace priority for known namespaces."""
        strategy = ColdStartStrategy()
        assert strategy.get_namespace_priority("builtin") == 100
        assert strategy.get_namespace_priority("superpowers") == 80

    def test_get_namespace_priority_unknown(self) -> None:
        """Test namespace priority fallback."""
        strategy = ColdStartStrategy()
        assert strategy.get_namespace_priority("unknown") == 50

    def test_should_warm_cache_true(self, tmp_path) -> None:
        """Test cache warming recommendation when no preferences exist."""
        strategy = ColdStartStrategy(tmp_path)
        assert strategy.should_warm_cache() is True

    def test_should_warm_cache_false(self, tmp_path) -> None:
        """Test cache warming recommendation when preferences exist."""
        prefs = tmp_path / ".vibe" / "preferences.json"
        prefs.parent.mkdir(parents=True)
        prefs.write_text("{}")
        strategy = ColdStartStrategy(tmp_path)
        assert strategy.should_warm_cache() is False


class TestGetColdStartStrategy:
    """Test suite for get_cold_start_strategy factory."""

    def test_singleton_behavior(self) -> None:
        """Factory should return cached instance."""
        # Clear any cached strategy
        if hasattr(get_cold_start_strategy, "_strategy"):
            delattr(get_cold_start_strategy, "_strategy")

        s1 = get_cold_start_strategy()
        s2 = get_cold_start_strategy()
        assert s1 is s2

    def test_new_instance_when_none_cached(self) -> None:
        """Factory creates new instance when cache is cleared."""
        s1 = get_cold_start_strategy()
        delattr(get_cold_start_strategy, "_strategy")
        s2 = get_cold_start_strategy()
        assert s1 is not s2
