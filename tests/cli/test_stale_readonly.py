"""gate38: hot-path and render stale-skill checks are read-only.

``_check_stale_skills_post_route`` (every 20 routes) and
``_render_stale_suggestions`` (no-match panel) must never write lifecycle
state — auto-disposition is opt-in via ``stale --auto`` / ``optimize --apply``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from vibesop.core.skills.evaluator import SkillEvaluation

_SET_LIFECYCLE = "vibesop.core.skills.feedback_loop.SkillConfigManager.set_lifecycle"
_EVALUATOR = "vibesop.core.skills.feedback_loop.RoutingEvaluator"


def _f_grade_evaluations() -> dict[str, SkillEvaluation]:
    """A real F-grade candidate that WOULD be deprecated if auto were on
    (>=3 routes, accuracy<0.5, 45d unused — gate40 double conjunct)."""
    last_used = (datetime.now(UTC).replace(tzinfo=None) - timedelta(days=45)).isoformat()
    return {
        "test/bad": SkillEvaluation(
            skill_id="test/bad",
            total_routes=3,
            routing_accuracy=0.3,
            user_satisfaction=0.3,
            execution_success=0.3,
            usage_frequency=0.3,
            health_score=0.3,
            last_used=last_used,
        )
    }


def _mock_evaluator() -> MagicMock:
    evaluator = MagicMock()
    evaluator.evaluate_all_skills.return_value = _f_grade_evaluations()
    return evaluator


def test_render_stale_suggestions_writes_nothing() -> None:
    from vibesop.cli.render import _render_stale_suggestions

    with (
        patch(_EVALUATOR, return_value=_mock_evaluator()),
        patch(_SET_LIFECYCLE) as mock_set,
    ):
        text = _render_stale_suggestions()
        assert "test/bad" in text  # suggestion still surfaced
        mock_set.assert_not_called()


def test_check_stale_skills_post_route_writes_nothing(tmp_path, monkeypatch) -> None:
    from vibesop.cli.main import _check_stale_skills_post_route

    monkeypatch.chdir(tmp_path)
    vibe_dir = tmp_path / ".vibe"
    vibe_dir.mkdir()
    # Preset the counter so this call crosses the check interval.
    (vibe_dir / "routing_counter.json").write_text(
        json.dumps({"routes_since_last_check": 19, "check_interval": 20}),
        encoding="utf-8",
    )

    with (
        patch(_EVALUATOR, return_value=_mock_evaluator()),
        patch(_SET_LIFECYCLE) as mock_set,
    ):
        _check_stale_skills_post_route()
        mock_set.assert_not_called()

    # Counter reset proves the FeedbackLoop analysis path actually ran
    # (the function swallows exceptions, so this guards against a
    # vacuously-passing test).
    counter = json.loads((vibe_dir / "routing_counter.json").read_text(encoding="utf-8"))
    assert counter["routes_since_last_check"] == 0
