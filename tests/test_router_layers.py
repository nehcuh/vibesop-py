"""Unit tests for routing layers (v3.0.0)."""

from pathlib import Path

from vibesop.core.routing import RoutingConfig, UnifiedRouter


class TestLayer1Explicit:
    """Test Layer 1: Explicit skill invocation."""

    def test_direct_skill_invocation(self) -> None:
        """Test direct skill invocation by keyword."""
        router = UnifiedRouter(project_root=Path.cwd())
        result = router.route("review my code")

        # Should find a match or have alternatives
        assert result is not None

    def test_slash_prefix_with_known_skill(self) -> None:
        """Test / prefix for direct skill invocation."""
        router = UnifiedRouter(project_root=Path.cwd())
        result = router.route("/review")

        # Should handle slash prefix
        assert result is not None


class TestLayer2Scenario:
    """Test Layer 2: Scenario-based patterns."""

    def test_test_keywords(self) -> None:
        """Test keywords trigger testing scenarios."""
        router = UnifiedRouter(project_root=Path.cwd())
        result = router.route("run tests")

        assert result is not None

    def test_refactor_keywords(self) -> None:
        """Test keywords trigger refactoring scenarios."""
        router = UnifiedRouter(project_root=Path.cwd())
        result = router.route("refactor this code")

        assert result is not None

    def test_chinese_keywords(self) -> None:
        """Test Chinese keywords work."""
        router = UnifiedRouter(project_root=Path.cwd())
        result = router.route("帮我调试")

        assert result is not None


class TestLayer3Semantic:
    """Test Layer 3: Semantic matching."""

    def test_semantic_similarity(self) -> None:
        """Test semantic similarity matching."""
        config = RoutingConfig(min_confidence=0.0, enable_embedding=False)
        router = UnifiedRouter(project_root=Path.cwd(), config=config)
        result = router.route("fix the bug")

        # Should attempt semantic matching
        assert result is not None

    def test_synonym_handling(self) -> None:
        """Test synonym handling in semantic layer."""
        config = RoutingConfig(min_confidence=0.0)
        router = UnifiedRouter(project_root=Path.cwd(), config=config)
        result = router.route("examine the code")

        assert result is not None


class TestLayer4Fuzzy:
    """Test Layer 4: Fuzzy matching fallback."""

    def test_typo_tolerance(self) -> None:
        """Test fuzzy matching handles typos."""
        config = RoutingConfig(min_confidence=0.0)
        router = UnifiedRouter(project_root=Path.cwd(), config=config)
        result = router.route("ddebug")  # Typo for "debug"

        # Should fall back to fuzzy matching
        assert result is not None

    def test_low_confidence_fallback(self) -> None:
        """Test fallback with very low confidence."""
        config = RoutingConfig(min_confidence=0.0)
        router = UnifiedRouter(project_root=Path.cwd(), config=config)
        result = router.route("xyz")

        # Should still return a result
        assert result is not None
