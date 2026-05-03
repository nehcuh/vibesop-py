"""Tests for integration recommendation system."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from vibesop.integrations import (
    IntegrationRecommender,
    Recommendation,
    RecommendationPriority,
)


class TestRecommendationPriority:
    """Test RecommendationPriority enum."""

    def test_priority_values(self) -> None:
        """Test priority enum values."""
        assert RecommendationPriority.HIGH.value == "high"
        assert RecommendationPriority.MEDIUM.value == "medium"
        assert RecommendationPriority.LOW.value == "low"


class TestRecommendation:
    """Test Recommendation dataclass."""

    def test_create_recommendation(self) -> None:
        """Test creating a recommendation."""
        rec = Recommendation(
            integration_id="gstack",
            name="Gstack",
            description="Virtual engineering team",
            priority=RecommendationPriority.HIGH,
            reason="Essential for code review",
            confidence=0.95,
            skills=["review", "qa"],
        )
        assert rec.integration_id == "gstack"
        assert rec.name == "Gstack"
        assert rec.priority == RecommendationPriority.HIGH
        assert rec.confidence == 0.95
        assert len(rec.skills) == 2


class TestIntegrationRecommender:
    """Test IntegrationRecommender functionality."""

    def test_create_recommender(self) -> None:
        """Test creating recommender."""
        recommender = IntegrationRecommender()
        assert recommender is not None

    def test_recommend_empty_context(self) -> None:
        """Test recommendations with empty context."""
        recommender = IntegrationRecommender()
        recommendations = recommender.recommend({})

        # Should return recommendations (even with empty context)
        assert isinstance(recommendations, list)

    def test_recommend_software_development(self) -> None:
        """Test recommendations for software development use case."""
        recommender = IntegrationRecommender()
        recommendations = recommender.recommend(
            {"use_case": "software-development"},
            max_recommendations=5,
        )

        assert isinstance(recommendations, list)
        # Check that high priority recommendations are present
        high_priority = [r for r in recommendations if r.priority == RecommendationPriority.HIGH]
        assert len(high_priority) > 0

    def test_recommend_code_review(self) -> None:
        """Test recommendations for code review use case."""
        recommender = IntegrationRecommender()
        recommendations = recommender.recommend(
            {"use_case": "code-review"},
            max_recommendations=5,
        )

        assert isinstance(recommendations, list)
        # Should recommend gstack for code review
        gstack_recs = [r for r in recommendations if r.integration_id == "gstack"]
        if len(gstack_recs) > 0:
            assert gstack_recs[0].priority == RecommendationPriority.HIGH

    def test_recommend_brainstorming(self) -> None:
        """Test recommendations for brainstorming use case."""
        recommender = IntegrationRecommender()
        recommendations = recommender.recommend(
            {"use_case": "brainstorming"},
            max_recommendations=5,
        )

        assert isinstance(recommendations, list)
        # Should recommend superpowers for brainstorming
        superpowers_recs = [r for r in recommendations if r.integration_id == "superpowers"]
        if len(superpowers_recs) > 0:
            assert superpowers_recs[0].priority == RecommendationPriority.MEDIUM

    def test_recommend_max_limit(self) -> None:
        """Test that max_recommendations is respected."""
        recommender = IntegrationRecommender()
        recommendations = recommender.recommend(
            {"use_case": "software-development"},
            max_recommendations=2,
        )

        assert len(recommendations) <= 2

    def test_recommend_confidence_range(self) -> None:
        """Test that confidence scores are in valid range."""
        recommender = IntegrationRecommender()
        recommendations = recommender.recommend({"use_case": "software-development"})

        for rec in recommendations:
            assert 0.0 <= rec.confidence <= 1.0

    def test_priority_from_confidence(self) -> None:
        """Test that priority is correctly derived from confidence."""
        recommender = IntegrationRecommender()
        recommendations = recommender.recommend(
            {"use_case": "software-development"},
            max_recommendations=10,
        )

        for rec in recommendations:
            if rec.confidence >= 0.75:  # HIGH: score >= 0.75
                assert rec.priority == RecommendationPriority.HIGH
            elif rec.confidence >= 0.5:  # MEDIUM: score >= 0.5
                assert rec.priority == RecommendationPriority.MEDIUM
            else:  # LOW: score < 0.5
                assert rec.priority == RecommendationPriority.LOW

    def test_get_compatibility_report_empty(self) -> None:
        """Test compatibility report with no integrations."""
        recommender = IntegrationRecommender()
        report = recommender.get_compatibility_report([], "claude-code")

        assert report["compatible"] == []
        assert report["incompatible"] == []
        assert report["warnings"] == []
        assert report["platform"] == "claude-code"

    def test_get_compatibility_report_known_integration(self) -> None:
        """Test compatibility report for known integration."""
        recommender = IntegrationRecommender()
        report = recommender.get_compatibility_report(["gstack"], "claude-code")

        # gstack is compatible with claude-code
        assert "gstack" in report["compatible"]
        assert len(report["incompatible"]) == 0

    def test_get_compatibility_report_unknown_integration(self) -> None:
        """Test compatibility report for unknown integration."""
        recommender = IntegrationRecommender()
        report = recommender.get_compatibility_report(["unknown-integration"], "claude-code")

        assert len(report["incompatible"]) == 1
        assert report["incompatible"][0]["integration_id"] == "unknown-integration"
        assert "Unknown integration" in report["incompatible"][0]["reason"]

    def test_generate_setup_plan_empty(self) -> None:
        """Test setup plan generation with no recommendations."""
        recommender = IntegrationRecommender()

        with tempfile.TemporaryDirectory() as tmpdir:
            plan = recommender.generate_setup_plan([], "claude-code", Path(tmpdir))

            assert plan["platform"] == "claude-code"
            assert plan["integrations"] == []
            assert plan["steps"] == []
            assert plan["estimated_time"] == 0
            assert len(plan["errors"]) == 0

    def test_generate_setup_plan_with_recommendations(self) -> None:
        """Test setup plan generation with recommendations."""
        recommender = IntegrationRecommender()

        # Create mock recommendations
        recommendations = [
            Recommendation(
                integration_id="gstack",
                name="Gstack",
                description="Virtual engineering team",
                priority=RecommendationPriority.HIGH,
                reason="Essential for code review",
                confidence=0.9,
                skills=["review", "qa"],
            ),
            Recommendation(
                integration_id="superpowers",
                name="Superpowers",
                description="Productivity skills",
                priority=RecommendationPriority.MEDIUM,
                reason="Nice to have",
                confidence=0.7,
                skills=["brainstorm"],
            ),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            plan = recommender.generate_setup_plan(recommendations, "claude-code", Path(tmpdir))

            assert plan["platform"] == "claude-code"
            assert len(plan["integrations"]) == 2
            assert len(plan["steps"]) == 2

            # Check high priority integration
            high_rec = plan["integrations"][0]
            assert high_rec["id"] == "gstack"
            assert high_rec["priority"] == "high"

            # Check medium priority integration
            medium_rec = plan["integrations"][1]
            assert medium_rec["id"] == "superpowers"
            assert medium_rec["priority"] == "medium"

            # Check installation steps
            assert plan["steps"][0]["action"] == "install"
            assert "gstack" in plan["steps"][0]["command"]
            assert plan["steps"][1]["action"] == "install"
            assert "superpowers" in plan["steps"][1]["command"]

            # Check estimated time
            assert plan["estimated_time"] > 0

    def test_score_integration_platform_preference(self) -> None:
        """Test that platform preference affects scoring."""
        recommender = IntegrationRecommender()

        # Test with platform preference
        score_with_platform = recommender._score_integration(
            "gstack",
            MagicMock(status="not_installed"),
            {"platform": "claude-code", "use_case": "software-development"},
        )

        # Test without platform preference
        score_without_platform = recommender._score_integration(
            "gstack",
            MagicMock(status="not_installed"),
            {"use_case": "software-development"},
        )

        # Platform preference should increase score
        assert score_with_platform > score_without_platform

    def test_score_integration_testing_preference(self) -> None:
        """Test that testing preference affects scoring."""
        recommender = IntegrationRecommender()

        # Test with testing preference
        score_with_testing = recommender._score_integration(
            "gstack",
            MagicMock(status="not_installed"),
            {
                "use_case": "software-development",
                "preferences": {"include_testing": True},
            },
        )

        # Test without testing preference
        score_without_testing = recommender._score_integration(
            "gstack",
            MagicMock(status="not_installed"),
            {"use_case": "software-development"},
        )

        # Testing preference should increase score for gstack
        assert score_with_testing > score_without_testing

    def test_score_integration_brainstorming_preference(self) -> None:
        """Test that brainstorming preference affects scoring."""
        recommender = IntegrationRecommender()

        # Test with brainstorming preference
        score_with_brainstorming = recommender._score_integration(
            "superpowers",
            MagicMock(status="not_installed"),
            {
                "use_case": "software-development",
                "preferences": {"include_brainstorming": True},
            },
        )

        # Test without brainstorming preference
        score_without_brainstorming = recommender._score_integration(
            "superpowers",
            MagicMock(status="not_installed"),
            {"use_case": "software-development"},
        )

        # Brainstorming preference should increase score for superpowers
        assert score_with_brainstorming > score_without_brainstorming

    def test_get_recommendation_reason_known_use_case(self) -> None:
        """Test getting recommendation reason for known use case."""
        recommender = IntegrationRecommender()
        reason = recommender._get_recommendation_reason(
            "gstack",
            {"use_case": "code-review"},
        )
        assert "specialized code review" in reason.lower()

    def test_get_recommendation_reason_default(self) -> None:
        """Test getting default recommendation reason."""
        recommender = IntegrationRecommender()
        reason = recommender._get_recommendation_reason(
            "gstack",
            {"use_case": "unknown"},
        )
        assert "engineering team" in reason.lower() or "code review" in reason.lower()

    def test_estimate_install_time_known(self) -> None:
        """Test estimating install time for known integration."""
        recommender = IntegrationRecommender()
        time = recommender._estimate_install_time("gstack")
        assert time > 0
        assert isinstance(time, int)

    def test_estimate_install_time_unknown(self) -> None:
        """Test estimating install time for unknown integration."""
        recommender = IntegrationRecommender()
        time = recommender._estimate_install_time("unknown")
        # Should return default time
        assert time > 0

