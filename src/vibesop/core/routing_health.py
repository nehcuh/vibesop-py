"""Routing health analyzer — reads analytics data and produces actionable insights.

Answers: "Is routing working well? Where are the problems? What should I optimize?"

Data sources:
    - ``.vibe/analytics.jsonl`` — per-route execution records
    - ``.vibe/ai_triage_log.jsonl`` — AI triage cost tracking
    - ``RoutingPerfMonitor`` — in-memory P50/P95/P99 latency

Output: structured health report with:
    - Hit rate (single-skill vs no-match vs fallback)
    - Latency distribution
    - Top routed skills
    - Missed query clusters
    - AI triage cost / effectiveness
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RoutingHealth:
    """Aggregated routing health metrics."""

    # Volume
    total_routes: int = 0
    routes_last_24h: int = 0
    routes_last_7d: int = 0

    # Hit classification
    single_skill_hits: int = 0  # routed to exactly 1 skill
    orchestrated_hits: int = 0  # multi-intent plan
    no_match: int = 0  # no skill matched
    fallback: int = 0  # FALLBACK_LLM sentinel
    errors: int = 0  # routing errors

    # Latency (ms) — noqa: ERA001
    avg_latency_ms: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0

    # Skills
    top_skills: list[tuple[str, int]] = field(default_factory=list)  # (skill_id, count)
    top_misses: list[tuple[str, int]] = field(default_factory=list)  # (query_hash, count)

    # AI Triage
    ai_triage_calls: int = 0
    ai_triage_cost_usd: float = 0.0
    ai_triage_success_rate: float = 0.0  # % of triage calls that produced a match

    # Layer distribution
    layer_breakdown: dict[str, int] = field(default_factory=dict)

    @property
    def hit_rate(self) -> float:
        total = self.single_skill_hits + self.orchestrated_hits + self.no_match
        if total == 0:
            return 0.0
        return (self.single_skill_hits + self.orchestrated_hits) / total

    @property
    def health_grade(self) -> str:
        """A-F grade based on hit rate."""
        if self.hit_rate >= 0.90:
            return "A"
        if self.hit_rate >= 0.80:
            return "B"
        if self.hit_rate >= 0.65:
            return "C"
        if self.hit_rate >= 0.50:
            return "D"
        return "F"


class RoutingHealthAnalyzer:
    """Analyzes routing analytics data and produces health reports."""

    def __init__(self, project_root: str | Path = ".") -> None:
        self._root = Path(project_root)
        self._analytics_path = self._root / ".vibe" / "analytics.jsonl"
        self._triage_log_path = self._root / ".vibe" / "ai_triage_log.jsonl"

    def analyze(self, days: int = 30) -> RoutingHealth:
        """Analyze routing data from the last N days."""
        health = RoutingHealth()
        now = datetime.now()

        # Parse analytics records
        records: list[dict[str, Any]] = []
        if self._analytics_path.exists():
            for line in self._analytics_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                    records.append(rec)
                except json.JSONDecodeError:
                    continue

        # Time filter
        cutoff = now - timedelta(days=days)
        filtered: list[dict[str, Any]] = []
        latencies: list[float] = []

        for rec in records:
            ts = rec.get("timestamp", "")
            try:
                rec_time = datetime.fromisoformat(ts)
            except (ValueError, TypeError):
                continue

            if rec_time < cutoff:
                continue

            filtered.append(rec)

            # Count routes in time windows
            health.total_routes += 1
            if rec_time > now - timedelta(hours=24):
                health.routes_last_24h += 1
            if rec_time > now - timedelta(days=7):
                health.routes_last_7d += 1

            # Hit classification
            mode = rec.get("mode", "single")
            primary = rec.get("primary_skill")
            if (
                primary == "FALLBACK_LLM"
                or rec.get("metadata", {}).get("degradation") == "fallback"
            ):
                health.fallback += 1
            elif primary is None:
                health.no_match += 1
            elif mode == "orchestrated":
                health.orchestrated_hits += 1
            else:
                health.single_skill_hits += 1

            # Latency
            duration = rec.get("duration_ms", 0)
            if duration > 0:
                latencies.append(duration)

            # Layer distribution
            for layer in rec.get("routing_layers", []):
                health.layer_breakdown[layer] = health.layer_breakdown.get(layer, 0) + 1

            # Errors
            if rec.get("metadata", {}).get("error"):
                health.errors += 1

        # Latency percentiles
        if latencies:
            sorted_lat = sorted(latencies)
            health.avg_latency_ms = sum(latencies) / len(latencies)
            health.p50_latency_ms = sorted_lat[len(sorted_lat) // 2]
            health.p95_latency_ms = sorted_lat[int(len(sorted_lat) * 0.95)]
            health.p99_latency_ms = sorted_lat[int(len(sorted_lat) * 0.99)]

        # Top skills
        skill_counts: Counter[str] = Counter()
        for rec in filtered:
            primary = rec.get("primary_skill")
            if primary and primary != "FALLBACK_LLM":
                skill_counts[primary] += 1
        health.top_skills = skill_counts.most_common(10)

        # AI Triage stats
        if self._triage_log_path.exists():
            for line in self._triage_log_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                    ts = rec.get("timestamp", "")
                    rec_time = datetime.fromisoformat(ts)
                    if rec_time < cutoff:
                        continue
                    health.ai_triage_calls += 1
                    health.ai_triage_cost_usd += rec.get("estimated_cost_usd", 0)
                    if rec.get("selected_skill"):
                        health.ai_triage_success_rate = (
                            health.ai_triage_success_rate * (health.ai_triage_calls - 1) + 1
                        ) / health.ai_triage_calls
                except (json.JSONDecodeError, ValueError, TypeError):
                    continue

        return health

    def get_actionable_insights(self, health: RoutingHealth) -> list[str]:
        """Generate actionable recommendations from health data."""
        insights: list[str] = []

        if health.hit_rate < 0.80:
            insights.append(
                f"Hit rate is {health.hit_rate:.0%} (grade {health.health_grade}). "
                "Consider adding skills for frequently-missed queries."
            )

        if health.fallback > health.total_routes * 0.1:
            insights.append(
                f"{health.fallback} fallback routes ({health.fallback / health.total_routes:.0%}). "
                "AI triage is being relied on heavily — check if keyword matching needs tuning."
            )

        if health.p95_latency_ms > 500:
            insights.append(
                f"P95 latency is {health.p95_latency_ms:.0f}ms. "
                "Consider disabling embedding matching or reducing skill count."
            )

        if health.ai_triage_cost_usd > 1.0:
            insights.append(
                f"AI triage cost ${health.ai_triage_cost_usd:.2f} over period. "
                "High cost may indicate keyword matching isn't covering common queries."
            )

        if health.no_match > health.total_routes * 0.15:
            insights.append(
                f"{health.no_match} unmatched queries ({health.no_match / health.total_routes:.0%}). "
                "Run 'vibe skills suggest' to generate skills for missed query clusters."
            )

        if not insights:
            insights.append("Routing health looks good! No urgent actions needed.")

        return insights
