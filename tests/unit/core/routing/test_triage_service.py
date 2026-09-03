"""Tests for TriageService — AI triage layer, parsing, caching, and budget."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from vibesop.core.routing.triage_service import TriageService

if TYPE_CHECKING:
    from pathlib import Path
    from typing import ClassVar

    import pytest


def _make_service(
    enable_ai_triage: bool = True,
    ai_triage_budget_monthly: float = 5.0,
    ai_triage_log_calls: bool = True,
    ai_triage_max_skills: int = 10,
    ai_triage_max_tokens: int = 500,
    ai_triage_prompt_version: str = "v2",
    ai_triage_circuit_breaker_enabled: bool = True,
) -> TriageService:
    """Factory for TriageService with mocked dependencies."""
    config = MagicMock()
    config.enable_ai_triage = enable_ai_triage
    config.ai_triage_budget_monthly = ai_triage_budget_monthly
    config.ai_triage_log_calls = ai_triage_log_calls
    config.ai_triage_max_skills = ai_triage_max_skills
    config.ai_triage_max_tokens = ai_triage_max_tokens
    config.ai_triage_prompt_version = ai_triage_prompt_version
    config.ai_triage_circuit_breaker_enabled = ai_triage_circuit_breaker_enabled
    config.ai_triage_circuit_breaker_failure_threshold = 3
    config.ai_triage_circuit_breaker_latency_threshold_ms = 500.0
    config.ai_triage_circuit_breaker_cooldown_seconds = 60

    cost_tracker = MagicMock()
    cost_tracker.get_monthly_cost.return_value = 0.0
    prefilter = MagicMock()
    cache_manager = MagicMock()

    return TriageService(
        config=config,
        cost_tracker=cost_tracker,
        prefilter=prefilter,
        cache_manager=cache_manager,
        get_skill_source=lambda sid, ns: f"{ns}/{sid}",
    )


class TestTryAiTriageDisabled:
    """Test early returns when AI triage is unavailable."""

    def test_disabled_config(self) -> None:
        """When enable_ai_triage=False, returns None immediately."""
        service = _make_service(enable_ai_triage=False)
        result = service.try_ai_triage("test", [])
        assert result is None

    def test_llm_not_configured(self) -> None:
        """When LLM is None or unconfigured, returns None."""
        service = _make_service()
        service._llm = MagicMock()
        service._llm.configured.return_value = False
        result = service.try_ai_triage("test", [])
        assert result is None

    def test_llm_init_on_first_call(self) -> None:
        """First call initializes LLM if None."""
        service = _make_service()
        service._llm = None
        with patch.object(
            service, "init_llm_client", return_value=MagicMock(configured=lambda: False)
        ) as mock_init:
            result = service.try_ai_triage("test", [])
        assert result is None
        mock_init.assert_called_once()


class TestBudgetEnforcement:
    """Test budget checks in try_ai_triage."""

    def test_budget_exhausted_trips_circuit(self) -> None:
        """Monthly budget exhausted → trip breaker and return None."""
        service = _make_service(ai_triage_budget_monthly=5.0)
        service._cost_tracker.get_monthly_cost.return_value = 5.5
        service._llm = MagicMock()
        service._llm.configured.return_value = True

        result = service.try_ai_triage("test", [])
        assert result is None
        assert service._circuit_breaker.state == "open"

    def test_budget_90_percent_warning(self) -> None:
        """Budget at 90%+ logs a warning but still allows execution."""
        service = _make_service(ai_triage_budget_monthly=10.0)
        service._cost_tracker.get_monthly_cost.return_value = 9.1
        service._llm = MagicMock()
        service._llm.configured.return_value = True
        service._llm.call.return_value = MagicMock(
            content="skill-a",
            model="test",
            tokens_used=10,
            input_tokens=5,
            output_tokens=5,
        )

        with patch.object(service, "parse_ai_triage_response", return_value={"skill_id": None}):
            service.try_ai_triage("test", [{"id": "skill-a", "intent": "test"}])

        # Should not have tripped
        assert service._circuit_breaker.state != "open"

    def test_zero_budget_disabled(self) -> None:
        """Budget of 0 disables budget enforcement."""
        service = _make_service(ai_triage_budget_monthly=0.0)
        service._llm = MagicMock()
        service._llm.configured.return_value = True
        service._llm.call.return_value = MagicMock(
            content="skill-a",
            model="test",
            tokens_used=10,
            input_tokens=5,
            output_tokens=5,
        )

        with patch.object(service, "parse_ai_triage_response", return_value={"skill_id": None}):
            service.try_ai_triage("test", [{"id": "skill-a", "intent": "test"}])

        # Budget check should be skipped
        service._cost_tracker.get_monthly_cost.assert_not_called()


class TestCircuitBreaker:
    """Test circuit breaker integration."""

    def test_circuit_open_blocks_execution(self) -> None:
        """Open circuit breaker prevents AI triage execution."""
        service = _make_service()
        service._circuit_breaker.trip("manual")
        service._llm = MagicMock()
        service._llm.configured.return_value = True

        result = service.try_ai_triage("test", [])
        assert result is None
        service._llm.call.assert_not_called()


class TestQueryAugmentation:
    """Test CJK follow-up query augmentation."""

    def test_short_query_augmented(self) -> None:
        """Short query (<20 chars) with recent context gets augmented."""
        service = _make_service()
        service._llm = MagicMock()
        service._llm.configured.return_value = True
        service._llm.call.return_value = MagicMock(
            content="skill-a",
            model="test",
            tokens_used=10,
            input_tokens=5,
            output_tokens=5,
        )

        context = MagicMock()
        context.recent_queries = ["previous question"]

        with patch.object(service, "parse_ai_triage_response", return_value={"skill_id": None}):
            service.try_ai_triage("debug", [{"id": "skill-a", "intent": "test"}], context=context)

        # The prompt should contain augmented query
        call_args = service._llm.call.call_args
        assert "Conversation:" in call_args.kwargs["prompt"]

    def test_cjk_follow_up_augmented(self) -> None:
        """CJK follow-up markers trigger augmentation even for longer queries."""
        service = _make_service()
        service._llm = MagicMock()
        service._llm.configured.return_value = True
        service._llm.call.return_value = MagicMock(
            content="skill-a",
            model="test",
            tokens_used=10,
            input_tokens=5,
            output_tokens=5,
        )

        context = MagicMock()
        context.recent_queries = ["如何部署"]

        with patch.object(service, "parse_ai_triage_response", return_value={"skill_id": None}):
            service.try_ai_triage(
                "还是部署问题", [{"id": "skill-a", "intent": "test"}], context=context
            )

        call_args = service._llm.call.call_args
        assert "Conversation:" in call_args.kwargs["prompt"]

    def test_long_query_no_augment(self) -> None:
        """Long query without CJK markers is not augmented."""
        service = _make_service()
        service._llm = MagicMock()
        service._llm.configured.return_value = True
        service._llm.call.return_value = MagicMock(
            content="skill-a",
            model="test",
            tokens_used=10,
            input_tokens=5,
            output_tokens=5,
        )

        context = MagicMock()
        context.recent_queries = ["previous"]

        with patch.object(service, "parse_ai_triage_response", return_value={"skill_id": None}):
            service.try_ai_triage(
                "this is a very long query without markers",
                [{"id": "skill-a", "intent": "test"}],
                context=context,
            )

        call_args = service._llm.call.call_args
        assert "Conversation:" not in call_args.kwargs["prompt"]


class TestCache:
    """Triage no longer uses the CacheManager; the persistent TriageCache
    (fresh-hit path, B1 aliveness) is covered in test_triage_cache.py."""

    def test_cache_manager_not_used_by_triage(self) -> None:
        """A full triage call never reads or writes the CacheManager."""
        service = _make_service()
        service._llm = MagicMock()
        service._llm.configured.return_value = True
        service._llm.call.return_value = MagicMock(
            content="skill-a",
            model="test",
            tokens_used=10,
            input_tokens=5,
            output_tokens=5,
        )

        with patch.object(
            service,
            "parse_ai_triage_response",
            return_value={"skill_id": "skill-a", "structured": True},
        ):
            result = service.try_ai_triage("test", [{"id": "skill-a", "intent": "test"}])

        assert result is not None
        service._cache_manager.get.assert_not_called()
        service._cache_manager.set.assert_not_called()

    def test_cache_miss_calls_llm(self) -> None:
        """Cache miss proceeds to LLM call."""
        service = _make_service()
        service._llm = MagicMock()
        service._llm.configured.return_value = True
        service._llm.call.return_value = MagicMock(
            content="skill-a",
            model="test",
            tokens_used=10,
            input_tokens=5,
            output_tokens=5,
        )

        with patch.object(service, "parse_ai_triage_response", return_value={"skill_id": None}):
            service.try_ai_triage("test", [{"id": "skill-a", "intent": "test"}])

        service._llm.call.assert_called_once()


class TestTokenFallback:
    """Test token counting fallback in cost recording."""

    def test_tokens_used_fallback(self) -> None:
        """When input/output tokens missing, falls back to tokens_used."""
        service = _make_service()
        service._llm = MagicMock()
        service._llm.configured.return_value = True
        service._llm.call.return_value = MagicMock(
            content="skill-a",
            model="test-model",
            tokens_used=100,
            # No input_tokens or output_tokens
        )

        with patch.object(service, "parse_ai_triage_response", return_value={"skill_id": None}):
            service.try_ai_triage("test", [{"id": "skill-a", "intent": "test"}])

        call = service._cost_tracker.record.call_args
        assert call.kwargs["input_tokens"] == 100
        assert call.kwargs["output_tokens"] == 0

    def test_no_token_info_defaults_to_zero(self) -> None:
        """When no token info available, defaults to 0."""
        service = _make_service()
        service._llm = MagicMock()
        service._llm.configured.return_value = True
        service._llm.call.return_value = MagicMock(
            content="skill-a",
            model="test-model",
            # No tokens at all
        )

        with patch.object(service, "parse_ai_triage_response", return_value={"skill_id": None}):
            service.try_ai_triage("test", [{"id": "skill-a", "intent": "test"}])

        call = service._cost_tracker.record.call_args
        assert call.kwargs["input_tokens"] == 0
        assert call.kwargs["output_tokens"] == 0


class TestExceptionHandling:
    """Test exception handling in try_ai_triage."""

    def test_llm_exception_records_failure(self) -> None:
        """LLM exception records failure on circuit breaker."""
        service = _make_service()
        service._llm = MagicMock()
        service._llm.configured.return_value = True
        service._llm.call.side_effect = RuntimeError("LLM error")

        result = service.try_ai_triage("test", [{"id": "skill-a", "intent": "test"}])
        assert result is None
        assert service._circuit_breaker._consecutive_failures == 1


class TestPrefilter:
    """Test prefilter_ai_triage_candidates."""

    def test_no_prefilter_when_under_limit(self) -> None:
        """When candidates <= max_skills, return all."""
        service = _make_service(ai_triage_max_skills=5)
        candidates = [
            {"id": "a", "intent": "test1"},
            {"id": "b", "intent": "test2"},
        ]
        result = service.prefilter_ai_triage_candidates("test", candidates, 5)
        assert len(result) == 2

    def test_prefilter_reduces_candidates(self) -> None:
        """When candidates > max_skills, keyword matcher reduces them."""
        service = _make_service(ai_triage_max_skills=2)
        candidates = [
            {"id": "debug-skill", "intent": "debug things"},
            {"id": "deploy-skill", "intent": "deploy things"},
            {"id": "review-skill", "intent": "review code"},
        ]
        result = service.prefilter_ai_triage_candidates("debug", candidates, 2)
        assert len(result) <= 2


class TestParseAiTriageResponse:
    """Test response parsing with JSON priority and regex fallback."""

    def test_parse_json_object(self) -> None:
        """Valid JSON object parsed for skill_id and confidence."""
        service = _make_service()
        result = service.parse_ai_triage_response(
            '{"skill_id": "gstack/review", "confidence": 0.95}'
        )
        assert result["skill_id"] == "gstack/review"
        assert result["confidence"] == 0.95
        assert result["structured"] is True

    def test_parse_json_with_markdown_fences(self) -> None:
        """JSON inside markdown fences is extracted and parsed."""
        service = _make_service()
        result = service.parse_ai_triage_response(
            '```json\n{"skill_id": "debug", "confidence": 0.8}\n```'
        )
        assert result["skill_id"] == "debug"
        assert result["structured"] is True

    def test_parse_invalid_json(self) -> None:
        """Invalid JSON falls through to regex."""
        service = _make_service()
        result = service.parse_ai_triage_response("{invalid json}")
        assert result["structured"] is False

    def test_parse_regex_code_fence(self) -> None:
        """Regex extracts skill_id from ```skill_id``` format."""
        service = _make_service()
        result = service.parse_ai_triage_response("```gstack/review```")
        assert result["skill_id"] == "gstack/review"
        assert result["structured"] is False

    def test_parse_plain_skill_id(self) -> None:
        """Plain skill_id on its own line is extracted."""
        service = _make_service()
        result = service.parse_ai_triage_response("gstack/review")
        assert result["skill_id"] == "gstack/review"
        assert result["structured"] is False

    def test_rejects_markdown_fence_keywords(self) -> None:
        """Keywords like 'json', 'yaml' are not treated as skill IDs."""
        service = _make_service()
        for keyword in ["json", "yaml", "python", "text", "markdown", "md"]:
            result = service.parse_ai_triage_response(keyword)
            assert result["skill_id"] is None, f"'{keyword}' should not be parsed as skill_id"

    def test_rejects_invalid_skill_id_format(self) -> None:
        """Skill IDs must match word/path pattern."""
        service = _make_service()
        result = service.parse_ai_triage_response("just some text without skill id")
        assert result["skill_id"] is None


class TestInitLlmClient:
    """Test LLM client initialization tiers."""

    def test_env_var_disable(self) -> None:
        """VIBE_AI_TRIAGE_ENABLED=0 disables LLM init."""
        service = _make_service()
        with patch.dict("os.environ", {"VIBE_AI_TRIAGE_ENABLED": "0"}):
            result = service.init_llm_client()
        assert result is None

    def test_env_var_false_string(self) -> None:
        """VIBE_AI_TRIAGE_ENABLED=false disables LLM init."""
        service = _make_service()
        with patch.dict("os.environ", {"VIBE_AI_TRIAGE_ENABLED": "false"}):
            result = service.init_llm_client()
        assert result is None

    def test_init_failure_returns_none(self) -> None:
        """Exception during init logs and returns None."""
        service = _make_service()
        with (
            patch("vibesop.core.routing.triage_service.os.getenv", return_value=""),
            patch(
                "vibesop.llm.factory.create_provider",
                side_effect=ValueError("no provider"),
            ),
        ):
            result = service.init_llm_client()
        assert result is None


class TestSkillIdNotInCandidates:
    """Test when parsed skill_id is not found in candidates list."""

    def test_unknown_skill_id_returns_none(self) -> None:
        """If LLM returns skill_id not in candidates, return None."""
        service = _make_service()
        service._llm = MagicMock()
        service._llm.configured.return_value = True
        service._llm.call.return_value = MagicMock(
            content="unknown-skill",
            model="test",
            tokens_used=10,
            input_tokens=5,
            output_tokens=5,
        )

        with patch.object(
            service, "parse_ai_triage_response", return_value={"skill_id": "unknown-skill"}
        ):
            result = service.try_ai_triage("test", [{"id": "skill-a", "intent": "test"}])

        assert result is None


class TestSessionEndGuard:
    """Test that session-end is only selected on explicit signals."""

    def _make_service_with_llm(self) -> TriageService:
        service = _make_service()
        service._llm = MagicMock()
        service._llm.configured.return_value = True
        service._llm.call.return_value = MagicMock(
            content='{"skill_id": "builtin/session-end"}',
            model="test",
            tokens_used=10,
            input_tokens=5,
            output_tokens=5,
        )
        return service

    def test_session_end_rejected_without_explicit_signal(self) -> None:
        """Ordinary technical queries must not route to session-end."""
        service = self._make_service_with_llm()
        candidates = [
            {
                "id": "builtin/session-end",
                "intent": "wrap up session",
                "triggers": ["that's all for now", "拜拜"],
            },
            {"id": "debug-skill", "intent": "debug things"},
        ]

        with patch.object(
            service,
            "parse_ai_triage_response",
            return_value={"skill_id": "builtin/session-end", "structured": True},
        ):
            result = service.try_ai_triage(
                "有点奇怪，当前 CMSpark 的 MCP 支持有问题，未连接，无法获取工具列表",
                candidates,
            )

        assert result is None

    def test_session_end_allowed_with_explicit_signal(self) -> None:
        """Explicit session-end signals should still route to session-end."""
        service = self._make_service_with_llm()
        candidates = [
            {
                "id": "builtin/session-end",
                "intent": "wrap up session",
                "triggers": ["that's all for now", "拜拜"],
            },
            {"id": "debug-skill", "intent": "debug things"},
        ]

        with patch.object(
            service,
            "parse_ai_triage_response",
            return_value={"skill_id": "builtin/session-end", "structured": True},
        ):
            result = service.try_ai_triage("今天就到这里，拜拜", candidates)

        assert result is not None
        assert result.match.skill_id == "builtin/session-end"

    def test_session_end_uses_fallback_triggers_when_missing(self) -> None:
        """If candidate has no triggers, guard still uses known signals."""
        service = self._make_service_with_llm()
        candidates = [
            {"id": "builtin/session-end", "intent": "wrap up session"},
            {"id": "debug-skill", "intent": "debug things"},
        ]

        with patch.object(
            service,
            "parse_ai_triage_response",
            return_value={"skill_id": "builtin/session-end", "structured": True},
        ):
            result = service.try_ai_triage("I'm done for today", candidates)

        assert result is not None
        assert result.match.skill_id == "builtin/session-end"

    def test_session_end_rejected_when_candidate_not_present(self) -> None:
        """If session-end is not in candidates, guard rejects selection."""
        service = self._make_service_with_llm()
        candidates = [{"id": "debug-skill", "intent": "debug things"}]

        with patch.object(
            service,
            "parse_ai_triage_response",
            return_value={"skill_id": "builtin/session-end", "structured": True},
        ):
            result = service.try_ai_triage("that's all for now", candidates)

        assert result is None

    def test_guarded_structured_reply_resets_unstructured_drops(self) -> None:
        """The guard's early return still followed a structured reply — the
        drop counter must reset there too ('reset on any structured reply',
        same rule as the match and NONE paths)."""
        service = self._make_service_with_llm()
        service._unstructured_drops = 2
        candidates = [
            {
                "id": "builtin/session-end",
                "intent": "wrap up session",
                "triggers": ["that's all for now", "拜拜"],
            },
            {"id": "debug-skill", "intent": "debug things"},
        ]

        with patch.object(
            service,
            "parse_ai_triage_response",
            return_value={"skill_id": "builtin/session-end", "structured": True},
        ):
            result = service.try_ai_triage(
                "有点奇怪，当前 CMSpark 的 MCP 支持有问题，未连接，无法获取工具列表",
                candidates,
            )

        assert result is None
        assert service._unstructured_drops == 0


class TestFreshCacheHit:
    """Persistent-cache fresh hits: session-end guard reuse and metadata keys."""

    def _make_service_with_fresh_hit(self, fresh_entry: dict) -> TriageService:
        service = _make_service()
        service._llm = MagicMock()
        service._llm.configured.return_value = True
        service._llm.call.return_value = MagicMock(
            content="debug-skill",
            model="test",
            tokens_used=10,
            input_tokens=5,
            output_tokens=5,
        )
        service._triage_cache = MagicMock()
        service._triage_cache.lookup.return_value = (fresh_entry, None)
        return service

    _CANDIDATES: ClassVar = [
        {
            "id": "builtin/session-end",
            "intent": "wrap up session",
            "triggers": ["that's all for now", "拜拜"],
        },
        {"id": "debug-skill", "intent": "debug things"},
    ]

    def test_fresh_hit_session_end_rejected_without_explicit_signal(self) -> None:
        """A fresh cached session-end hit is bypassed without an explicit
        signal (same guard as the LLM path); triage continues to the LLM."""
        service = self._make_service_with_fresh_hit(
            {
                "skill_id": "builtin/session-end",
                "confidence": 0.9,
                "source": "builtin/session-end",
                "description": "wrap up session",
            }
        )

        with patch.object(
            service,
            "parse_ai_triage_response",
            return_value={"skill_id": "debug-skill", "structured": True},
        ):
            result = service.try_ai_triage(
                "有点奇怪，当前 MCP 支持有问题，无法获取工具列表",
                self._CANDIDATES,
            )

        service._llm.call.assert_called_once()
        assert result is not None
        assert result.match.skill_id == "debug-skill"

    def test_fresh_hit_session_end_allowed_with_explicit_signal(self) -> None:
        """A fresh cached session-end hit is honored on an explicit signal."""
        service = self._make_service_with_fresh_hit(
            {
                "skill_id": "builtin/session-end",
                "confidence": 0.9,
                "source": "builtin/session-end",
                "description": "wrap up session",
            }
        )

        result = service.try_ai_triage("that's all for now", self._CANDIDATES)

        service._llm.call.assert_not_called()
        assert result is not None
        assert result.match.skill_id == "builtin/session-end"

    def test_fresh_hit_metadata_keys_match_llm_path(self) -> None:
        """Fresh-hit metadata carries the same keys as the LLM path."""
        service = self._make_service_with_fresh_hit(
            {
                "skill_id": "debug-skill",
                "confidence": 0.9,
                "source": "builtin/debug-skill",
                "description": "debug things",
            }
        )

        result = service.try_ai_triage("debug this", self._CANDIDATES)

        service._llm.call.assert_not_called()
        assert result is not None
        metadata = result.match.metadata
        assert metadata["model"] == "cache"
        assert metadata["structured"] is False
        assert metadata["candidates_sent"] == 0
        assert metadata["recall_method"] is None

    def test_fresh_hit_carries_candidate_source_file(self) -> None:
        """Fresh-hit route metadata must carry the discovered source_file.

        Match⇔injectable-content isomorphism: every AI-triage SkillRoute
        construction site threads the candidate's SKILL.md path so the
        injector can load the same file the router matched.
        """
        service = self._make_service_with_fresh_hit(
            {
                "skill_id": "debug-skill",
                "confidence": 0.9,
                "source": "builtin/debug-skill",
                "description": "debug things",
            }
        )
        candidates = [{**c, "source_file": f"/skills/{c['id']}/SKILL.md"} for c in self._CANDIDATES]

        result = service.try_ai_triage("debug this", candidates)

        service._llm.call.assert_not_called()
        assert result is not None
        assert result.match.metadata["source_file"] == "/skills/debug-skill/SKILL.md"

    def test_llm_match_carries_candidate_source_file(self) -> None:
        """LLM-path route metadata must carry the discovered source_file."""
        service = _make_service()
        service._llm = MagicMock()
        service._llm.configured.return_value = True
        service._llm.call.return_value = MagicMock(
            content="debug-skill",
            model="test",
            tokens_used=10,
            input_tokens=5,
            output_tokens=5,
        )
        candidates = [
            {"id": "debug-skill", "intent": "debug things", "source_file": "/s/debug/SKILL.md"}
        ]

        with patch.object(
            service,
            "parse_ai_triage_response",
            return_value={"skill_id": "debug-skill", "structured": True, "confidence": 0.9},
        ):
            result = service.try_ai_triage("debug this", candidates)

        assert result is not None
        assert result.match.metadata["source_file"] == "/s/debug/SKILL.md"


class TestBudgetExhaustedLogging:
    """Budget exhaustion must produce exactly one log (the trip warning)."""

    def test_budget_exhausted_logs_single_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        service = _make_service(ai_triage_budget_monthly=5.0)
        service._cost_tracker.get_monthly_cost.return_value = 5.5
        service._llm = MagicMock()
        service._llm.configured.return_value = True

        with caplog.at_level(logging.WARNING):
            result = service.try_ai_triage("test", [{"id": "skill-a", "intent": "test"}])

        assert result is None
        assert len(caplog.records) == 1
        message = caplog.records[0].getMessage()
        assert caplog.records[0].levelno == logging.WARNING
        assert "budget exhausted" in message
        assert "5.5000/5.0000" in message


class TestCacheDirResolution:
    """The .vibe dir is derived from cache_dir for both layouts."""

    def _make_service_at(self, cache_dir: Path) -> TriageService:
        config = MagicMock()
        cache_manager = MagicMock()
        cache_manager.cache_dir = cache_dir
        return TriageService(
            config=config,
            cost_tracker=MagicMock(),
            prefilter=MagicMock(),
            cache_manager=cache_manager,
            get_skill_source=lambda sid, ns: f"{ns}/{sid}",
        )

    def test_standard_cache_subdir_layout(self, tmp_path: Path) -> None:
        """<root>/.vibe/cache -> the .vibe dir is the parent."""
        vibe_dir = tmp_path / ".vibe"
        service = self._make_service_at(vibe_dir / "cache")

        assert service._triage_cache is not None
        assert service._triage_cache.cache_path == vibe_dir / "triage_cache.json"
        assert service._embedding_recall is not None
        assert service._embedding_recall.cache_path == vibe_dir / "skill_embeddings.json"

    def test_cache_dir_is_vibe_dir_itself(self, tmp_path: Path) -> None:
        """A custom cache_dir that already IS .vibe is used as-is."""
        vibe_dir = tmp_path / ".vibe"
        service = self._make_service_at(vibe_dir)

        assert service._triage_cache is not None
        assert service._triage_cache.cache_path == vibe_dir / "triage_cache.json"
        assert service._embedding_recall is not None
        assert service._embedding_recall.cache_path == vibe_dir / "skill_embeddings.json"


class TestLastGoodRecallMethod:
    """Last-good routes must not leak a previous request's recall_method.

    Regression: _last_good_route used to read the instance attribute
    self._last_recall_method, which in a long-lived process carried the
    previous request's value into the budget/circuit/LLM-failure paths.
    """

    _CANDIDATES: ClassVar = [
        {"id": "debug-skill", "intent": "debug things"},
        {"id": "deploy-skill", "intent": "deploy things"},
        {"id": "review-skill", "intent": "review code"},
    ]
    _STALE_ENTRY: ClassVar = {
        "skill_id": "debug-skill",
        "confidence": 0.9,
        "source": "builtin/debug-skill",
        "description": "debug things",
    }

    def _make_service_with_llm(self) -> TriageService:
        # max_skills=2 with 3 candidates forces the prefilter down the
        # keyword-recall path, setting _last_recall_method = "keyword".
        service = _make_service(ai_triage_max_skills=2)
        service._llm = MagicMock()
        service._llm.configured.return_value = True
        service._llm.call.return_value = MagicMock(
            content="debug-skill",
            model="test",
            tokens_used=10,
            input_tokens=5,
            output_tokens=5,
        )
        service._triage_cache = MagicMock()
        service._triage_cache.lookup.return_value = (None, None)
        return service

    def _run_successful_triage(self, service: TriageService) -> None:
        """First request: full prefilter + LLM path, recall_method recorded."""
        with patch.object(
            service,
            "parse_ai_triage_response",
            return_value={"skill_id": "debug-skill", "structured": True},
        ):
            result = service.try_ai_triage("debug", self._CANDIDATES)
        assert result is not None
        assert result.match.metadata["recall_method"] == "keyword"

    def test_budget_rejected_last_good_has_no_residual_recall_method(self) -> None:
        """Second request rejected by the budget gate must not carry the
        first request's recall_method into its last-good metadata."""
        service = self._make_service_with_llm()
        self._run_successful_triage(service)

        service._cost_tracker.get_monthly_cost.return_value = 5.5
        service._triage_cache.lookup.return_value = (None, self._STALE_ENTRY)

        result = service.try_ai_triage("debug", self._CANDIDATES)

        assert result is not None
        assert result.match.metadata["last_good"] is True
        assert result.match.metadata["recall_method"] is None

    def test_circuit_open_last_good_has_no_residual_recall_method(self) -> None:
        """Second request rejected by an open circuit must not carry the
        first request's recall_method either."""
        service = self._make_service_with_llm()
        self._run_successful_triage(service)

        service._circuit_breaker.trip("manual")
        service._triage_cache.lookup.return_value = (None, self._STALE_ENTRY)

        result = service.try_ai_triage("debug", self._CANDIDATES)

        assert result is not None
        assert result.match.metadata["last_good"] is True
        assert result.match.metadata["recall_method"] is None

    def test_llm_failure_last_good_has_no_recall_method(self) -> None:
        """On the LLM-failure path the prefilter DID run for this request,
        but the last-good route replays a stale entry and used none of that
        recall — recall_method must still be None."""
        service = self._make_service_with_llm()
        self._run_successful_triage(service)

        service._llm.call.side_effect = RuntimeError("LLM error")
        service._triage_cache.lookup.return_value = (None, self._STALE_ENTRY)

        result = service.try_ai_triage("debug", self._CANDIDATES)

        assert result is not None
        assert result.match.metadata["last_good"] is True
        assert result.match.metadata["recall_method"] is None

    def test_last_good_carries_candidate_source_file(self) -> None:
        """Last-good route metadata must carry the discovered source_file."""
        service = self._make_service_with_llm()
        self._run_successful_triage(service)

        service._cost_tracker.get_monthly_cost.return_value = 5.5
        service._triage_cache.lookup.return_value = (None, self._STALE_ENTRY)
        candidates = [{**c, "source_file": f"/skills/{c['id']}/SKILL.md"} for c in self._CANDIDATES]

        result = service.try_ai_triage("debug", candidates)

        assert result is not None
        assert result.match.metadata["last_good"] is True
        assert result.match.metadata["source_file"] == "/skills/debug-skill/SKILL.md"


class TestLlmUnconfiguredCacheLookup:
    """With no LLM configured, a fresh persistent-cache hit is still served;
    a miss short-circuits exactly as before (no last-good fallback)."""

    _FRESH_ENTRY: ClassVar = {
        "skill_id": "debug-skill",
        "confidence": 0.9,
        "source": "builtin/debug-skill",
        "description": "debug things",
    }
    _CANDIDATES: ClassVar = [{"id": "debug-skill", "intent": "debug things"}]

    def _make_unconfigured_service(self) -> TriageService:
        service = _make_service()
        service._llm = MagicMock()
        service._llm.configured.return_value = False
        service._triage_cache = MagicMock()
        return service

    def test_fresh_hit_returned_without_llm(self) -> None:
        service = self._make_unconfigured_service()
        service._triage_cache.lookup.return_value = (self._FRESH_ENTRY, None)

        result = service.try_ai_triage("debug this", self._CANDIDATES)

        service._llm.call.assert_not_called()
        assert result is not None
        assert result.match.skill_id == "debug-skill"
        assert result.match.metadata["persistent_cache"] is True

    def test_fresh_hit_returned_with_env_var_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """VIBE_AI_TRIAGE_ENABLED=0 gates only the LLM client: a fresh
        persistent-cache hit is still served, and the LLM path is never
        touched (init_llm_client is not even called)."""
        monkeypatch.setenv("VIBE_AI_TRIAGE_ENABLED", "0")
        service = _make_service()
        service._triage_cache = MagicMock()
        service._triage_cache.lookup.return_value = (self._FRESH_ENTRY, None)

        with patch.object(service, "init_llm_client") as init_spy:
            result = service.try_ai_triage("debug this", self._CANDIDATES)

        init_spy.assert_not_called()
        assert result is not None
        assert result.match.skill_id == "debug-skill"
        assert result.match.metadata["persistent_cache"] is True

    def test_miss_short_circuits_without_llm(self) -> None:
        """No fresh entry → the layer stays closed; even a stale entry is
        NOT served as last-good when the LLM was never configured."""
        service = self._make_unconfigured_service()
        service._triage_cache.lookup.return_value = (None, self._FRESH_ENTRY)

        result = service.try_ai_triage("debug this", self._CANDIDATES)

        service._llm.call.assert_not_called()
        assert result is None


class TestGuardedSkills:
    """Guarded skills (session-end, riper-workflow) require explicit intent.

    Session-end is high side-effect (wrap-up, commit, memory writes);
    riper-workflow's own contract is explicit-RIPER-requests-only. Fuzzy
    layers (keyword/embedding/scenario) must not select them unless the
    query carries the skill's trigger phrases or distinctive name token.
    """

    _SESSION_END: ClassVar[dict] = {
        "id": "builtin/session-end",
        "description": "Session wrap-up",
        "namespace": "builtin",
        "triggers": ["我要离开了", "离开了", "先走了", "收工", "拜拜"],
    }
    _RIPER: ClassVar[dict] = {
        "id": "builtin/riper-workflow",
        "description": "RIPER 5-phase workflow",
        "namespace": "builtin",
        "triggers": ["use riper", "riper workflow", "riper 工作流", "五阶段工作流"],
    }

    def _candidates(self) -> list[dict]:
        return [dict(self._SESSION_END), dict(self._RIPER)]

    def test_guarded_skill_name(self) -> None:
        service = _make_service()
        assert service.guarded_skill_name("builtin/session-end") == "session-end"
        assert service.guarded_skill_name("session-end") == "session-end"
        assert service.guarded_skill_name("builtin/riper-workflow") == "riper-workflow"
        assert service.guarded_skill_name("omx/plan") is None

    def test_unguarded_skill_always_passes(self) -> None:
        service = _make_service()
        assert service.has_explicit_guard_signal("anything", [], "omx/plan") is True

    def test_session_end_leaving_signal(self) -> None:
        """「我先离开了」 contains the 离开了 trigger → explicit signal."""
        service = _make_service()
        assert (
            service.has_explicit_guard_signal(
                "我先离开了", self._candidates(), "builtin/session-end"
            )
            is True
        )

    def test_session_end_close_something_is_not_a_signal(self) -> None:
        """「帮我先关闭了」 (close a process) must NOT count as an exit signal."""
        service = _make_service()
        assert (
            service.has_explicit_guard_signal(
                "似乎有其他进程没有关闭，帮我先关闭了", self._candidates(), "builtin/session-end"
            )
            is False
        )

    def test_riper_generic_workflow_query_blocked(self) -> None:
        """Generic 'workflow' queries carry no explicit RIPER intent."""
        service = _make_service()
        assert (
            service.has_explicit_guard_signal(
                "使用合适的 workflow 在独立的 worktree 上进行开发吧",
                self._candidates(),
                "builtin/riper-workflow",
            )
            is False
        )

    def test_riper_name_token_counts_as_explicit(self) -> None:
        """The distinctive 'riper' token is explicit intent even when no full
        trigger phrase appears verbatim (「用 RIPER 流程来做这个功能」)."""
        service = _make_service()
        assert (
            service.has_explicit_guard_signal(
                "用 RIPER 流程来做这个功能", self._candidates(), "builtin/riper-workflow"
            )
            is True
        )

    def test_riper_trigger_phrase_counts_as_explicit(self) -> None:
        service = _make_service()
        assert (
            service.has_explicit_guard_signal(
                "run the riper workflow for this feature",
                self._candidates(),
                "builtin/riper-workflow",
            )
            is True
        )

    def test_riper_fallback_triggers_when_candidate_missing(self) -> None:
        """Without a riper candidate, the conservative fallback list applies."""
        service = _make_service()
        assert service.has_explicit_guard_signal(
            "tell me about riper", [], "builtin/riper-workflow"
        )
        assert not service.has_explicit_guard_signal("make a plan", [], "builtin/riper-workflow")

    def test_session_end_real_skill_md_covers_leaving(self) -> None:
        """The shipped session-end SKILL.md triggers must detect 「我先离开了」.

        Ties the frontmatter trigger list (core/skills/session-end/SKILL.md)
        to the guard semantics so removing the trigger fails this test.
        """
        from pathlib import Path

        from vibesop.core.skills.parser import extract_frontmatter

        repo_root = Path(__file__).resolve().parents[4]
        content = (repo_root / "core" / "skills" / "session-end" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        frontmatter, _ = extract_frontmatter(content)
        assert frontmatter is not None
        candidates = [
            {
                "id": "builtin/session-end",
                "namespace": "builtin",
                "triggers": list(frontmatter.get("triggers") or []),
            }
        ]
        service = _make_service()
        assert (
            service.has_explicit_guard_signal("我先离开了", candidates, "builtin/session-end")
            is True
        )

    def test_riper_fallback_triggers_cover_real_skill_md(self) -> None:
        """The riper fallback trigger list must cover the real SKILL.md.

        When no riper candidate is loaded, the guard falls back to
        _GUARDED_SKILL_FALLBACK_TRIGGERS; that list must contain every
        trigger declared in core/skills/riper-workflow/SKILL.md so the two
        never drift apart.
        """
        from pathlib import Path

        from vibesop.core.skills.parser import extract_frontmatter

        repo_root = Path(__file__).resolve().parents[4]
        content = (repo_root / "core" / "skills" / "riper-workflow" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        frontmatter, _ = extract_frontmatter(content)
        assert frontmatter is not None
        declared = [str(t).lower() for t in (frontmatter.get("triggers") or [])]

        service = _make_service()
        fallback = [t.lower() for t in service._GUARDED_SKILL_FALLBACK_TRIGGERS["riper-workflow"]]
        for trigger in declared:
            # Each declared trigger must be represented: either verbatim in
            # the fallback list, or covered by the "riper" extra token /
            # a broader fallback entry that is a substring of it.
            assert trigger in fallback or any(f in trigger for f in fallback), (
                f"declared trigger {trigger!r} not covered by fallback list"
            )


class TestExplicitGuardedSkillMatch:
    """Promotion direction for guarded skills: an explicit signal routes the
    skill directly, complementing has_explicit_guard_signal (the gate)."""

    _RIPER: ClassVar[dict] = {
        "id": "builtin/riper-workflow",
        "description": "RIPER 5-phase workflow",
        "namespace": "builtin",
        "triggers": ["use riper", "riper workflow", "riper 工作流", "五阶段工作流"],
    }
    _SESSION_END: ClassVar[dict] = {
        "id": "builtin/session-end",
        "description": "Session wrap-up",
        "namespace": "builtin",
        "triggers": ["收工", "拜拜"],
    }
    _OTHER: ClassVar[dict] = {
        "id": "omx/plan",
        "description": "Planning",
        "namespace": "omx",
    }

    def _candidates(self) -> list[dict]:
        return [dict(self._SESSION_END), dict(self._RIPER), dict(self._OTHER)]

    def test_uppercase_name_token_is_explicit_signal(self) -> None:
        """Case-insensitivity: an all-caps mention of the guarded skill's
        distinctive name token counts as explicit intent."""
        service = _make_service()
        assert (
            service.has_explicit_guard_signal(
                "PLEASE SWITCH TO RIPER FOR THIS SPIKE",
                self._candidates(),
                "builtin/riper-workflow",
            )
            is True
        )

    def test_mixed_case_trigger_phrase_is_explicit_signal(self) -> None:
        service = _make_service()
        assert (
            service.has_explicit_guard_signal(
                "Let's Run The RiPeR Workflow Now", self._candidates(), "builtin/riper-workflow"
            )
            is True
        )

    def test_promotes_guarded_skill_on_explicit_signal(self) -> None:
        service = _make_service()
        match = service.explicit_guarded_skill_match(
            "Let's do this refactor with the RIPER approach", self._candidates()
        )
        assert match is not None
        assert match["id"] == "builtin/riper-workflow"

    def test_no_signal_no_promotion(self) -> None:
        service = _make_service()
        assert (
            service.explicit_guarded_skill_match("tidy up the module structure", self._candidates())
            is None
        )

    def test_session_end_excluded_has_own_fast_path(self) -> None:
        service = _make_service()
        assert service.explicit_guarded_skill_match("收工", self._candidates()) is None

    def test_guarded_skill_not_installed_no_promotion(self) -> None:
        service = _make_service()
        candidates = [dict(self._SESSION_END), dict(self._OTHER)]
        assert service.explicit_guarded_skill_match("switch to RIPER please", candidates) is None


class TestNoMatchExit:
    """Routing-precision audit 2026-08-29: AI triage must have a usable
    no-match exit and unstructured replies must never auto-inject.

    The hook path has no interactive confirmation gate — min_confidence
    (0.3) is the only injection gate — so a bare-token reply stamped with
    a fixed 0.82 silently injected skills into non-coding prompts
    (audit: 5/7 negatives misrouted). Unstructured replies are now a
    no-match; only structured JSON can produce a SkillRoute.
    """

    def _service_with_reply(self, content: str) -> TriageService:
        service = _make_service()
        service._llm = MagicMock()
        service._llm.configured.return_value = True
        service._llm.call.return_value = MagicMock(
            content=content, model="test", tokens_used=10, input_tokens=5, output_tokens=5
        )
        return service

    def test_bare_skill_id_reply_is_dropped(self) -> None:
        """Unstructured bare-token reply -> no auto-inject."""
        service = self._service_with_reply("skill-a")
        result = service.try_ai_triage("explain the GIL", [{"id": "skill-a", "intent": "test"}])
        assert result is None

    def test_fenced_skill_id_reply_is_dropped(self) -> None:
        """Unstructured fenced reply -> no auto-inject."""
        service = self._service_with_reply("```skill-a```")
        result = service.try_ai_triage("translate this", [{"id": "skill-a", "intent": "test"}])
        assert result is None

    def test_structured_null_skill_id_is_no_match(self) -> None:
        """Structured {"skill_id": null} -> no match."""
        service = self._service_with_reply('{"skill_id": null}')
        result = service.try_ai_triage("explain the GIL", [{"id": "skill-a", "intent": "test"}])
        assert result is None

    def test_structured_null_resets_unstructured_drops(self) -> None:
        """A structured NONE verdict is a structured reply: the consecutive
        unstructured-drop counter resets, same as on a structured match."""
        service = self._service_with_reply('{"skill_id": null}')
        service._unstructured_drops = 2
        result = service.try_ai_triage("explain the GIL", [{"id": "skill-a", "intent": "test"}])
        assert result is None
        assert service._unstructured_drops == 0

    def test_structured_match_honors_parsed_confidence(self) -> None:
        service = self._service_with_reply('{"skill_id": "skill-a", "confidence": 0.93}')
        result = service.try_ai_triage("fix the bug", [{"id": "skill-a", "intent": "test"}])
        assert result is not None
        assert result.match.confidence == 0.93

    def test_structured_match_default_confidence(self) -> None:
        """Structured reply without a valid confidence defaults to 0.88."""
        service = self._service_with_reply('{"skill_id": "skill-a"}')
        result = service.try_ai_triage("fix the bug", [{"id": "skill-a", "intent": "test"}])
        assert result is not None
        assert result.match.confidence == 0.88

    def test_parse_bare_none_tokens(self) -> None:
        """NONE/null bare tokens parse to skill_id None, not a skill."""
        service = _make_service()
        for token in ("NONE", "none", "null", "NULL", "N/A", "no-match"):
            assert service.parse_ai_triage_response(token)["skill_id"] is None, token

    def test_parse_fenced_none_token(self) -> None:
        service = _make_service()
        assert service.parse_ai_triage_response("```NONE```")["skill_id"] is None

    def test_parse_json_string_none(self) -> None:
        """A JSON "NONE" string normalizes to null."""
        service = _make_service()
        result = service.parse_ai_triage_response('{"skill_id": "NONE"}')
        assert result["skill_id"] is None
        assert result["structured"] is True

    def test_all_prompt_versions_have_no_match_exit(self) -> None:
        """Every registered prompt must tell the model how to say 'no match'
        — v1 and v3 shipped without one, forcing a skill on any prompt."""
        from vibesop.llm.triage_prompts import TriagePromptRegistry

        for version, template in TriagePromptRegistry.VERSIONS.items():
            lower = template.lower()
            assert "no skill matches" in lower, f"prompt {version} lacks a no-match exit"

    def test_all_prompt_versions_request_json_match_exit(self) -> None:
        """A bare-ID match exit would be silently dropped by the
        unstructured gate (positive-recall hole): every prompt must ask
        for the JSON form on matches."""
        from vibesop.llm.triage_prompts import TriagePromptRegistry

        for version, template in TriagePromptRegistry.VERSIONS.items():
            assert '"skill_id"' in template, f"prompt {version} lacks a JSON match exit"

    def test_minimal_fallback_prompt_carries_json_and_none_contract(self) -> None:
        """The no-prompt_builder fallback must match the registry prompts'
        JSON-match / NONE-decline contract — a forced-match fallback
        reintroduces the false-positive channel on builder-less routers."""
        service = _make_service()
        prompt = service.build_ai_triage_prompt("test query", "- skill-a: test")
        assert '"skill_id"' in prompt
        assert "NONE" in prompt

    def test_boolean_confidence_is_rejected(self) -> None:
        """JSON true/false are int subclasses; true must not become 1.0."""
        service = self._service_with_reply('{"skill_id": "skill-a", "confidence": true}')
        result = service.try_ai_triage("fix the bug", [{"id": "skill-a", "intent": "test"}])
        assert result is not None
        assert result.match.confidence == 0.88

    def test_prompt_declined_formats_round_trip_to_no_match(self) -> None:
        """Contract: every prompt version's DECLINED output format parses to
        no-match — pins prompt↔parser against drift (v4 must be added here)."""
        declined_formats = {
            "v1": "NONE",
            "v2": '{"skill_id": null}',
            "v3": '{"skill_id": null}',
        }
        service = _make_service()
        from vibesop.llm.triage_prompts import TriagePromptRegistry

        for version in TriagePromptRegistry.VERSIONS:
            assert version in declined_formats, f"add declined format for {version}"
            parsed = service.parse_ai_triage_response(declined_formats[version])
            assert parsed["skill_id"] is None, version
