"""D1: disable-model-invocation candidates stay in the EXPLICIT pool only."""

from __future__ import annotations

from vibesop.core.routing.matcher_pipeline import filter_invocation_disabled_candidates


def test_filter_drops_flagged_ids() -> None:
    kept = filter_invocation_disabled_candidates(
        [
            {"id": "open", "disable_model_invocation": False},
            {"id": "grill-me", "disable_model_invocation": True},
            {"id": "other"},
        ]
    )
    assert [c["id"] for c in kept] == ["open", "other"]
