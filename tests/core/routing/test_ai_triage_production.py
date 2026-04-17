"""Tests for AI Triage production features (budget, prompts, cost tracking)."""

from unittest.mock import MagicMock

import pytest

from vibesop.core.config.manager import RoutingConfig
from vibesop.core.models import RoutingLayer
from vibesop.core.routing import UnifiedRouter
from vibesop.llm.base import LLMResponse
from vibesop.llm.cost_tracker import TriageCostTracker
from vibesop.llm.triage_prompts import TriagePromptRegistry


class TestTriageResponseParsing:
    """Test AI Triage response parsing edge cases."""

    def test_parse_ai_triage_response_rejects_json_fence(self, tmp_path):
        from vibesop.core.routing.triage_service import TriageService
        from vibesop.llm.cost_tracker import TriageCostTracker
        from vibesop.core.routing.cache import CacheManager
        from vibesop.core.optimization import CandidatePrefilter

        config = RoutingConfig(enable_ai_triage=True)
        cost_tracker = TriageCostTracker(storage_dir=tmp_path)
        cache_manager = CacheManager(cache_dir=tmp_path)
        prefilter = CandidatePrefilter()

        service = TriageService(
            config=config,
            cost_tracker=cost_tracker,
            prefilter=prefilter,
            cache_manager=cache_manager,
            get_skill_source=lambda _sid, ns: ns,
        )

        # Markdown fence starting with json should not be parsed as skill_id
        response = "```json\n{}\n```"
        parsed = service.parse_ai_triage_response(response)
        assert parsed["skill_id"] is None

    def test_parse_ai_triage_response_accepts_valid_skill_id(self, tmp_path):
        from vibesop.core.routing.triage_service import TriageService
        from vibesop.llm.cost_tracker import TriageCostTracker
        from vibesop.core.routing.cache import CacheManager
        from vibesop.core.optimization import CandidatePrefilter

        config = RoutingConfig(enable_ai_triage=True)
        cost_tracker = TriageCostTracker(storage_dir=tmp_path)
        cache_manager = CacheManager(cache_dir=tmp_path)
        prefilter = CandidatePrefilter()

        service = TriageService(
            config=config,
            cost_tracker=cost_tracker,
            prefilter=prefilter,
            cache_manager=cache_manager,
            get_skill_source=lambda _sid, ns: ns,
        )

        response = "systematic-debugging"
        parsed = service.parse_ai_triage_response(response)
        assert parsed["skill_id"] == "systematic-debugging"


class TestTriagePromptRegistry:
    """Test prompt template registry."""

    def test_get_default_prompt(self) -> None:
        prompt = TriagePromptRegistry.get_prompt()
        assert "skill routing assistant" in prompt

    def test_render_prompt(self) -> None:
        rendered = TriagePromptRegistry.render(
            query="debug this",
            skills_summary="- systematic-debugging: Find root cause",
            version="v1",
        )
        assert "debug this" in rendered
        assert "systematic-debugging" in rendered

    def test_unknown_version_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown triage prompt version"):
            TriagePromptRegistry.get_prompt("nonexistent")


class TestTriageCostTracker:
    """Test cost tracking for AI Triage."""

    def test_record_and_stats(self, tmp_path) -> None:
        tracker = TriageCostTracker(storage_dir=tmp_path)
        record = tracker.record(
            model="claude-3-5-haiku-20241022",
            input_tokens=1000,
            output_tokens=500,
            query="debug this",
            selected_skill="systematic-debugging",
        )
        assert record.total_tokens == 1500
        assert record.estimated_cost_usd > 0

        stats = tracker.get_stats(days=30)
        assert stats["total_calls"] == 1
        assert stats["total_tokens"] == 1500
        assert stats["total_cost_usd"] > 0

    def test_monthly_cost_aggregation(self, tmp_path) -> None:
        tracker = TriageCostTracker(storage_dir=tmp_path)
        tracker.record(
            model="gpt-4o-mini",
            input_tokens=10_000,
            output_tokens=5_000,
            query="test",
            selected_skill=None,
        )
        cost = tracker.get_monthly_cost()
        assert cost > 0


class TestUnifiedRouterAIBudget:
    """Test AI Triage budget enforcement in UnifiedRouter."""

    def test_ai_triage_skipped_when_budget_exhausted(self, tmp_path) -> None:
        config = RoutingConfig(
            enable_ai_triage=True,
            ai_triage_budget_monthly=0.01,
            ai_triage_log_calls=True,
        )
        router = UnifiedRouter(project_root=tmp_path, config=config)

        # Exhaust budget by recording a high-cost call directly
        router._cost_tracker.record(
            model="claude-3-5-sonnet-20241022",
            input_tokens=1_000_000,
            output_tokens=500_000,
            query="prior call",
            selected_skill=None,
        )

        result = router._try_ai_triage("debug this", [])
        assert result is None

    def test_ai_triage_uses_configured_prompt_version(self, tmp_path) -> None:
        config = RoutingConfig(
            enable_ai_triage=True,
            ai_triage_prompt_version="v1",
        )
        router = UnifiedRouter(project_root=tmp_path, config=config)

        prompt = router._build_ai_triage_prompt("test", "- skill")
        assert "skill routing assistant" in prompt

    def test_ai_triage_records_cost_on_success(self, tmp_path) -> None:
        config = RoutingConfig(
            enable_ai_triage=True,
            ai_triage_log_calls=True,
        )
        router = UnifiedRouter(project_root=tmp_path, config=config)

        mock_llm = MagicMock()
        mock_llm.configured.return_value = True
        mock_llm.call.return_value = LLMResponse(
            content="systematic-debugging",
            model="claude-3-5-haiku-20241022",
            provider="Anthropic",
            tokens_used=100,
            input_tokens=60,
            output_tokens=40,
        )
        router._llm = mock_llm

        candidates = [{"id": "systematic-debugging", "intent": "debug"}]
        result = router._try_ai_triage("debug this", candidates)

        assert result is not None
        assert result.match.layer == RoutingLayer.AI_TRIAGE
        stats = router._cost_tracker.get_stats(days=30)
        assert stats["total_calls"] == 1
        assert stats["total_tokens"] == 100

    def test_get_ai_triage_stats_includes_budget(self, tmp_path) -> None:
        config = RoutingConfig(ai_triage_budget_monthly=5.0)
        router = UnifiedRouter(project_root=tmp_path, config=config)
        stats = router.get_ai_triage_stats()
        assert stats["budget_monthly_usd"] == 5.0
        assert stats["budget_remaining_usd"] >= 0
