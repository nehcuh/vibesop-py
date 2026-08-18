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
