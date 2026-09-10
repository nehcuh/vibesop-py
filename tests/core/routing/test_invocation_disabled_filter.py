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
