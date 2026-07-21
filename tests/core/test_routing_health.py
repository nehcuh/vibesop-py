"""Tests for routing_health.py."""

from pathlib import Path

from vibesop.core.routing_health import RoutingHealth, RoutingHealthAnalyzer


class TestRoutingHealth:
    def test_hit_rate_perfect(self):
        h = RoutingHealth(single_skill_hits=100, total_routes=100)
        assert h.hit_rate == 1.0
        assert h.health_grade == "A"

    def test_hit_rate_mixed(self):
        h = RoutingHealth(single_skill_hits=60, orchestrated_hits=20, no_match=20, total_routes=100)
        assert h.hit_rate == 0.8
        assert h.health_grade == "B"

    def test_hit_rate_poor(self):
        h = RoutingHealth(single_skill_hits=30, no_match=70, total_routes=100)
        assert h.hit_rate == 0.3
        assert h.health_grade == "F"

    def test_empty_no_division_by_zero(self):
        h = RoutingHealth()
        assert h.hit_rate == 0.0
        assert h.health_grade == "F"

    def test_latency_percentiles(self):
        h = RoutingHealth(
            avg_latency_ms=100.0, p50_latency_ms=80.0, p95_latency_ms=200.0, p99_latency_ms=500.0
        )
        assert h.avg_latency_ms == 100.0
        assert h.p95_latency_ms == 200.0

    def test_top_skills(self):
        h = RoutingHealth(top_skills=[("debug", 10), ("review", 5)])
        assert len(h.top_skills) == 2
        assert h.top_skills[0] == ("debug", 10)

    def test_layer_breakdown(self):
        h = RoutingHealth(layer_breakdown={"explicit": 5, "keyword": 20})
        assert h.layer_breakdown["keyword"] == 20


class TestRoutingHealthAnalyzer:
    def test_empty_project_returns_zeroes(self, tmp_path: Path):
        analyzer = RoutingHealthAnalyzer(tmp_path)
        health = analyzer.analyze()
        assert health.total_routes == 0
        assert health.health_grade == "F"

    def test_insights_for_healthy_routing(self):
        h = RoutingHealth(single_skill_hits=90, orchestrated_hits=5, no_match=5, total_routes=100)
        analyzer = RoutingHealthAnalyzer(".")
        insights = analyzer.get_actionable_insights(h)
        assert "looks good" in insights[0]

    def test_insights_for_poor_routing(self):
        h = RoutingHealth(
            single_skill_hits=30,
            no_match=50,
            fallback=20,
            total_routes=100,
            p95_latency_ms=600,
            ai_triage_cost_usd=5.0,
        )
        analyzer = RoutingHealthAnalyzer(".")
        insights = analyzer.get_actionable_insights(h)
        assert len(insights) >= 2  # Multiple issues should be flagged
