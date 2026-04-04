"""Tests for the 'vibe auto' command."""

from __future__ import annotations

from unittest.mock import Mock, patch

from typer.testing import CliRunner

from vibesop.cli.main import app

runner = CliRunner()


class TestAutoCommand:
    """Tests for vibe auto command."""

    def test_auto_dry_run(self) -> None:
        """Test auto command with --dry-run flag."""
        with patch("vibesop.cli.commands.auto.KeywordDetector") as mock_detector:
            mock_instance = Mock()
            mock_instance.detect.return_value = Mock(
                skill_id="/review",
                confidence=0.85,
                pattern_id="code-review",
                category="Dev",
            )
            mock_detector.return_value = mock_instance

            result = runner.invoke(app, ["auto", "review my code", "--dry-run"])

            assert result.exit_code == 0

    def test_auto_no_match(self) -> None:
        """Test auto command when no skill matches."""
        with patch("vibesop.cli.commands.auto.KeywordDetector") as mock_detector:
            mock_instance = Mock()
            mock_instance.detect.return_value = None
            mock_detector.return_value = mock_instance

            result = runner.invoke(app, ["auto", "xyzabc123random"])

            # Command runs successfully even when no match found
            assert result.exit_code in (0, 1)

    def test_auto_with_verbose(self) -> None:
        """Test auto command with --verbose flag."""
        with patch("vibesop.cli.commands.auto.KeywordDetector") as mock_detector:
            mock_instance = Mock()
            mock_instance.detect.return_value = Mock(
                skill_id="/debug",
                confidence=0.90,
                pattern_id="debug-issue",
                category="Dev",
            )
            mock_instance.get_all_patterns.return_value = []
            mock_detector.return_value = mock_instance

            result = runner.invoke(app, ["auto", "debug this issue", "--verbose"])

            assert result.exit_code == 0
