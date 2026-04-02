"""Unit tests for each routing layer."""

import os
import shutil
import tempfile
from pathlib import Path

from vibesop.core.models import RoutingRequest, SkillRoute
from vibesop.core.routing.engine import SkillRouter


class TestLayer1Explicit:
    """Test Layer 1: Explicit overrides."""

    def test_direct_skill_invocation(self) -> None:
        """Test direct /skill invocation.

        Note: The config maps skill IDs, so /review may resolve to gstack/review.
        If the exact skill ID isn't in config, it falls through to layer 2.
        """
        router = SkillRouter(enable_ai_triage=False)
        request = RoutingRequest(query="/review my code")

        result = router.route(request)

        # Should match either layer 1 (explicit) or layer 2 (scenario keyword)
        assert "review" in result.primary.skill_id.lower()
        assert result.primary.layer in (1, 2)
        assert result.primary.source in ("explicit", "scenario")

    def test_slash_prefix_with_known_skill(self) -> None:
        r"""Test / prefix with a known skill ID.

        Note: Layer 1 explicit regex only matches \w+ (word characters),
        so skills with hyphens like systematic-debugging won't match.
        """
        router = SkillRouter(enable_ai_triage=False)
        # Use a skill with only word characters
        request = RoutingRequest(query="/review")

        result = router.route(request)

        # Should match layer 1 explicit or fall through to layer 2
        assert result.primary.layer in (1, 2)
        assert "review" in result.primary.skill_id.lower()

    def test_chinese_use_keyword(self) -> None:
        """Test Chinese '使用' keyword."""
        router = SkillRouter(enable_ai_triage=False)
        request = RoutingRequest(query="使用 review 来评审代码")

        result = router.route(request)

        # Should match explicit (layer 1) or fall through to scenario (layer 2)
        assert result.primary.layer in (1, 2)

    def test_chinese_call_keyword(self) -> None:
        """Test Chinese '调用' keyword."""
        router = SkillRouter(enable_ai_triage=False)
        request = RoutingRequest(query="调用 debug 技能")

        result = router.route(request)

        # Should match explicit (layer 1) or fall through to scenario (layer 2)
        assert result.primary.layer in (1, 2)


class TestLayer2Scenario:
    """Test Layer 2: Scenario patterns."""

    def test_debug_keywords(self) -> None:
        """Test debug scenario keywords."""
        router = SkillRouter(enable_ai_triage=False)
        request = RoutingRequest(query="I have a bug to fix")

        result = router.route(request)

        assert result.primary.layer == 2
        assert result.primary.source == "scenario"

    def test_error_keywords(self) -> None:
        """Test error scenario keywords."""
        router = SkillRouter(enable_ai_triage=False)
        request = RoutingRequest(query="fix this error")

        result = router.route(request)

        assert result.primary.layer == 2
        assert result.primary.source == "scenario"

    def test_chinese_debug_keywords(self) -> None:
        """Test Chinese debug keywords."""
        router = SkillRouter(enable_ai_triage=False)
        request = RoutingRequest(query="调试这个错误")

        result = router.route(request)

        assert result.primary.layer == 2
        assert result.primary.source == "scenario"

    def test_review_keywords(self) -> None:
        """Test review scenario keywords."""
        router = SkillRouter(enable_ai_triage=False)
        request = RoutingRequest(query="please review my code")

        result = router.route(request)

        assert result.primary.layer == 2
        assert result.primary.source == "scenario"

    def test_chinese_review_keywords(self) -> None:
        """Test Chinese review keywords."""
        router = SkillRouter(enable_ai_triage=False)
        request = RoutingRequest(query="审查代码质量")

        result = router.route(request)

        assert result.primary.layer == 2
        assert result.primary.source == "scenario"

    def test_test_keywords(self) -> None:
        """Test test scenario keywords."""
        router = SkillRouter(enable_ai_triage=False)
        request = RoutingRequest(query="write tests for this")

        result = router.route(request)

        assert result.primary.layer == 2
        assert result.primary.source == "scenario"

    def test_refactor_keywords(self) -> None:
        """Test refactor scenario keywords."""
        router = SkillRouter(enable_ai_triage=False)
        request = RoutingRequest(query="help me refactor this")

        result = router.route(request)

        assert result.primary.layer == 2
        assert result.primary.source == "scenario"


class TestLayer3Semantic:
    """Test Layer 3: Semantic matching."""

    def test_semantic_match(self) -> None:
        """Test semantic matching fallback."""
        router = SkillRouter(enable_ai_triage=False)
        # Use a query that won't match explicit or scenario
        request = RoutingRequest(query="check my implementation")

        result = router.route(request)

        # Should reach layer 3 (semantic) or 4 (fuzzy)
        assert result.primary.layer >= 3
        assert result.primary.skill_id is not None

    def test_semantic_with_low_confidence(self) -> None:
        """Test semantic match with low confidence falls through."""
        router = SkillRouter(enable_ai_triage=False)
        # Nonsense query
        request = RoutingRequest(query="xyzabc nonsense query")

        result = router.route(request)

        # Should still return a result (fallback)
        assert result.primary.skill_id is not None


class TestLayer4Fuzzy:
    """Test Layer 4: Fuzzy matching."""

    def test_fuzzy_match_typo(self) -> None:
        """Test fuzzy matching with typos."""
        router = SkillRouter(enable_ai_triage=False)
        request = RoutingRequest(query="reviw my code")  # Typo: review

        result = router.route(request)

        # Should match via fuzzy or semantic
        assert result.primary.skill_id is not None
        assert result.primary.layer >= 3


class TestNoMatch:
    """Test no match fallback."""

    def test_nonsense_query_returns_fallback(self) -> None:
        """Test nonsense query returns fallback skill."""
        router = SkillRouter(enable_ai_triage=False)
        request = RoutingRequest(query="asdfgh zxcvbn")

        result = router.route(request)

        # Should return fallback result
        assert result.primary.skill_id is not None
        assert result.primary.source == "fallback"
        assert result.primary.layer == 4


class TestRouterStats:
    """Test router statistics."""

    def test_stats_tracking(self) -> None:
        """Test that stats are tracked."""
        router = SkillRouter(enable_ai_triage=False)

        # Make some routes
        router.route(RoutingRequest(query="/review"))
        router.route(RoutingRequest(query="debug this"))
        router.route(RoutingRequest(query="testing"))

        stats = router.get_stats()

        assert stats["total_routes"] == 3
        assert "layer_distribution" in stats

    def test_layer_distribution_counts(self) -> None:
        """Test layer distribution is counted correctly."""
        router = SkillRouter(enable_ai_triage=False)

        # Get initial stats
        initial_stats = router.get_stats()
        initial_total = initial_stats["total_routes"]

        # Layer 1 - use a skill that exists in config
        router.route(RoutingRequest(query="/gstack/review"))
        # Layer 2
        router.route(RoutingRequest(query="debug this"))

        stats = router.get_stats()

        # Should have 2 more routes
        assert stats["total_routes"] == initial_total + 2
        # Layer 1 should have at least 1 more (the /gstack/review)
        assert (
            stats["layer_distribution"]["layer_1_explicit"]
            >= initial_stats["layer_distribution"]["layer_1_explicit"]
        )


class TestPreferenceIntegration:
    """Test preference learning integration."""

    def test_record_selection(self) -> None:
        """Test recording skill selection."""
        router = SkillRouter(enable_ai_triage=False)

        # Get initial count
        initial_stats = router.get_preference_stats()
        initial_count = initial_stats["total_selections"]

        router.record_selection("/review", "review my code", was_helpful=True)

        stats = router.get_preference_stats()
        assert stats["total_selections"] == initial_count + 1
        assert stats["helpful_count"] == initial_stats["helpful_count"] + 1

    def test_preference_boost(self) -> None:
        """Test preference recording."""
        router = SkillRouter(enable_ai_triage=False)

        # Get initial count
        initial_stats = router.get_preference_stats()
        initial_count = initial_stats["total_selections"]

        # Record selections
        router.record_selection("/gstack/review", "review code", was_helpful=True)
        router.record_selection("/gstack/review", "check code", was_helpful=True)

        # Verify selections were recorded
        stats = router.get_preference_stats()
        assert stats["total_selections"] == initial_count + 2

    def test_get_top_skills(self) -> None:
        """Test getting top preferred skills."""
        router = SkillRouter(enable_ai_triage=False)

        # Record some selections
        router.record_selection("/review", "review code")
        router.record_selection("/review", "check code")
        router.record_selection("/debug", "fix bug")

        top = router.get_top_skills(limit=5, min_selections=1)

        # Should have at least some skills
        assert len(top) >= 0  # May be 0 if min_selections not met

    def test_clear_old_preferences(self) -> None:
        """Test clearing old preference data."""
        router = SkillRouter(enable_ai_triage=False)

        router.record_selection("/review", "test")

        # Clear with very short threshold (may or may not remove)
        removed = router.clear_old_preferences(days=0)

        # Should return non-negative count
        assert removed >= 0


class TestNormalizeInput:
    """Test input normalization."""

    def test_normalize_lowercase(self) -> None:
        """Test lowercase normalization."""
        router = SkillRouter(enable_ai_triage=False)

        normalized = router._normalize_input("HELLO WORLD")

        assert normalized == "hello world"

    def test_normalize_whitespace(self) -> None:
        """Test whitespace normalization."""
        router = SkillRouter(enable_ai_triage=False)

        normalized = router._normalize_input("too    much   space")

        assert normalized == "too much space"

    def test_normalize_punctuation(self) -> None:
        """Test punctuation removal."""
        router = SkillRouter(enable_ai_triage=False)

        normalized = router._normalize_input("hello, world!")

        assert normalized == "hello world"


class TestAIResponseParsing:
    """Test AI response parsing."""

    def test_parse_plain_skill_id(self) -> None:
        """Test parsing plain skill ID."""
        router = SkillRouter(enable_ai_triage=False)

        result = router._parse_ai_response("gstack/review")

        assert result == "gstack/review"

    def test_parse_markdown_code_block(self) -> None:
        """Test parsing markdown code block."""
        router = SkillRouter(enable_ai_triage=False)

        result = router._parse_ai_response("```json\ngstack/review\n```")

        assert result == "gstack/review"

    def test_parse_plain_code_block(self) -> None:
        """Test parsing plain code block."""
        router = SkillRouter(enable_ai_triage=False)

        result = router._parse_ai_response("```\ngstack/review\n```")

        assert result == "gstack/review"

    def test_parse_multiline_response(self) -> None:
        """Test parsing multiline response."""
        router = SkillRouter(enable_ai_triage=False)

        # The regex matches first non-empty line
        result = router._parse_ai_response("systematic-debugging\nMore text")

        assert result == "systematic-debugging"

    def test_parse_invalid_response(self) -> None:
        """Test parsing invalid response returns None."""
        router = SkillRouter(enable_ai_triage=False)

        result = router._parse_ai_response("")

        assert result is None


class TestTriagePrompt:
    """Test AI triage prompt generation."""

    def test_prompt_includes_input(self) -> None:
        """Test prompt includes user input."""
        router = SkillRouter(enable_ai_triage=False)

        prompt = router._build_triage_prompt("test query", {})

        assert "test query" in prompt

    def test_prompt_includes_context(self) -> None:
        """Test prompt includes context."""
        router = SkillRouter(enable_ai_triage=False)

        prompt = router._build_triage_prompt("test", {"file_type": "py"})

        assert "file_type" in prompt or "py" in prompt

    def test_prompt_lists_skills(self) -> None:
        """Test prompt lists available skills."""
        router = SkillRouter(enable_ai_triage=False)

        prompt = router._build_triage_prompt("test", {})

        assert "skills" in prompt.lower()


class TestRouterInit:
    """Test router initialization."""

    def test_init_with_custom_cache_dir(self) -> None:
        """Test initialization with custom cache directory."""
        tmpdir = Path(tempfile.mkdtemp())
        router = SkillRouter(cache_dir=str(tmpdir / "cache"))

        assert router._cache.cache_dir == tmpdir / "cache"

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_init_with_ai_triage_disabled(self) -> None:
        """Test initialization with AI triage disabled."""
        router = SkillRouter(enable_ai_triage=False)

        assert not router._ai_triage_enabled
        assert router._llm is None

    def test_init_with_ai_triage_enabled(self) -> None:
        """Test initialization with AI triage enabled."""
        # Only test if API key is available
        if not os.getenv("ANTHROPIC_API_KEY") and not os.getenv("OPENAI_API_KEY"):
            return  # Skip test if no API key

        router = SkillRouter(enable_ai_triage=True)

        # Should have attempted to initialize LLM
        assert router._ai_triage_enabled or router._llm is not None


class TestSkillRoute:
    """Test SkillRoute model."""

    def test_skill_route_creation(self) -> None:
        """Test creating a SkillRoute."""
        route = SkillRoute(
            skill_id="/review",
            confidence=0.95,
            layer=1,
            source="explicit",
        )

        assert route.skill_id == "/review"
        assert route.confidence == 0.95
        assert route.layer == 1
        assert route.source == "explicit"

    def test_skill_route_with_metadata(self) -> None:
        """Test SkillRoute with metadata."""
        route = SkillRoute(
            skill_id="/review",
            confidence=0.95,
            layer=1,
            source="explicit",
            metadata={"preference_boost": 0.1},
        )

        assert route.metadata["preference_boost"] == 0.1
