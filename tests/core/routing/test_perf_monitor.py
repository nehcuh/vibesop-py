"""Tests for routing performance monitor."""

import pytest

from vibesop.core.routing.perf_monitor import (
    RouteTiming,
    RoutingPerfMonitor,
    get_perf_monitor,
    reset_perf_monitor,
)


class TestRouteTiming:
    """Test RouteTiming dataclass."""

    def test_creation(self):
        timing = RouteTiming(duration_ms=42.0, route_layer="ai_triage")
        assert timing.duration_ms == pytest.approx(42.0)
        assert timing.route_layer == "ai_triage"
        assert timing.timestamp > 0


class TestRoutingPerfMonitor:
    """Test RoutingPerfMonitor statistics."""

    def test_init(self):
        monitor = RoutingPerfMonitor(window_size=50)
        assert monitor._window_size == 50

    def test_record_and_get_stats(self):
        monitor = RoutingPerfMonitor(window_size=100)
        monitor.record(10.0, "keyword")
        monitor.record(20.0, "scenario")
        monitor.record(30.0, "ai_triage")

        stats = monitor.get_stats()
        assert stats["total_routes"] == 3
        assert stats["window_size"] == 3
        assert stats["avg_ms"] == pytest.approx(20.0)
        assert stats["p50_ms"] == pytest.approx(20.0)
        assert stats["p95_ms"] > 0
        assert stats["p99_ms"] > 0
        assert stats["layer_distribution"]["keyword"] == 1
        assert stats["layer_distribution"]["scenario"] == 1
        assert stats["layer_distribution"]["ai_triage"] == 1

    def test_empty_stats(self):
        monitor = RoutingPerfMonitor()
        stats = monitor.get_stats()
        assert stats["total_routes"] == 0
        assert stats["window_size"] == 0
        assert stats["avg_ms"] == pytest.approx(0.0)
        assert stats["p50_ms"] == pytest.approx(0.0)
        assert stats["p95_ms"] == pytest.approx(0.0)
        assert stats["p99_ms"] == pytest.approx(0.0)
        assert stats["layer_distribution"] == {}

    def test_window_size_limit(self):
        monitor = RoutingPerfMonitor(window_size=3)
        monitor.record(1.0, "a")
        monitor.record(2.0, "a")
        monitor.record(3.0, "a")
        monitor.record(4.0, "a")

        stats = monitor.get_stats()
        assert stats["window_size"] == 3
        assert stats["total_routes"] == 4
        # Oldest should be evicted
        assert stats["avg_ms"] == pytest.approx(10.0 / 4)  # total routes still 4
        durations = [1.0, 2.0, 3.0, 4.0]
        assert stats["p50_ms"] == pytest.approx(3.0)  # median of [2,3,4]

    def test_percentile_calculation(self):
        monitor = RoutingPerfMonitor()
        # Test with known data
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert monitor._percentile(data, 0) == pytest.approx(1.0)
        assert monitor._percentile(data, 50) == pytest.approx(3.0)
        assert monitor._percentile(data, 100) == pytest.approx(5.0)

    def test_percentile_empty(self):
        monitor = RoutingPerfMonitor()
        assert monitor._percentile([], 50) == pytest.approx(0.0)

    def test_get_target_status_on_target(self):
        monitor = RoutingPerfMonitor()
        monitor.record(10.0, "keyword")
        monitor.record(20.0, "keyword")
        on_target, p95 = monitor.get_target_status(p95_target_ms=100.0)
        assert on_target is True
        assert p95 > 0

    def test_get_target_status_off_target(self):
        monitor = RoutingPerfMonitor()
        monitor.record(200.0, "ai_triage")
        on_target, p95 = monitor.get_target_status(p95_target_ms=100.0)
        assert on_target is False
        assert p95 > 100.0

    def test_get_target_status_empty(self):
        monitor = RoutingPerfMonitor()
        on_target, p95 = monitor.get_target_status()
        assert on_target is False
        assert p95 == pytest.approx(0.0)

    def test_single_record_percentiles(self):
        monitor = RoutingPerfMonitor()
        monitor.record(42.0, "keyword")
        stats = monitor.get_stats()
        assert stats["p50_ms"] == pytest.approx(42.0)
        assert stats["p95_ms"] == pytest.approx(42.0)
        assert stats["p99_ms"] == pytest.approx(42.0)


class TestGlobalPerfMonitor:
    """Test module-level singleton functions."""

    def test_get_perf_monitor_returns_singleton(self):
        reset_perf_monitor()
        m1 = get_perf_monitor()
        m2 = get_perf_monitor()
        assert m1 is m2

    def test_reset_perf_monitor(self):
        reset_perf_monitor()
        m1 = get_perf_monitor()
        m1.record(10.0, "test")
        reset_perf_monitor()
        m2 = get_perf_monitor()
        assert m1 is not m2
        assert m2.get_stats()["total_routes"] == 0
