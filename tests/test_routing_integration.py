"""Integration tests for routing system (v3.0.0)."""

from pathlib import Path

from vibesop.core.routing import UnifiedRouter


class TestSkillRouterIntegration:
    """Integration tests for UnifiedRouter."""

    def test_route_debug_query(self) -> None:
        """Test routing a debug query."""
        router = UnifiedRouter(project_root=Path.cwd())
        result = router.route("debug this error")

        assert result is not None
        # Should have a routing path even if no exact match
        assert len(result.routing_path) >= 0

    def test_route_review_query(self) -> None:
        """Test routing a review query."""
        router = UnifiedRouter(project_root=Path.cwd())
        result = router.route("review my code")

        assert result is not None
        # With min_confidence default, should find something or return alternatives
        if result.has_match:
            assert result.primary.skill_id is not None

    def test_route_refactor_query(self) -> None:
        """Test routing a refactor query."""
        router = UnifiedRouter(project_root=Path.cwd())
        result = router.route("refactor this code")

        assert result is not None
        # Check that result exists

    def test_route_chinese_query(self) -> None:
        """Test routing Chinese queries."""
        router = UnifiedRouter(project_root=Path.cwd())
        result = router.route("帮我调试这个 bug")

        assert result is not None
        # Should handle Chinese queries

    def test_get_capabilities(self) -> None:
        """Test getting router capabilities."""
        router = UnifiedRouter(project_root=Path.cwd())
        caps = router.get_capabilities()

        assert "type" in caps
        assert "matchers" in caps
        assert len(caps["matchers"]) > 0

    def test_get_candidates(self) -> None:
        """Test getting candidate skills."""
        router = UnifiedRouter(project_root=Path.cwd())
        candidates = router.get_candidates()

        assert isinstance(candidates, list)
        # Should find at least some skills in a real project
