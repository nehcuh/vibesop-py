"""Tests for RouterStatsMixin — stats, preferences, and AI triage cost tracking."""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

from vibesop.core.models import RoutingLayer
from vibesop.core.routing.stats_mixin import RouterStatsMixin


class _MockHost(RouterStatsMixin):
    """Minimal host satisfying _StatsHost protocol."""

    def __init__(self) -> None:
        self._total_routes = 0
        self._layer_distribution: dict[str, int] = {}
        self._stats_lock = threading.Lock()
        self._cost_tracker = MagicMock()
        self._config = MagicMock()
        self._config.ai_triage_budget_monthly = 5.0
        self._preference_booster = MagicMock()
        self.project_root = Path("/tmp/test-project")
        self.logger = MagicMock()


class TestRecordLayer:
    """Test _record_layer distribution tracking."""

    def test_record_single_layer(self) -> None:
        """Recording a layer increments its count."""
        host = _MockHost()
        host._record_layer(RoutingLayer.KEYWORD)
        assert host._layer_distribution["keyword"] == 1

    def test_record_multiple_same_layer(self) -> None:
        """Multiple records of same layer accumulate."""
        host = _MockHost()
        host._record_layer(RoutingLayer.AI_TRIAGE)
        host._record_layer(RoutingLayer.AI_TRIAGE)
        assert host._layer_distribution["ai_triage"] == 2

    def test_record_different_layers(self) -> None:
        """Different layers tracked separately."""
        host = _MockHost()
        host._record_layer(RoutingLayer.KEYWORD)
        host._record_layer(RoutingLayer.SCENARIO)
        assert host._layer_distribution["keyword"] == 1
        assert host._layer_distribution["scenario"] == 1

    def test_record_layer_thread_safety(self) -> None:
        """Concurrent updates are safe due to lock."""
        host = _MockHost()

        def record_many() -> None:
            for _ in range(100):
                host._record_layer(RoutingLayer.KEYWORD)

        threads = [threading.Thread(target=record_many) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert host._layer_distribution["keyword"] == 400


class TestGetStats:
    """Test get_stats aggregation."""

    def test_empty_stats(self) -> None:
        """No routes recorded → zeros and empty distributions."""
        host = _MockHost()
        host._cost_tracker.get_stats.return_value = {
            "total_cost_usd": 0.0,
            "monthly_cost_usd": 0.0,
        }
        with patch("vibesop.core.routing.perf_monitor.get_perf_monitor") as mock_get:
            mock_perf = MagicMock()
            mock_perf.get_stats.return_value = {
                "window_size": 0,
                "p50_ms": 0.0,
                "p95_ms": 0.0,
                "p99_ms": 0.0,
                "avg_ms": 0.0,
            }
            mock_get.return_value = mock_perf

            stats = host.get_stats()

        assert stats["total_routes"] == 0
        assert stats["layer_distribution"] == {}
        assert stats["cache_dir"] == str(Path("/tmp/test-project/.vibe/cache"))
        assert stats["performance"]["p95_on_target"] is True  # 0 < 100

    def test_with_routes_and_layers(self) -> None:
        """Stats reflect recorded routes and layer distribution."""
        host = _MockHost()
        host._total_routes = 5
        host._layer_distribution = {"keyword": 3, "ai_triage": 2}
        host._cost_tracker.get_stats.return_value = {
            "total_cost_usd": 0.0,
            "monthly_cost_usd": 0.0,
        }

        with patch("vibesop.core.routing.perf_monitor.get_perf_monitor") as mock_get:
            mock_perf = MagicMock()
            mock_perf.get_stats.return_value = {
                "window_size": 5,
                "p50_ms": 15.0,
                "p95_ms": 45.0,
                "p99_ms": 50.0,
                "avg_ms": 20.0,
            }
            mock_get.return_value = mock_perf

            stats = host.get_stats()

        assert stats["total_routes"] == 5
        assert stats["layer_distribution"] == {"keyword": 3, "ai_triage": 2}
        assert stats["performance"]["p50_ms"] == 15.0
        assert stats["performance"]["p95_on_target"] is True  # 45 < 100

    def test_p95_off_target(self) -> None:
        """p95_on_target is False when P95 exceeds target."""
        host = _MockHost()
        host._cost_tracker.get_stats.return_value = {
            "total_cost_usd": 0.0,
            "monthly_cost_usd": 0.0,
        }
        with patch("vibesop.core.routing.perf_monitor.get_perf_monitor") as mock_get:
            mock_perf = MagicMock()
            mock_perf.get_stats.return_value = {
                "window_size": 1,
                "p50_ms": 10.0,
                "p95_ms": 150.0,
                "p99_ms": 150.0,
                "avg_ms": 10.0,
            }
            mock_get.return_value = mock_perf

            stats = host.get_stats()

        assert stats["performance"]["p95_on_target"] is False


class TestGetAiTriageStats:
    """Test AI triage cost and budget tracking."""

    def test_budget_remaining(self) -> None:
        """Budget remaining calculated from cost tracker stats."""
        host = _MockHost()
        host._cost_tracker.get_stats.return_value = {
            "total_cost_usd": 2.5,
            "monthly_cost_usd": 1.0,
        }
        host._config.ai_triage_budget_monthly = 5.0

        stats = host.get_ai_triage_stats()

        assert stats["budget_monthly_usd"] == 5.0
        assert stats["budget_remaining_usd"] == 2.5

    def test_budget_exhausted(self) -> None:
        """Remaining budget floors at zero."""
        host = _MockHost()
        host._cost_tracker.get_stats.return_value = {
            "total_cost_usd": 10.0,
            "monthly_cost_usd": 10.0,
        }
        host._config.ai_triage_budget_monthly = 5.0

        stats = host.get_ai_triage_stats()

        assert stats["budget_remaining_usd"] == 0.0

    def test_default_budget_when_unset(self) -> None:
        """Default budget is 5.0 when config lacks the attribute."""
        host = _MockHost()
        host._cost_tracker.get_stats.return_value = {
            "total_cost_usd": 1.0,
            "monthly_cost_usd": 1.0,
        }
        # Remove attribute so getattr falls back to default
        delattr(host._config, "ai_triage_budget_monthly")

        stats = host.get_ai_triage_stats()

        assert stats["budget_monthly_usd"] == 5.0
        assert stats["budget_remaining_usd"] == 4.0


class TestPreferenceTracking:
    """Test preference booster delegation methods."""

    def test_record_selection(self) -> None:
        """record_selection delegates to preference booster learner."""
        host = _MockHost()
        mock_learner = MagicMock()
        host._preference_booster.get_learner.return_value = mock_learner

        host.record_selection("gstack/review", "review code", was_helpful=True)

        mock_learner.record_selection.assert_called_once_with("gstack/review", "review code", True)

    def test_get_preference_stats(self) -> None:
        """get_preference_stats delegates to learner."""
        host = _MockHost()
        mock_learner = MagicMock()
        mock_learner.get_stats.return_value = {"total_selections": 42}
        host._preference_booster.get_learner.return_value = mock_learner

        stats = host.get_preference_stats()

        assert stats["total_selections"] == 42

    def test_get_top_skills(self) -> None:
        """get_top_skills delegates with limit and min_selections."""
        host = _MockHost()
        mock_learner = MagicMock()
        mock_learner.get_top_skills.return_value = [{"skill_id": "gstack/review", "count": 10}]
        host._preference_booster.get_learner.return_value = mock_learner

        result = host.get_top_skills(limit=3, min_selections=5)

        mock_learner.get_top_skills.assert_called_once_with(3, 5)
        assert len(result) == 1

    def test_clear_old_preferences(self) -> None:
        """clear_old_preferences delegates to learner and returns count."""
        host = _MockHost()
        mock_learner = MagicMock()
        mock_learner.clear_old_data.return_value = 7
        host._preference_booster.get_learner.return_value = mock_learner

        count = host.clear_old_preferences(days=30)

        mock_learner.clear_old_data.assert_called_once_with(30)
        assert count == 7
