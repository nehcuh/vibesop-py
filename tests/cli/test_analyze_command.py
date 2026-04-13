"""Tests for vibe analyze command."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from vibesop.cli.main import app
from vibesop.integrations import IntegrationStatus

runner = CliRunner()


class TestAnalyzeCommand:
    """Test suite for analyze command."""

    def test_analyze_unknown_target(self) -> None:
        """Test analyze with invalid target."""
        result = runner.invoke(app, ["analyze", "unknown"])
        assert result.exit_code == 1
        assert "Unknown analysis target" in result.stdout

    @patch("vibesop.core.session_analyzer.SessionAnalyzer")
    def test_analyze_session_no_file(self, mock_analyzer_cls) -> None:
        """Test analyze session when no session file exists."""
        mock_analyzer = MagicMock()
        mock_analyzer_cls.return_value = mock_analyzer

        result = runner.invoke(app, ["analyze", "session"])
        assert result.exit_code == 0
        assert "No session file found" in result.stdout

    @patch("vibesop.core.session_analyzer.SessionAnalyzer")
    def test_analyze_session_with_suggestions(self, mock_analyzer_cls, monkeypatch, tmp_path) -> None:
        """Test analyze session with skill suggestions."""
        monkeypatch.chdir(tmp_path)
        session_file = tmp_path / "session.jsonl"
        session_file.write_text("{}")

        mock_analyzer = MagicMock()
        suggestion = MagicMock()
        suggestion.skill_name = "debug"
        suggestion.description = "Debug skill"
        suggestion.frequency = 5
        suggestion.confidence = 0.85
        suggestion.trigger_queries = ["help debug"]
        suggestion.estimated_value = "high"
        mock_analyzer.analyze_session_file.return_value = [suggestion]
        mock_analyzer_cls.return_value = mock_analyzer

        result = runner.invoke(app, ["analyze", "session", str(session_file)])
        assert result.exit_code == 0
        assert "Found 1 potential skills" in result.stdout

    @patch("vibesop.core.session_analyzer.SessionAnalyzer")
    def test_analyze_session_empty_suggestions(self, mock_analyzer_cls, monkeypatch, tmp_path) -> None:
        """Test analyze session with no patterns."""
        monkeypatch.chdir(tmp_path)
        session_file = tmp_path / "session.jsonl"
        session_file.write_text("{}")

        mock_analyzer = MagicMock()
        mock_analyzer.analyze_session_file.return_value = []
        mock_analyzer_cls.return_value = mock_analyzer

        result = runner.invoke(app, ["analyze", "session", str(session_file)])
        assert result.exit_code == 0
        assert "No strong patterns detected" in result.stdout

    @patch("vibesop.core.session_analyzer.SessionAnalyzer")
    def test_analyze_patterns_directory(self, mock_analyzer_cls, monkeypatch, tmp_path) -> None:
        """Test analyze patterns on a directory."""
        monkeypatch.chdir(tmp_path)
        session_file = tmp_path / "session.jsonl"
        session_file.write_text("{}")

        mock_analyzer = MagicMock()
        mock_analyzer.analyze_session_file.return_value = []
        mock_analyzer_cls.return_value = mock_analyzer

        result = runner.invoke(app, ["analyze", "patterns", str(tmp_path)])
        assert result.exit_code == 0
        assert "Pattern Analysis" in result.stdout
        assert "Found 1 session files" in result.stdout

    @patch("vibesop.security.scanner.SecurityScanner")
    def test_analyze_security_clean(self, mock_scanner_cls, monkeypatch, tmp_path) -> None:
        """Test analyze security with no issues."""
        monkeypatch.chdir(tmp_path)
        py_file = tmp_path / "test.py"
        py_file.write_text("print('hello')")

        mock_scanner = MagicMock()
        mock_scanner.scan_file.return_value = []
        mock_scanner_cls.return_value = mock_scanner

        result = runner.invoke(app, ["analyze", "security", str(tmp_path)])
        assert result.exit_code == 0
        assert "No security issues found" in result.stdout

    @patch("vibesop.security.scanner.SecurityScanner")
    def test_analyze_security_with_issues(self, mock_scanner_cls, monkeypatch, tmp_path) -> None:
        """Test analyze security with issues found."""
        monkeypatch.chdir(tmp_path)
        py_file = tmp_path / "test.py"
        py_file.write_text("eval('1')")

        mock_scanner = MagicMock()
        mock_scanner.scan_file.return_value = [
            {"file": str(py_file), "severity": "high", "message": "Dangerous eval", "line": 1}
        ]
        mock_scanner_cls.return_value = mock_scanner

        result = runner.invoke(app, ["analyze", "security", str(tmp_path)])
        assert result.exit_code == 0
        assert "Found 1 potential issues" in result.stdout
        assert "high" in result.stdout

    @patch("vibesop.security.scanner.SecurityScanner")
    def test_analyze_security_json(self, mock_scanner_cls, monkeypatch, tmp_path) -> None:
        """Test analyze security --json."""
        monkeypatch.chdir(tmp_path)
        py_file = tmp_path / "test.py"
        py_file.write_text("x = 1")

        mock_scanner = MagicMock()
        mock_scanner.scan_file.return_value = []
        mock_scanner_cls.return_value = mock_scanner

        result = runner.invoke(app, ["analyze", "security", str(tmp_path), "--json"])
        assert result.exit_code == 0
        # JSON output should contain empty list
        assert "[]" in result.stdout

    @patch("vibesop.integrations.IntegrationManager")
    @patch("vibesop.integrations.IntegrationDetector")
    def test_analyze_integrations(self, mock_detector_cls, mock_mgr_cls) -> None:
        """Test analyze integrations."""
        mock_detector = MagicMock()
        mock_detector.skills_base_path = Path("/tmp/skills")
        mock_detector_cls.return_value = mock_detector

        mock_mgr = MagicMock()
        integration = MagicMock()
        integration.status = IntegrationStatus.INSTALLED
        integration.name = "gstack"
        integration.description = "Virtual team"
        integration.version = "1.0.0"
        mock_mgr.list_integrations.return_value = [integration]
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(app, ["analyze", "integrations"])
        assert result.exit_code == 0
        assert "Detecting Integrations" in result.stdout
        assert "gstack" in result.stdout

    @patch("vibesop.integrations.IntegrationManager")
    @patch("vibesop.integrations.IntegrationDetector")
    def test_analyze_integrations_no_path(self, mock_detector_cls, mock_mgr_cls) -> None:
        """Test analyze integrations when no skills path found."""
        mock_detector = MagicMock()
        mock_detector.skills_base_path = None
        mock_detector.SKILLS_BASE_PATHS = [Path("/tmp/skills")]
        mock_detector_cls.return_value = mock_detector

        mock_mgr = MagicMock()
        mock_mgr.list_integrations.return_value = []
        mock_mgr_cls.return_value = mock_mgr

        result = runner.invoke(app, ["analyze", "integrations"])
        assert result.exit_code == 0
        assert "No skills path found" in result.stdout
