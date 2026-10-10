"""Real config validation through the public route CLI error boundary."""

import pytest
from typer.testing import CliRunner

from vibesop.cli.main import app


@pytest.mark.parametrize(
    "value", ["[/bold red]", "[red]bad[/red]", "[link=https://example.com]bad[/link]"]
)
def test_route_invalid_config_prints_literal_input(tmp_path, monkeypatch, value):
    config = tmp_path / ".vibe" / "config.toml"
    config.parent.mkdir()
    config.write_text(f'[routing]\nkeyword_match_max_chars = "{value}"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        app, ["route", "--no-session", "--no-replay", "--yes", "--json", "test query"]
    )
    assert result.exit_code == 2, result.output
    assert "Invalid routing configuration" in result.output
    assert "keyword_match_max_chars" in result.output
    assert value in result.output
    assert "MarkupError" not in result.output
