"""Tests for vibe skill cleanup command."""

from __future__ import annotations


class TestCleanupRender:
    """Tests for cleanup render logic (no I/O)."""

    def test_empty_table(self):
        from vibesop.cli.commands.cleanup_cmd import _render_cleanup_table

        table = _render_cleanup_table([], [], [])
        assert table is not None

    def test_table_with_deprecations(self):
        from vibesop.cli.commands.cleanup_cmd import _render_cleanup_table
        from vibesop.core.skills.feedback_loop import RetentionSuggestion

        deprecate = [
            RetentionSuggestion(
                skill_id="gstack/broken",
                action="deprecate",
                reason="Bad quality",
                grade="F",
                days_since_last_use=90,
                total_routes=5,
                quality_score=0.1,
            )
        ]
        table = _render_cleanup_table([], deprecate, [])
        assert table is not None

    def test_table_with_archives(self):
        from vibesop.cli.commands.cleanup_cmd import _render_cleanup_table
        from vibesop.core.skills.feedback_loop import RetentionSuggestion

        archive = [
            RetentionSuggestion(
                skill_id="gstack/stale",
                action="archive",
                reason="Very old",
                grade="D",
                days_since_last_use=180,
                total_routes=1,
                quality_score=0.2,
            )
        ]
        table = _render_cleanup_table([], [], archive)
        assert table is not None

    def test_table_archive_shown_before_deprecate(self):
        from vibesop.cli.commands.cleanup_cmd import _render_cleanup_table
        from vibesop.core.skills.feedback_loop import RetentionSuggestion

        deprecate = [
            RetentionSuggestion(
                skill_id="gstack/low",
                action="deprecate",
                reason="Low",
                grade="F",
                days_since_last_use=30,
                total_routes=3,
                quality_score=0.1,
            )
        ]
        archive = [
            RetentionSuggestion(
                skill_id="gstack/ancient",
                action="archive",
                reason="Ancient",
                grade="D",
                days_since_last_use=200,
                total_routes=1,
                quality_score=0.2,
            )
        ]
        table = _render_cleanup_table(deprecate, archive, [])
        assert table is not None
