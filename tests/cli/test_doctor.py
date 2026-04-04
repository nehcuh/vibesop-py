"""Tests for the 'vibe doctor' command."""

from __future__ import annotations

from typer.testing import CliRunner

from vibesop.cli.main import app

runner = CliRunner()


class TestDoctorCommand:
    """Tests for vibe doctor command."""

    def test_doctor_runs_successfully(self) -> None:
        """Test that doctor command completes without errors."""
        result = runner.invoke(app, ["doctor"])

        assert result.exit_code == 0
        assert len(result.stdout) > 0

    def test_doctor_shows_python_version(self) -> None:
        """Test that doctor command shows Python version."""
        result = runner.invoke(app, ["doctor"])

        assert result.exit_code == 0
        assert "Python" in result.stdout or "python" in result.stdout
