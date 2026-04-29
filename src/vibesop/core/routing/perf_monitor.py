"""Routing performance monitor — tracks real-time routing latency percentiles.

Provides P50/P95/P99 calculation on a rolling window of recent routes,
exposed via `vibe route-stats`.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class RouteTiming:
    """Timing data for a single routing call."""

    duration_ms: float
    route_layer: str
    timestamp: float = field(default_factory=time.time)


class RoutingPerfMonitor:
    """Tracks routing performance with rolling percentile metrics.

    Maintains a sliding window of the most recent N route timings
    and computes P50, P95, P99 on demand.

    Example:
        >>> monitor = RoutingPerfMonitor(window_size=100)
        >>> monitor.record(45.2, "ai_triage")
        >>> monitor.record(12.5, "scenario")
        >>> print(monitor.get_stats())
    """

    def __init__(self, window_size: int = 100):
        self._window_size = window_size
        self._timings: deque[RouteTiming] = deque(maxlen=window_size)
        self._lock = Lock()
        self._total_routes: int = 0
        self._total_duration_ms: float = 0.0
        self._layer_counts: dict[str, int] = {}

    def record(self, duration_ms: float, route_layer: str = "unknown") -> None:
        """Record a routing timing.

        Args:
            duration_ms: Routing duration in milliseconds
            route_layer: The layer that produced the final match
        """
        with self._lock:
            self._timings.append(
                RouteTiming(
                    duration_ms=duration_ms,
                    route_layer=route_layer,
                )
            )
            self._total_routes += 1
            self._total_duration_ms += duration_ms
            self._layer_counts[route_layer] = self._layer_counts.get(route_layer, 0) + 1

    def get_stats(self) -> dict:
        """Get current performance statistics.

        Returns:
            Dictionary with:
                - total_routes: int
                - window_size: int (current, may be less than max)
                - avg_ms: float
                - p50_ms: float
                - p95_ms: float
                - p99_ms: float
                - layer_distribution: dict
        """
        with self._lock:
            if not self._timings:
                return {
                    "total_routes": self._total_routes,
                    "window_size": 0,
                    "avg_ms": 0.0,
                    "p50_ms": 0.0,
                    "p95_ms": 0.0,
                    "p99_ms": 0.0,
                    "layer_distribution": {},
                }

            durations = sorted(t.duration_ms for t in self._timings)
            n = len(durations)

            return {
                "total_routes": self._total_routes,
                "window_size": n,
                "avg_ms": self._total_duration_ms / self._total_routes,
                "p50_ms": self._percentile(durations, 50),
                "p95_ms": self._percentile(durations, 95),
                "p99_ms": self._percentile(durations, 99),
                "layer_distribution": dict(self._layer_counts),
            }

    def get_target_status(self, p95_target_ms: float = 100.0) -> tuple[bool, float]:
        """Check if P95 is within target.

        Args:
            p95_target_ms: Target P95 latency in ms

        Returns:
            (is_on_target, current_p95_ms)
        """
        stats = self.get_stats()
        p95 = stats["p95_ms"]
        if p95 == 0.0:
            return False, 0.0
        return p95 < p95_target_ms, p95

    @staticmethod
    def _percentile(sorted_data: list[float], pct: float) -> float:
        """Compute percentile from sorted data."""
        if not sorted_data:
            return 0.0
        index = (pct / 100.0) * (len(sorted_data) - 1)
        lower = int(index)
        upper = min(lower + 1, len(sorted_data) - 1)
        fraction = index - lower
        return sorted_data[lower] + fraction * (sorted_data[upper] - sorted_data[lower])


# Module-level singleton
_perf_monitor: RoutingPerfMonitor | None = None


def _get_perf_monitor() -> RoutingPerfMonitor:
    global _perf_monitor  # noqa: PLW0603
    if _perf_monitor is None:
        _perf_monitor = RoutingPerfMonitor()
    return _perf_monitor


def get_perf_monitor() -> RoutingPerfMonitor:
    """Get or create the global performance monitor."""
    return _get_perf_monitor()


def reset_perf_monitor() -> None:
    """Reset the global performance monitor (for testing)."""
    global _perf_monitor  # noqa: PLW0603
    _perf_monitor = None


__all__ = [
    "RouteTiming",
    "RoutingPerfMonitor",
    "get_perf_monitor",
]
