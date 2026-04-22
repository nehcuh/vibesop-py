"""Tests for vibesop.core.matching.plugin module."""

from __future__ import annotations

from pathlib import Path

import pytest

from vibesop.core.matching.plugin import MatcherPluginRegistry, PluginMatcher


class TestPluginMatcher:
    """Test PluginMatcher scoring and matching."""

    def test_score_success(self) -> None:
        def match_fn(query: str, candidate: dict[str, str]) -> float:
            if query in candidate.get("name", ""):
                return 0.8
            return 0.0

        plugin = PluginMatcher(
            name="test",
            description="Test matcher",
            source_file=Path("/tmp/test.py"),
            match_fn=match_fn,
        )
        score = plugin.score("hello", {"name": "hello world"})
        assert score == 0.8

    def test_score_failure_returns_zero(self) -> None:
        def match_fn(query: str, candidate: dict[str, str]) -> float:
            raise ValueError("boom")

        plugin = PluginMatcher(
            name="test",
            description="",
            source_file=Path("/tmp/test.py"),
            match_fn=match_fn,
        )
        score = plugin.score("q", {"id": "a"})
        assert score == 0.0

    def test_match_filters_low_scores(self) -> None:
        def match_fn(query: str, candidate: dict[str, str]) -> float:
            return 0.3 if candidate.get("id") == "a" else 0.0

        plugin = PluginMatcher(
            name="test",
            description="",
            source_file=Path("/tmp/test.py"),
            match_fn=match_fn,
        )
        results = plugin.match("q", [{"id": "a"}, {"id": "b"}])
        assert len(results) == 1
        assert results[0].skill_id == "a"

    def test_match_respects_top_k(self) -> None:
        def match_fn(query: str, candidate: dict[str, str]) -> float:
            return float(candidate.get("score", 0))

        plugin = PluginMatcher(
            name="test",
            description="",
            source_file=Path("/tmp/test.py"),
            match_fn=match_fn,
        )
        candidates = [
            {"id": "a", "score": 0.9},
            {"id": "b", "score": 0.8},
            {"id": "c", "score": 0.7},
        ]
        results = plugin.match("q", candidates, top_k=2)
        assert len(results) == 2
        assert results[0].skill_id == "a"
        assert results[1].skill_id == "b"

    def test_weight_applied(self) -> None:
        def match_fn(query: str, candidate: dict[str, str]) -> float:
            return 0.5

        plugin = PluginMatcher(
            name="test",
            description="",
            source_file=Path("/tmp/test.py"),
            match_fn=match_fn,
            weight=0.5,
        )
        results = plugin.match("q", [{"id": "a"}])
        assert results[0].confidence == 0.25  # 0.5 * 0.5


class TestMatcherPluginRegistry:
    """Test MatcherPluginRegistry loading and management."""

    def test_empty_directory(self, tmp_path: Path) -> None:
        registry = MatcherPluginRegistry(tmp_path)
        assert registry.list_plugins() == []

    def test_load_valid_plugin(self, tmp_path: Path) -> None:
        matchers_dir = tmp_path / ".vibe" / "matchers"
        matchers_dir.mkdir(parents=True)

        plugin_file = matchers_dir / "my_matcher.py"
        plugin_file.write_text("""
NAME = "my_matcher"
DESCRIPTION = "A test matcher"
WEIGHT = 0.8

def match(query: str, candidate: dict) -> float:
    if "test" in query:
        return 0.9
    return 0.0
""")

        registry = MatcherPluginRegistry(tmp_path)
        plugins = registry.list_plugins()
        assert len(plugins) == 1
        assert plugins[0].name == "my_matcher"
        assert plugins[0].description == "A test matcher"
        assert plugins[0].weight == 0.8

    def test_load_without_name_uses_filename(self, tmp_path: Path) -> None:
        matchers_dir = tmp_path / ".vibe" / "matchers"
        matchers_dir.mkdir(parents=True)

        plugin_file = matchers_dir / "fallback.py"
        plugin_file.write_text("""
def match(query: str, candidate: dict) -> float:
    return 0.1
""")

        registry = MatcherPluginRegistry(tmp_path)
        plugins = registry.list_plugins()
        assert len(plugins) == 1
        assert plugins[0].name == "fallback"

    def test_skip_underscore_files(self, tmp_path: Path) -> None:
        matchers_dir = tmp_path / ".vibe" / "matchers"
        matchers_dir.mkdir(parents=True)

        plugin_file = matchers_dir / "_private.py"
        plugin_file.write_text("""
def match(query: str, candidate: dict) -> float:
    return 1.0
""")

        registry = MatcherPluginRegistry(tmp_path)
        assert registry.list_plugins() == []

    def test_skip_files_without_match_function(self, tmp_path: Path) -> None:
        matchers_dir = tmp_path / ".vibe" / "matchers"
        matchers_dir.mkdir(parents=True)

        plugin_file = matchers_dir / "bad.py"
        plugin_file.write_text("""
NAME = "bad"
# No match function
""")

        registry = MatcherPluginRegistry(tmp_path)
        assert registry.list_plugins() == []

    def test_register_new_file(self, tmp_path: Path) -> None:
        src_file = tmp_path / "new_matcher.py"
        src_file.write_text("""
NAME = "new_matcher"

def match(query: str, candidate: dict) -> float:
    return 0.5
""")

        registry = MatcherPluginRegistry(tmp_path)
        plugin = registry.register(src_file)

        assert plugin is not None
        assert plugin.name == "new_matcher"
        assert (tmp_path / ".vibe" / "matchers" / "new_matcher.py").exists()

    def test_register_nonexistent_file(self, tmp_path: Path) -> None:
        registry = MatcherPluginRegistry(tmp_path)
        plugin = registry.register(tmp_path / "no.py")
        assert plugin is None

    def test_remove_plugin(self, tmp_path: Path) -> None:
        matchers_dir = tmp_path / ".vibe" / "matchers"
        matchers_dir.mkdir(parents=True)

        plugin_file = matchers_dir / "to_remove.py"
        plugin_file.write_text("""
def match(query: str, candidate: dict) -> float:
    return 0.1
""")

        registry = MatcherPluginRegistry(tmp_path)
        assert len(registry.list_plugins()) == 1

        assert registry.remove("to_remove") is True
        assert registry.list_plugins() == []
        assert not plugin_file.exists()

    def test_remove_nonexistent(self, tmp_path: Path) -> None:
        registry = MatcherPluginRegistry(tmp_path)
        assert registry.remove("none") is False

    def test_reload(self, tmp_path: Path) -> None:
        matchers_dir = tmp_path / ".vibe" / "matchers"
        matchers_dir.mkdir(parents=True)

        plugin_file = matchers_dir / "reload.py"
        plugin_file.write_text("""
def match(query: str, candidate: dict) -> float:
    return 0.1
""")

        registry = MatcherPluginRegistry(tmp_path)
        assert len(registry.list_plugins()) == 1

        # Add another file directly
        (matchers_dir / "new.py").write_text("""
def match(query: str, candidate: dict) -> float:
    return 0.2
""")

        registry.reload()
        assert len(registry.list_plugins()) == 2

    def test_get_plugin(self, tmp_path: Path) -> None:
        matchers_dir = tmp_path / ".vibe" / "matchers"
        matchers_dir.mkdir(parents=True)

        plugin_file = matchers_dir / "specific.py"
        plugin_file.write_text("""
NAME = "specific"

def match(query: str, candidate: dict) -> float:
    return 0.1
""")

        registry = MatcherPluginRegistry(tmp_path)
        assert registry.get_plugin("specific") is not None
        assert registry.get_plugin("none") is None
