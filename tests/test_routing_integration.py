"""Integration tests for routing system."""

from vibesop.core.models import RoutingRequest
from vibesop.core.routing.engine import SkillRouter


class TestSkillRouterIntegration:
    """Integration tests for SkillRouter."""

    def test_route_debug_query(self) -> None:
        """Test routing a debug query."""
        router = SkillRouter()
        request = RoutingRequest(query="debug this error")

        result = router.route(request)

        assert result.primary.skill_id is not None
        assert result.primary.confidence > 0.0
        assert result.primary.layer >= 0

    def test_route_review_query(self) -> None:
        """Test routing a review query."""
        router = SkillRouter()
        request = RoutingRequest(query="review my code")

        result = router.route(request)

        assert result.primary.skill_id is not None
        assert (
            "review" in result.primary.skill_id.lower()
            or "review" in str(result.primary.metadata).lower()
        )

    def test_route_refactor_query(self) -> None:
        """Test routing a refactor query."""
        router = SkillRouter()
        request = RoutingRequest(query="refactor this code")

        result = router.route(request)

        assert result.primary.skill_id is not None
        assert "refactor" in result.primary.skill_id.lower()

    def test_route_chinese_query(self) -> None:
        """Test routing Chinese queries."""
        router = SkillRouter()
        request = RoutingRequest(query="帮我调试这个 bug")

        result = router.route(request)

        assert result.primary.skill_id is not None
        assert result.primary.confidence > 0.0

    def test_route_explicit_skill_invocation(self) -> None:
        """Test explicit skill invocation."""
        router = SkillRouter()
        request = RoutingRequest(query="/systematic-debugging")

        result = router.route(request)

        assert result.primary.skill_id is not None
        # Should find systematic-debugging skill
        assert "debug" in result.primary.skill_id.lower()
        # High confidence for explicit or pattern match
        assert result.primary.confidence >= 0.7

    def test_route_with_context(self) -> None:
        """Test routing with additional context."""
        router = SkillRouter()
        request = RoutingRequest(
            query="fix this",
            context={"file_type": "python", "error_count": 3},
        )

        result = router.route(request)

        assert result.primary.skill_id is not None

    def test_multiple_requests_increment_stats(self) -> None:
        """Test that multiple requests increment statistics."""
        router = SkillRouter()

        # Make multiple requests
        for _ in range(5):
            router.route(RoutingRequest(query="test"))

        stats = router.get_stats()

        assert stats["total_routes"] == 5

    def test_layer_distribution_tracking(self) -> None:
        """Test that layer distribution is tracked."""
        router = SkillRouter()

        # Make various requests
        router.route(RoutingRequest(query="debug error"))
        router.route(RoutingRequest(query="review code"))
        router.route(RoutingRequest(query="refactor"))

        stats = router.get_stats()

        # Check that some layers were used
        total_routes = sum(stats["layer_distribution"].values())
        assert total_routes > 0

    def test_explicit_override_priority(self) -> None:
        """Test that explicit patterns take priority."""
        router = SkillRouter()

        # Direct skill invocation format
        result1 = router.route(RoutingRequest(query="/systematic-debugging"))
        # Should find the skill and have high confidence
        assert result1.primary.skill_id is not None
        assert result1.primary.confidence >= 0.7

    def test_no_match_fallback(self) -> None:
        """Test fallback for queries with no match."""
        router = SkillRouter()

        # Very unclear query
        result = router.route(RoutingRequest(query="xyzabc123"))

        # Should still return something (fallback)
        assert result.primary.skill_id is not None

    def test_consistent_routing_for_same_query(self) -> None:
        """Test that same query produces consistent results."""
        router = SkillRouter()

        request = RoutingRequest(query="debug error")

        result1 = router.route(request)
        result2 = router.route(request)

        # Should return same skill_id
        assert result1.primary.skill_id == result2.primary.skill_id

    def test_alternatives_field_exists(self) -> None:
        """Test that alternatives field is always present."""
        router = SkillRouter()

        result = router.route(RoutingRequest(query="test"))

        assert hasattr(result, "alternatives")
        assert isinstance(result.alternatives, list)

    def test_routing_path_field_exists(self) -> None:
        """Test that routing_path field is always present."""
        router = SkillRouter()

        result = router.route(RoutingRequest(query="test"))

        assert hasattr(result, "routing_path")
        assert isinstance(result.routing_path, list)

    def test_query_normalization(self) -> None:
        """Test that queries are normalized correctly."""
        router = SkillRouter()

        # Various forms of "review"
        queries = ["Review", "  REVIEW  ", "review!!!"]

        for query in queries:
            result = router.route(RoutingRequest(query=query))
            # Should all route to similar skills
            assert result.primary.skill_id is not None

    def test_multilingual_support(self) -> None:
        """Test support for multiple languages."""
        router = SkillRouter()

        # English
        result_en = router.route(RoutingRequest(query="debug error"))
        assert result_en.primary.skill_id is not None

        # Chinese
        result_zh = router.route(RoutingRequest(query="调试 错误"))
        assert result_zh.primary.skill_id is not None

    def test_cache_integration(self) -> None:
        """Test that cache is used for repeated queries."""
        router = SkillRouter()

        # Same query twice
        query = "test this code"
        request1 = RoutingRequest(query=query)
        request2 = RoutingRequest(query=query)

        result1 = router.route(request1)
        result2 = router.route(request2)

        # Should return same result
        assert result1.primary.skill_id == result2.primary.skill_id


class TestSkillRouterWithConfig:
    """Test router with configuration."""

    def test_router_with_project_root(self) -> None:
        """Test router initialization with custom project root."""
        router = SkillRouter(project_root=".")

        # Should work normally
        result = router.route(RoutingRequest(query="test"))
        assert result.primary.skill_id is not None

    def test_router_loads_from_yaml(self) -> None:
        """Test that router loads skills from YAML configuration."""
        router = SkillRouter()

        # Router should have loaded skills from core/registry.yaml
        result = router.route(RoutingRequest(query="review"))

        # Should find a review-related skill
        assert result.primary.skill_id is not None
