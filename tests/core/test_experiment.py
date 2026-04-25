"""Tests for vibesop.core.experiment module."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from vibesop.core.experiment import (
    Experiment,
    ExperimentAnalyzer,
    ExperimentRunner,
    ExperimentStore,
    RouteMetrics,
    VariantConfig,
    VariantResult,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestVariantConfig:
    """Test VariantConfig serialization."""

    def test_to_dict(self) -> None:
        v = VariantConfig(name="baseline", description="Default config", overrides={"min_confidence": 0.7})
        data = v.to_dict()
        assert data["name"] == "baseline"
        assert data["overrides"]["min_confidence"] == 0.7

    def test_from_dict(self) -> None:
        data = {"name": "test", "description": "d", "overrides": {"a": 1}}
        v = VariantConfig.from_dict(data)
        assert v.name == "test"
        assert v.overrides == {"a": 1}


class TestRouteMetrics:
    """Test RouteMetrics serialization."""

    def test_roundtrip(self) -> None:
        m = RouteMetrics(
            query="test",
            matched=True,
            skill_id="a/b",
            confidence=0.85,
            layer="keyword",
            duration_ms=12.5,
        )
        restored = RouteMetrics.from_dict(m.to_dict())
        assert restored.query == "test"
        assert restored.confidence == 0.85


class TestVariantResult:
    """Test VariantResult aggregation."""

    def test_match_rate(self) -> None:
        vr = VariantResult(
            variant=VariantConfig(name="v"),
            metrics=[
                RouteMetrics("q1", True, "a", 0.8, "keyword", 10.0),
                RouteMetrics("q2", False, None, 0.0, None, 5.0),
                RouteMetrics("q3", True, "b", 0.9, "tfidf", 8.0),
            ],
        )
        assert vr.match_rate == 2 / 3

    def test_avg_confidence(self) -> None:
        vr = VariantResult(
            variant=VariantConfig(name="v"),
            metrics=[
                RouteMetrics("q1", True, "a", 0.8, "keyword", 10.0),
                RouteMetrics("q2", True, "b", 0.6, "keyword", 5.0),
            ],
        )
        assert vr.avg_confidence == 0.7

    def test_avg_confidence_no_matches(self) -> None:
        vr = VariantResult(
            variant=VariantConfig(name="v"),
            metrics=[RouteMetrics("q1", False, None, 0.0, None, 10.0)],
        )
        assert vr.avg_confidence == 0.0

    def test_fallback_rate(self) -> None:
        vr = VariantResult(
            variant=VariantConfig(name="v"),
            metrics=[
                RouteMetrics("q1", True, "a", 0.8, "fallback_llm", 10.0),
                RouteMetrics("q2", True, "b", 0.6, "keyword", 5.0),
            ],
        )
        assert vr.fallback_rate == 0.5


class TestExperiment:
    """Test Experiment serialization."""

    def test_roundtrip(self) -> None:
        exp = Experiment(
            name="test-exp",
            description="test",
            queries=["q1", "q2"],
            variants=[VariantConfig("v1"), VariantConfig("v2")],
            created_at="2026-04-22",
        )
        restored = Experiment.from_dict(exp.to_dict())
        assert restored.name == "test-exp"
        assert len(restored.variants) == 2
        assert restored.queries == ["q1", "q2"]


class TestExperimentStore:
    """Test ExperimentStore persistence."""

    def test_save_and_load(self, tmp_path: Path) -> None:
        store = ExperimentStore(tmp_path)
        exp = Experiment(name="my-exp", description="d", queries=["q"], variants=[VariantConfig("v1")], created_at="now")
        store.save(exp)

        loaded = store.load("my-exp")
        assert loaded is not None
        assert loaded.name == "my-exp"

    def test_load_nonexistent(self, tmp_path: Path) -> None:
        store = ExperimentStore(tmp_path)
        assert store.load("none") is None

    def test_list_experiments(self, tmp_path: Path) -> None:
        store = ExperimentStore(tmp_path)
        store.save(Experiment(name="exp-a", description="", queries=[], variants=[], created_at=""))
        store.save(Experiment(name="exp-b", description="", queries=[], variants=[], created_at=""))
        names = store.list_experiments()
        assert sorted(names) == ["exp-a", "exp-b"]

    def test_delete(self, tmp_path: Path) -> None:
        store = ExperimentStore(tmp_path)
        store.save(Experiment(name="del", description="", queries=[], variants=[], created_at=""))
        assert store.delete("del") is True
        assert store.load("del") is None
        assert store.delete("del") is False


class TestExperimentAnalyzer:
    """Test ExperimentAnalyzer winner selection."""

    def test_analyze_selects_winner(self) -> None:
        exp = Experiment(
            name="test",
            description="",
            queries=["q1", "q2"],
            variants=[
                VariantConfig("good"),
                VariantConfig("bad"),
            ],
            created_at="",
            status="completed",
        )
        exp.results["good"] = VariantResult(
            variant=VariantConfig("good"),
            metrics=[
                RouteMetrics("q1", True, "a", 0.9, "keyword", 10.0),
                RouteMetrics("q2", True, "b", 0.9, "keyword", 10.0),
            ],
        )
        exp.results["bad"] = VariantResult(
            variant=VariantConfig("bad"),
            metrics=[
                RouteMetrics("q1", False, None, 0.0, None, 20.0),
                RouteMetrics("q2", False, None, 0.0, None, 20.0),
            ],
        )

        analysis = ExperimentAnalyzer.analyze(exp)
        assert "error" not in analysis
        assert analysis["winner"] == "good"
        assert analysis["scores"]["good"] > analysis["scores"]["bad"]
        assert exp.winner == "good"

    def test_analyze_not_completed(self) -> None:
        exp = Experiment(name="test", description="", queries=[], variants=[], created_at="", status="draft")
        analysis = ExperimentAnalyzer.analyze(exp)
        assert "error" in analysis

    def test_analyze_single_variant(self) -> None:
        exp = Experiment(
            name="test",
            description="",
            queries=["q1"],
            variants=[VariantConfig("only")],
            created_at="",
            status="completed",
        )
        exp.results["only"] = VariantResult(variant=VariantConfig("only"), metrics=[])
        analysis = ExperimentAnalyzer.analyze(exp)
        assert "error" in analysis


class TestExperimentRunner:
    """Test ExperimentRunner with mocked router."""

    def test_run_experiment(self, tmp_path: Path) -> None:
        exp = Experiment(
            name="run-test",
            description="",
            queries=["hello"],
            variants=[
                VariantConfig("v1"),
                VariantConfig("v2"),
            ],
            created_at="",
        )

        mock_result = MagicMock()
        mock_result.has_match = True
        mock_result.primary.skill_id = "test/skill"
        mock_result.primary.confidence = 0.85
        mock_result.primary.layer.value = "keyword"

        with patch("vibesop.core.routing.UnifiedRouter") as mock_router_cls:
            mock_router = MagicMock()
            mock_router.route.return_value = mock_result
            mock_router_cls.return_value = mock_router

            runner = ExperimentRunner(tmp_path)
            completed = runner.run(exp)

            assert completed.status == "completed"
            assert "v1" in completed.results
            assert "v2" in completed.results
            assert completed.results["v1"].match_rate == 1.0
            assert completed.results["v1"].metrics[0].skill_id == "test/skill"
