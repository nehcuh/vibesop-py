"""Tests for AI Triage prefiltering and structured parsing."""

from vibesop.core.routing.unified import UnifiedRouter


def test_prefilter_ai_triage_candidates_reduces_count():
    """Keyword prefilter should reduce candidates sent to LLM."""
    candidates = [
        {"id": f"skill_{i}", "name": f"Skill {i}", "description": f"Desc {i}", "intent": "", "keywords": ["other"]}
        for i in range(20)
    ]
    # Add a few debug-related skills that should be prioritized
    candidates[5]["keywords"] = ["debug"]
    candidates[12]["keywords"] = ["debug", "error"]

    router = UnifiedRouter()
    filtered = router._prefilter_ai_triage_candidates("debug error", candidates, max_skills=5)

    assert len(filtered) <= 5
    # The debug skills should be present
    ids = {c["id"] for c in filtered}
    assert "skill_5" in ids or "skill_12" in ids


def test_prefilter_ai_triage_candidates_no_change_when_below_max():
    candidates = [
        {"id": f"skill_{i}", "name": f"Skill {i}", "description": f"Desc {i}", "intent": "", "keywords": []}
        for i in range(3)
    ]
    router = UnifiedRouter()
    filtered = router._prefilter_ai_triage_candidates("debug", candidates, max_skills=5)
    assert len(filtered) == 3
