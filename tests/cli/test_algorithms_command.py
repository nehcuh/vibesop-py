"""Tests for vibe algorithms command."""

from typer.testing import CliRunner

from vibesop.cli.main import app

runner = CliRunner()


class TestAlgorithmsCommand:
    """Test suite for algorithms command."""

    def test_algorithms_help(self) -> None:
        """Test algorithms help output."""
        result = runner.invoke(app, ["algorithms", "--help"])
        assert result.exit_code == 0
        assert "List all registered algorithms" in result.stdout

    def test_algorithms_list_empty(self, monkeypatch) -> None:
        """Test algorithms list when no algorithms registered."""
        from vibesop.core.algorithms import AlgorithmRegistry

        monkeypatch.setattr(AlgorithmRegistry, "_algorithms", {})
        monkeypatch.setattr(AlgorithmRegistry, "_descriptions", {})

        result = runner.invoke(app, ["algorithms"])
        assert result.exit_code == 0
        assert "No algorithms registered" in result.stdout

    def test_algorithms_list_with_items(self, monkeypatch) -> None:
        """Test algorithms list with registered algorithms."""
        from vibesop.core.algorithms import AlgorithmRegistry

        def dummy_fn():
            pass

        monkeypatch.setattr(AlgorithmRegistry, "_algorithms", {"test/algo": dummy_fn})
        monkeypatch.setattr(AlgorithmRegistry, "_descriptions", {"test/algo": "A test algorithm"})

        result = runner.invoke(app, ["algorithms"])
        assert result.exit_code == 0
        assert "test/algo" in result.stdout
        assert "A test algorithm" in result.stdout
