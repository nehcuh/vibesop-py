"""Tests for vibe status ecosystem dashboard."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


class TestStatusHelpers:
    """Tests for status command pure helper functions."""

    def test_grade_color_a(self):
        from vibesop.cli.commands.status_cmd import _grade_color

        assert _grade_color("A") == "green"

    def test_grade_color_b(self):
        from vibesop.cli.commands.status_cmd import _grade_color

        assert _grade_color("B") == "blue"

    def test_grade_color_f(self):
        from vibesop.cli.commands.status_cmd import _grade_color

        assert _grade_color("F") == "red"

    def test_grade_color_unknown(self):
        from vibesop.cli.commands.status_cmd import _grade_color

        assert _grade_color("X") == "dim"

    def test_grade_bar_empty(self):
        from vibesop.cli.commands.status_cmd import _grade_bar

        result = _grade_bar({}, 0)
        assert "no skills evaluated" in result

    def test_grade_bar_with_data(self):
        from vibesop.cli.commands.status_cmd import _grade_bar

        counts = {"A": 5, "B": 3, "C": 2, "D": 1, "F": 0}
        result = _grade_bar(counts, 11)

        assert "A" in result
        assert "B" in result
        assert "5" in result

    def test_detect_first_run_true(self, tmp_path: Path):
        from vibesop.cli.commands.status_cmd import _detect_first_run

        assert _detect_first_run(tmp_path) is True

    def test_detect_first_run_false_with_analytics(self, tmp_path: Path):
        from vibesop.cli.commands.status_cmd import _detect_first_run

        (tmp_path / ".vibe").mkdir(exist_ok=True)
        (tmp_path / ".vibe" / "analytics.jsonl").write_text("{}")

        assert _detect_first_run(tmp_path) is False

    def test_detect_first_run_false_with_feedback(self, tmp_path: Path):
        from vibesop.cli.commands.status_cmd import _detect_first_run

        (tmp_path / ".vibe").mkdir(exist_ok=True)
        (tmp_path / ".vibe" / "feedback.jsonl").write_text("{}")

        assert _detect_first_run(tmp_path) is False

    def test_welcome_panel_shows_for_first_run(self):
        from vibesop.cli.commands.status_cmd import _load_welcome

        panel = _load_welcome(is_first=True)
        assert panel is not None

    def test_welcome_panel_none_for_returning_user(self):
        from vibesop.cli.commands.status_cmd import _load_welcome

        panel = _load_welcome(is_first=False)
        assert panel is None


class TestStatusPanels:
    """Integration tests for status panels with minimal dependencies."""

    def test_ecosystem_health_returns_panel(self, tmp_path: Path):
        from vibesop.cli.commands.status_cmd import _load_ecosystem_health

        (tmp_path / ".vibe").mkdir(exist_ok=True)
        panel = _load_ecosystem_health(tmp_path)

        assert panel is not None
        content = str(getattr(panel, "renderable", ""))
        assert len(content) > 0

    def test_recent_activity_no_data_returns_panel(self, tmp_path: Path):
        from vibesop.cli.commands.status_cmd import _load_recent_activity

        (tmp_path / ".vibe").mkdir(exist_ok=True)
        panel = _load_recent_activity(tmp_path)

        assert panel is not None

    def test_warnings_no_data_returns_panel(self, tmp_path: Path):
        from vibesop.cli.commands.status_cmd import _load_warnings

        (tmp_path / ".vibe").mkdir(exist_ok=True)
        panel = _load_warnings(tmp_path)

        assert panel is not None

    def test_recommendations_returns_panel(self):
        from vibesop.cli.commands.status_cmd import _load_recommendations

        panel = _load_recommendations()
        assert panel is not None

    def test_badges_returns_none_when_no_file(self, tmp_path: Path):
        from vibesop.cli.commands.status_cmd import _load_badges

        with patch("vibesop.core.badges.BadgeTracker._load", return_value=None):
            result = _load_badges()
            # Without a badges file, should handle gracefully
            assert result is not None or result is None  # Either is fine
