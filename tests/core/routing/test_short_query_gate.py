"""Regression tests for the short-query keyword gate (routing audit 2026-10-07).

Pins two invariants that session-context enrichment used to break:

1. The keyword-vs-LLM decision and the AI-triage short-query bypass both
   measure the user's ORIGINAL query (captured before
   ``ConversationContext.build_contextual_query`` enrichment). Enrichment
   prepends conversation context, so the enriched query is always longer —
   measuring it pushed 5-6 char production queries (e.g. ``相同方式继续``)
   into forced LLM triage (5-6s fallback_llm spans).
2. The bypass boundary matches ``keyword_match_max_chars`` semantics
   (``<=``): a query at exactly the threshold must not sit in the
   contradictory state "keyword mode selected, triage not bypassed".
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pytest

from vibesop.core.config.manager import RoutingConfig
from vibesop.core.matching import RoutingContext
from vibesop.core.models import RoutingLayer
from vibesop.core.routing import UnifiedRouter, _layers


class _CountingLLM:
    """Duck-typed LLM that records every call and returns unmatchable output."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def configured(self) -> bool:
        # TriageService 在发起调用前会先查 configured()（见 try_ai_triage 的
        # availability gate），缺了它会直接 AttributeError——与 base.LLMProvider
        # 的接口保持一致。
        return True

    def call(self, prompt: str = "", max_tokens: int = 100, temperature: float = 0.1) -> Any:
        self.calls.append(prompt)
        return type("R", (), {"content": "(no skill)"})()


def _fixture_candidates(tmp_path: Path) -> list[dict[str, Any]]:
    """One routable candidate; source_file must exist (routability gate)."""
    sf = tmp_path / "fixtures" / "diagnosis-skill" / "SKILL.md"
    sf.parent.mkdir(parents=True, exist_ok=True)
    sf.write_text("---\nid: diagnosis-skill\n---\n# body\n", encoding="utf-8")
    return [
        {
            "id": "diagnosis-skill",
            "name": "diagnosis-skill",
            "description": "Deep diagnosis and optimization",
            "namespace": "builtin",
            "keywords": ["diagnosis", "optimization"],
            "source_file": str(sf),
        }
    ]


def _triage_detail(result: Any) -> Any:
    return next(d for d in result.layer_details if d.layer == RoutingLayer.AI_TRIAGE)


class TestKeywordGateMeasuresOriginalQuery:
    def test_short_query_with_long_enrichment_skips_llm(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Enrichment must not push a short original query into LLM triage."""
        router = UnifiedRouter(project_root=tmp_path, config=RoutingConfig(enable_ai_triage=True))
        llm = _CountingLLM()
        router.set_llm(llm)

        def _enrich(self: Any, query: str) -> str:
            return f"（会话上下文）此前对话已经涵盖若干其它主题内容。{query}"

        monkeypatch.setattr(
            "vibesop.core.conversation.ConversationContext.build_contextual_query",
            _enrich,
        )

        result = router._single_skill_route(
            "相同方式继续",
            candidates=_fixture_candidates(tmp_path),
            context=RoutingContext(conversation_id="conv-short"),
        )

        assert len("相同方式继续") <= 15
        assert llm.calls == []  # 短 query 不得触发 LLM（修复前此处会烧 1 次）
        assert _triage_detail(result).reason.startswith("Short-query bypass")

    def test_long_query_still_forces_triage(self, tmp_path: Path) -> None:
        """Long queries keep the forced-triage path (no behavior change)."""
        router = UnifiedRouter(project_root=tmp_path, config=RoutingConfig(enable_ai_triage=True))
        llm = _CountingLLM()
        router.set_llm(llm)

        query = "这是一个明显超过十五个字符的长查询测例"
        assert len(query) > 15
        router._single_skill_route(query, candidates=_fixture_candidates(tmp_path))

        assert len(llm.calls) == 1


class TestShortQueryBypassBoundary:
    def test_exactly_threshold_chars_bypass_triage(self, tmp_path: Path) -> None:
        """len(query) == keyword_match_max_chars stays in keyword mode."""
        router = UnifiedRouter(project_root=tmp_path, config=RoutingConfig(enable_ai_triage=True))
        llm = _CountingLLM()
        router.set_llm(llm)

        query = "一二三四五六七八九十壹贰叁肆伍"
        assert len(query) == 15
        result = router._single_skill_route(query, candidates=_fixture_candidates(tmp_path))

        assert llm.calls == []  # 修复前（< 15）恰好 15 字会进 triage
        assert _triage_detail(result).reason.startswith("Short-query bypass (<=")

    def test_keyword_gate_inclusive_boundary(self, tmp_path: Path) -> None:
        """与 _layers 旁路口径一致：恰好 15 字走词法，16 字走 LLM。"""
        router = UnifiedRouter(project_root=tmp_path, config=RoutingConfig(enable_ai_triage=True))
        router.set_llm(_CountingLLM())

        assert router._should_use_keyword_routing("x" * 15) is True
        assert router._should_use_keyword_routing("x" * 16) is False


class TestTriageLayerBypassSource:
    """Unit tests for _layers.try_ai_triage_layer bypass measurement."""

    @staticmethod
    def _router(tmp_path: Path) -> tuple[UnifiedRouter, _CountingLLM]:
        router = UnifiedRouter(project_root=tmp_path, config=RoutingConfig(enable_ai_triage=True))
        llm = _CountingLLM()
        router.set_llm(llm)
        return router, llm

    def test_bypass_measures_original_query_when_given(self, tmp_path: Path) -> None:
        router, llm = self._router(tmp_path)
        match, detail = _layers.try_ai_triage_layer(
            router,
            "（会话上下文）很长的增强查询内容拼接在这里",
            [],
            None,
            force=False,
            original_query="帮我发布吧",
        )
        assert match is None
        assert detail.reason.startswith("Short-query bypass")
        assert llm.calls == []

    def test_bypass_falls_back_to_query_without_original(self, tmp_path: Path) -> None:
        router, llm = self._router(tmp_path)
        match, detail = _layers.try_ai_triage_layer(
            router,
            "（会话上下文）很长的增强查询内容拼接在这里",
            _fixture_candidates(tmp_path),
            None,
            force=False,
        )
        assert match is None
        assert "Short-query bypass" not in detail.reason
        # 无 original_query 时退回量 query（长）→ 不旁路 → 确实进入了 LLM 路径。
        # 注：候选集不能为空——prefilter 无候选可召回时会先于 LLM 提前返回。
        assert len(llm.calls) == 1

    def test_force_overrides_bypass(self, tmp_path: Path) -> None:
        router, llm = self._router(tmp_path)
        match, detail = _layers.try_ai_triage_layer(
            router,
            "帮我发布吧",
            _fixture_candidates(tmp_path),
            None,
            force=True,
            original_query="帮我发布吧",
        )
        assert match is None
        # force=True 时旁路整体跳过，即使 original_query 很短也照走 LLM。
        assert "Short-query bypass" not in detail.reason
        assert len(llm.calls) == 1
