"""Tests for vibe config command."""

from typer.testing import CliRunner

from vibesop.cli.main import app

runner = CliRunner()


class TestConfigCommand:
    """Test suite for config command."""

    def test_config_default(self) -> None:
        """Test config command without flags."""
        result = runner.invoke(app, ["config"])
        assert result.exit_code == 0
        assert "VibeSOP" in result.stdout
        assert "Configuration" in result.stdout
        assert "Keyword, TF-IDF, Fuzzy" in result.stdout

    def test_config_semantic_deprecated(self) -> None:
        """Test config --semantic shows deprecated warning."""
        result = runner.invoke(app, ["config", "--semantic"])
        assert result.exit_code == 0
        assert "Deprecated" in result.stdout
        assert "Semantic module has been removed" in result.stdout
