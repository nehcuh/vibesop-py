"""Tests for optimize_cmd.py."""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from vibesop.cli.main import app
from vibesop.core.models import SkillLifecycle
from vibesop.core.skills.config_manager import SkillConfig
from vibesop.core.skills.evaluator import SkillEvaluation

runner = CliRunner()

_EVALUATOR = "vibesop.core.skills.evaluator.RoutingEvaluator"
_SET_LIFECYCLE = "vibesop.core.skills.feedback_loop.SkillConfigManager.set_lifecycle"
_GET_CONFIG = "vibesop.core.skills.feedback_loop.SkillConfigManager.get_skill_config"


def _days_ago(days: int) -> str:
    return (datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)).isoformat()


def _candidate_evaluations() -> dict[str, SkillEvaluation]:
    """One real candidate per lifecycle action: deprecate, archive, boost."""
    return {
        # F-grade, 30+ days unused, < 3 uses → deprecate
        "test/bad": SkillEvaluation(
            skill_id="test/bad",
            total_routes=1,
            routing_accuracy=0.3,
            user_satisfaction=0.3,
            execution_success=0.3,
            usage_frequency=0.3,
            health_score=0.3,
            last_used=_days_ago(45),
        ),
        # C-grade, 90+ days unused → archive
        "test/stale": SkillEvaluation(
            skill_id="test/stale",
            total_routes=5,
            routing_accuracy=0.65,
            user_satisfaction=0.65,
            execution_success=0.65,
            usage_frequency=0.65,
            health_score=0.65,
            last_used=_days_ago(120),
        ),
        # A-grade, sufficient data → boost (restores deprecated → active)
        "test/great": SkillEvaluation(
            skill_id="test/great",
            total_routes=5,
            routing_accuracy=0.95,
            user_satisfaction=0.95,
            execution_success=0.95,
            usage_frequency=0.95,
            health_score=0.95,
        ),
    }


def _mock_evaluator(evaluations: dict[str, SkillEvaluation]) -> MagicMock:
    evaluator = MagicMock()
    evaluator.evaluate_all_skills.return_value = evaluations
    return evaluator


def _deprecated_config(skill_id: str) -> SkillConfig:
    return SkillConfig(skill_id=skill_id, lifecycle=SkillLifecycle.DEPRECATED)


class TestOptimizeCommand:
    """Tests for vibe optimize command."""

    def test_optimize_help(self):
        result = runner.invoke(app, ["optimize", "--help"])
        assert result.exit_code == 0
        assert "optimize" in result.stdout.lower()

    def test_optimize_dry_run(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["optimize", "--days", "1"])
        # May return 0 or 1 depending on data availability
        assert "Routing Health" in result.stdout or result.exit_code == 0

    def test_optimize_with_days(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["optimize", "--days", "7"])
        assert result.exit_code in (0, 1)

    def test_optimize_with_apply_flag(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["optimize", "--apply", "--days", "1"])
        # --apply may fail gracefully if no evaluator data
        assert "Applied Optimizations" in result.stdout or "Routing Health" in result.stdout


class TestOptimizeLifecycleGating:
    """gate38: dry-run must not write lifecycle; --apply writes only real ones."""

    def test_dry_run_never_writes_lifecycle(self, tmp_path, monkeypatch):
        """must-NOT: `vibe optimize` without --apply shows candidates but
        writes no lifecycle state."""
        monkeypatch.chdir(tmp_path)
        with (
            patch(_EVALUATOR, return_value=_mock_evaluator(_candidate_evaluations())),
            patch(_SET_LIFECYCLE) as mock_set,
        ):
            result = runner.invoke(app, ["optimize"])
            assert result.exit_code == 0
            mock_set.assert_not_called()
        # Candidates are still surfaced in the preview
        assert "test/bad" in result.stdout
        assert "Applied Optimizations" not in result.stdout
        # Dry-run must not create the optimization log either
        assert not (tmp_path / ".vibe" / "optimization-log.jsonl").exists()

    def test_apply_writes_and_logs_all_three_action_types(self, tmp_path, monkeypatch):
        """--apply deprecates F-grade, archives stale C-grade, restores
        deprecated A-grade — and only actually-written skills reach the log
        and the Applied Optimizations list."""
        monkeypatch.chdir(tmp_path)
        with (
            patch(_EVALUATOR, return_value=_mock_evaluator(_candidate_evaluations())),
            patch(_SET_LIFECYCLE) as mock_set,
            patch(_GET_CONFIG, side_effect=_deprecated_config),
        ):
            result = runner.invoke(app, ["optimize", "--apply"])
            assert result.exit_code == 0

        writes = {c.args[0]: c.args[1] for c in mock_set.call_args_list}
        assert writes == {
            "test/bad": "deprecated",
            "test/stale": "archived",
            "test/great": "active",
        }
        for skill_id in ("test/bad", "test/stale", "test/great"):
            assert skill_id in result.stdout

        log_path = tmp_path / ".vibe" / "optimization-log.jsonl"
        assert log_path.exists()
        entries = [json.loads(line) for line in log_path.read_text().splitlines()]
        assert len(entries) == 1
        assert sorted(entries[0]["applied_skills"]) == [
            "test/bad",
            "test/great",
            "test/stale",
        ]

    def test_apply_with_no_candidates_writes_nothing(self, tmp_path, monkeypatch):
        """--apply with no candidates: no lifecycle write, no log entry."""
        monkeypatch.chdir(tmp_path)
        with (
            patch(_EVALUATOR, return_value=_mock_evaluator({})),
            patch(_SET_LIFECYCLE) as mock_set,
        ):
            result = runner.invoke(app, ["optimize", "--apply"])
            assert result.exit_code == 0
            mock_set.assert_not_called()
        assert "Applied Optimizations" in result.stdout
        assert not (tmp_path / ".vibe" / "optimization-log.jsonl").exists()

    def test_apply_excludes_noop_boost_from_log(self, tmp_path, monkeypatch):
        """must-NOT: a boost suggestion for an already-active skill is not
        applied and must not appear in the log."""
        monkeypatch.chdir(tmp_path)
        evaluations = {"test/great": _candidate_evaluations()["test/great"]}

        def _active_config(skill_id: str) -> SkillConfig:
            return SkillConfig(skill_id=skill_id, lifecycle=SkillLifecycle.ACTIVE)

        with (
            patch(_EVALUATOR, return_value=_mock_evaluator(evaluations)),
            patch(_SET_LIFECYCLE) as mock_set,
            patch(_GET_CONFIG, side_effect=_active_config),
        ):
            result = runner.invoke(app, ["optimize", "--apply"])
            assert result.exit_code == 0
            mock_set.assert_not_called()
        assert not (tmp_path / ".vibe" / "optimization-log.jsonl").exists()
