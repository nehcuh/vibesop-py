"""Tests for cold start strategy."""

from pathlib import Path

import pytest

from vibesop.core.optimization.cold_start import (
    ColdStartStrategy,
    QuerySkillMapping,
    get_cold_start_strategy,
)


class TestQuerySkillMapping:
    """Test QuerySkillMapping dataclass."""

    def test_creation(self):
        mapping = QuerySkillMapping(pattern="debug", skill_id="gstack/investigate")
        assert mapping.pattern == "debug"
        assert mapping.skill_id == "gstack/investigate"
        assert mapping.confidence == pytest.approx(0.9)
        assert mapping.keywords == []

    def test_creation_with_keywords(self):
        mapping = QuerySkillMapping(
            pattern="test", skill_id="superpowers/tdd", keywords=["test", "tdd"]
        )
        assert mapping.keywords == ["test", "tdd"]


class TestColdStartStrategy:
    """Test ColdStartStrategy methods."""

    def test_get_builtin_mappings(self):
        strategy = ColdStartStrategy()
        mappings = strategy.get_builtin_mappings()
        assert len(mappings) > 0
        assert all(isinstance(m, QuerySkillMapping) for m in mappings)
        patterns = [m.pattern for m in mappings]
        assert "debug" in patterns
        assert "review" in patterns

    def test_get_mapping_for_query_pattern_match(self):
        strategy = ColdStartStrategy()
        mapping = strategy.get_mapping_for_query("debug this error")
        assert mapping is not None
        assert mapping.skill_id == "superpowers/debug"

    def test_get_mapping_for_query_keyword_match(self):
        strategy = ColdStartStrategy()
        mapping = strategy.get_mapping_for_query("修复这个bug")
        assert mapping is not None
        assert mapping.skill_id == "superpowers/debug"

    def test_get_mapping_for_query_no_match(self):
        strategy = ColdStartStrategy()
        mapping = strategy.get_mapping_for_query("xyzabc123")
        assert mapping is None

    def test_get_default_weights(self):
        strategy = ColdStartStrategy()
        weights = strategy.get_default_weights()
        assert "keyword" in weights
        assert weights["keyword"] == pytest.approx(1.0)
        assert weights["levenshtein"] == pytest.approx(0.7)

    def test_get_default_weights_returns_copy(self):
        strategy = ColdStartStrategy()
        weights1 = strategy.get_default_weights()
        weights2 = strategy.get_default_weights()
        assert weights1 is not weights2
        weights1["keyword"] = 0.5
        assert weights2["keyword"] == pytest.approx(1.0)

    def test_get_p0_skills(self):
        strategy = ColdStartStrategy()
        skills = strategy.get_p0_skills()
        assert "session-end" in skills

    def test_get_p0_skills_returns_copy(self):
        strategy = ColdStartStrategy()
        skills1 = strategy.get_p0_skills()
        skills2 = strategy.get_p0_skills()
        assert skills1 is not skills2

    def test_get_namespace_priority_builtin(self):
        strategy = ColdStartStrategy()
        assert strategy.get_namespace_priority("builtin") == 100

    def test_get_namespace_priority_gstack(self):
        """gstack namespace returns default priority (not in priority map)."""
        strategy = ColdStartStrategy()
        assert strategy.get_namespace_priority("gstack") == 50  # external default

    def test_get_namespace_priority_unknown(self):
        strategy = ColdStartStrategy()
        assert strategy.get_namespace_priority("unknown") == 50

    def test_should_warm_cache_when_no_prefs(self, tmp_path: Path):
        strategy = ColdStartStrategy(project_root=tmp_path)
        assert strategy.should_warm_cache() is True

    def test_should_warm_cache_when_prefs_exist(self, tmp_path: Path):
        prefs_path = tmp_path / ".vibe" / "preferences.json"
        prefs_path.parent.mkdir(parents=True, exist_ok=True)
        prefs_path.write_text("{}", encoding="utf-8")
        strategy = ColdStartStrategy(project_root=tmp_path)
        assert strategy.should_warm_cache() is False


class TestGetColdStartStrategy:
    """Test module-level singleton function."""

    def test_returns_cold_start_strategy(self, tmp_path: Path):
        strategy = get_cold_start_strategy(project_root=tmp_path)
        assert isinstance(strategy, ColdStartStrategy)
