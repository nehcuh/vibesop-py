"""D1: disable-model-invocation candidates stay in the EXPLICIT pool only."""

from __future__ import annotations

from vibesop.core.routing import matcher_pipeline
from vibesop.core.routing.matcher_pipeline import filter_invocation_disabled_candidates
from vibesop.core.routing.unified import UnifiedRouter


def test_filter_drops_flagged_ids() -> None:
    kept = filter_invocation_disabled_candidates(
        [
            {"id": "open", "disable_model_invocation": False},
            {"id": "grill-me", "disable_model_invocation": True},
            {"id": "other"},
        ]
    )
    assert [c["id"] for c in kept] == ["open", "other"]


def test_decomposition_catalog_drops_invocation_disabled() -> None:
    router = UnifiedRouter.__new__(UnifiedRouter)
    router._get_cached_candidates = lambda: [  # type: ignore[method-assign]
        {"id": "open", "description": "ok", "disable_model_invocation": False},
        {"id": "grill-me", "description": "grill", "disable_model_invocation": True},
        {
            "id": "builtin/verify-result",
            "description": "verify",
            "disable_model_invocation": True,
        },
    ]
    catalog = UnifiedRouter._build_decomposition_skills(router)
    joined = "\n".join(catalog)
    assert "open:" in joined
    assert "grill-me" not in joined
    assert "verify-result" not in joined


def test_invocation_disabled_ids_unwraps_nested_router() -> None:
    class Inner:
        def __init__(self) -> None:
            self._candidate_manager = type(
                "CM",
                (),
                {
                    "get_cached_candidates": staticmethod(
                        lambda: [
                            {"id": "grill-me", "disable_model_invocation": True},
                            {"id": "open", "disable_model_invocation": False},
                        ]
                    )
                },
            )()

    wrapper = type("AgentRouter", (), {"_router": Inner()})()
    fn = matcher_pipeline.invocation_disabled_skill_ids
    assert fn(wrapper) == {"grill-me"}


def test_invocation_disabled_ids_raises_on_broken_catalog() -> None:
    """8.3.1 (A-5): a broken catalog fails closed instead of silently
    re-admitting explicit-only skills into auto-routing."""
    import pytest

    class BrokenManager:
        def get_cached_candidates(self):
            raise RuntimeError("catalog exploded")

    inner = type("Inner", (), {"_candidate_manager": BrokenManager()})()
    wrapper = type("AgentRouter", (), {"_router": inner})()
    with pytest.raises(RuntimeError, match="catalog exploded"):
        matcher_pipeline.invocation_disabled_skill_ids(wrapper)


def test_triage_cannot_select_disabled_skill(tmp_path) -> None:
    """8.3.1 (P1-2): the triage funnel filters invocation-disabled skills, so
    even an LLM that names one cannot get it injected."""
    import json
    from types import SimpleNamespace

    from vibesop.core.optimization import CandidatePrefilter
    from vibesop.core.routing import RoutingConfig
    from vibesop.core.routing.cache import CacheManager
    from vibesop.core.routing.triage_service import TriageService
    from vibesop.llm.cost_tracker import TriageCostTracker

    class _FakeLLM:
        def configured(self) -> bool:
            return True

        def call(self, prompt: str, **kwargs):
            return SimpleNamespace(
                content=json.dumps({"skill_id": "builtin/verify-result", "confidence": 0.95})
            )

    service = TriageService(
        config=RoutingConfig(enable_ai_triage=True),
        cost_tracker=TriageCostTracker(storage_dir=tmp_path),
        prefilter=CandidatePrefilter(),
        cache_manager=CacheManager(cache_dir=tmp_path),
        get_skill_source=lambda _sid, ns: ns,
    )
    service._llm = _FakeLLM()

    candidates = [
        {
            "id": "builtin/verify-result",
            "description": "verify",
            "disable_model_invocation": True,
            "management_only": False,
        },
        {
            "id": "open",
            "description": "open skill",
            "disable_model_invocation": False,
            "management_only": False,
        },
    ]
    result = service.try_ai_triage("帮我验收这次的结果", candidates)
    if result is not None and result.match is not None:
        assert result.match.skill_id != "builtin/verify-result"

    # Positive control: the same harness CAN select a non-disabled skill, so
    # the block above is the filter's doing, not a dead LLM path.
    class _FakeLLMOpen:
        def configured(self) -> bool:
            return True

        def call(self, prompt: str, **kwargs):
            return SimpleNamespace(content=json.dumps({"skill_id": "open", "confidence": 0.9}))

    service._llm = _FakeLLMOpen()
    open_result = service.try_ai_triage("另一个查询", candidates)
    assert open_result is not None
    assert open_result.match is not None
    assert open_result.match.skill_id == "open"
