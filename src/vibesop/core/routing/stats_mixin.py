"""Router statistics and preference tracking mixin.

Extracted from UnifiedRouter to reduce class size and separate concerns.
"""

from __future__ import annotations

from typing import Any

from vibesop.core.models import RoutingLayer


class RouterStatsMixin:
    """Mixin providing routing statistics and preference tracking methods.

    Intended for use with UnifiedRouter. Expects the following attributes
    on the host class:
        - _total_routes: int
        - _layer_distribution: dict[str, int]
        - _stats_lock: threading.Lock
        - _cost_tracker: TriageCostTracker
        - _config: RoutingConfig
        - _preference_booster: PreferenceBooster
        - project_root: Path
    """

    def _record_layer(self, layer: RoutingLayer) -> None:
        with self._stats_lock:  # type: ignore[attr-defined]
            dist = self._layer_distribution  # type: ignore[attr-defined]
            dist[layer.value] = dist.get(layer.value, 0) + 1

    def get_stats(self) -> dict[str, Any]:
        from vibesop.core.routing.perf_monitor import get_perf_monitor

        perf = get_perf_monitor().get_stats()

        with self._stats_lock:  # type: ignore[attr-defined]
            total_routes = self._total_routes  # type: ignore[attr-defined]
            layer_dist = dict(self._layer_distribution)  # type: ignore[attr-defined]

        return {
            "total_routes": total_routes,
            "layer_distribution": layer_dist,
            "cache_dir": str(self.project_root / ".vibe" / "cache"),  # type: ignore[attr-defined]
            "ai_triage": self.get_ai_triage_stats(),
            "performance": {
                "window_size": perf["window_size"],
                "p50_ms": perf["p50_ms"],
                "p95_ms": perf["p95_ms"],
                "p99_ms": perf["p99_ms"],
                "avg_ms": perf["avg_ms"],
                "p95_on_target": perf["p95_ms"] < 100.0,
            },
        }

    def get_ai_triage_stats(self) -> dict[str, Any]:
        """Get AI Triage usage and cost statistics."""
        stats = self._cost_tracker.get_stats(days=30)  # type: ignore[attr-defined]
        budget = getattr(self._config, "ai_triage_budget_monthly", 5.0)  # type: ignore[attr-defined]
        return {
            **stats,
            "budget_monthly_usd": budget,
            "budget_remaining_usd": round(max(0.0, budget - stats["total_cost_usd"]), 6),
        }

    def record_selection(self, skill_id: str, query: str, was_helpful: bool = True) -> None:
        learner = self._preference_booster.get_learner()  # type: ignore[attr-defined]
        learner.record_selection(skill_id, query, was_helpful)

    def get_preference_stats(self) -> dict[str, int | float | str]:
        learner = self._preference_booster.get_learner()  # type: ignore[attr-defined]
        return learner.get_stats()

    def get_top_skills(self, limit: int = 5, min_selections: int = 2) -> list[Any]:
        learner = self._preference_booster.get_learner()  # type: ignore[attr-defined]
        return learner.get_top_skills(limit, min_selections)

    def clear_old_preferences(self, days: int = 90) -> int:
        learner = self._preference_booster.get_learner()  # type: ignore[attr-defined]
        return learner.clear_old_data(days)
