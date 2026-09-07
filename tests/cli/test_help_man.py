"""Tests for `vibe help` / `vibe man` subcommands and the -h short flag."""

from typer.testing import CliRunner

from vibesop.cli.main import app

runner = CliRunner()


# -- -h short flag -----------------------------------------------------------


def test_root_short_h_shows_help() -> None:
    result = runner.invoke(app, ["-h"])
    assert result.exit_code == 0
    assert "Usage:" in result.output


def test_leaf_command_inherits_short_h() -> None:
    result = runner.invoke(app, ["route", "-h"])
    assert result.exit_code == 0
    assert "Usage:" in result.output
    assert "route" in result.output


def test_sub_group_inherits_short_h() -> None:
    result = runner.invoke(app, ["trace", "-h"])
    assert result.exit_code == 0
    assert "Usage:" in result.output


def test_conflicting_command_keeps_own_h() -> None:
    """`vibe dashboard -h` stays bound to --host; --help still works."""
    result = runner.invoke(app, ["dashboard", "-h"])
    assert result.exit_code != 0
    assert "requires an argument" in result.output

    help_result = runner.invoke(app, ["dashboard", "--help"])
    assert help_result.exit_code == 0
    assert "Host to bind" in help_result.output


# -- vibe help ---------------------------------------------------------------


def test_help_without_args_shows_root_help() -> None:
    result = runner.invoke(app, ["help"])
    assert result.exit_code == 0
    assert "Usage:" in result.output


def test_help_for_leaf_command() -> None:
    result = runner.invoke(app, ["help", "route"])
    assert result.exit_code == 0
    assert "vibe route" in result.output


def test_help_for_nested_command() -> None:
    result = runner.invoke(app, ["help", "trace", "replay"])
    assert result.exit_code == 0
    assert "vibe trace replay" in result.output


def test_help_for_group() -> None:
    result = runner.invoke(app, ["help", "config"])
    assert result.exit_code == 0
    assert "vibe config" in result.output


def test_help_unknown_command_errors_with_suggestion() -> None:
    result = runner.invoke(app, ["help", "rout"])
    assert result.exit_code == 1
    assert "No such command" in result.output
    assert "route" in result.output  # close-match suggestion


def test_help_traverse_into_non_group_errors() -> None:
    result = runner.invoke(app, ["help", "route", "deeper"])
    assert result.exit_code == 1
    assert "not a command group" in result.output


def test_help_help_works() -> None:
    result = runner.invoke(app, ["help", "help"])
    assert result.exit_code == 0
    assert "help" in result.output


# -- vibe man ----------------------------------------------------------------


def test_man_root_renders_sections() -> None:
    result = runner.invoke(app, ["man"])
    assert result.exit_code == 0
    for section in ("NAME", "SYNOPSIS", "OPTIONS", "COMMANDS"):
        assert section in result.output
    assert "VIBE(1)" in result.output


def test_man_leaf_command_renders_sections() -> None:
    result = runner.invoke(app, ["man", "route"])
    assert result.exit_code == 0
    for section in ("NAME", "SYNOPSIS", "DESCRIPTION", "OPTIONS"):
        assert section in result.output
    assert "vibe route" in result.output


def test_man_nested_command() -> None:
    result = runner.invoke(app, ["man", "trace", "replay"])
    assert result.exit_code == 0
    assert "VIBE-TRACE-REPLAY(1)" in result.output


def test_man_roff_emits_valid_source() -> None:
    result = runner.invoke(app, ["man", "--roff", "route"])
    assert result.exit_code == 0
    assert '.TH "VIBE-ROUTE" "1"' in result.output
    assert ".SH NAME" in result.output
    assert ".SH SYNOPSIS" in result.output
    assert ".SH OPTIONS" in result.output
    # NAME line must contain a single-escaped roff dash, not \e\-
    assert "\\e\\-" not in result.output


def test_roff_text_escapes_leading_dots_and_hyphens() -> None:
    from vibesop.cli.commands.help_cmd import _roff_text

    assert _roff_text(".vibe/path") == "\\&.vibe/path"
    assert _roff_text("a-b") == "a\\-b"
    assert _roff_text("back\\slash") == "back\\eslash"
    assert _roff_text("a\n\nb") == "a\n.PP\nb"


def test_man_roff_group_lists_commands() -> None:
    result = runner.invoke(app, ["man", "--roff"])
    assert result.exit_code == 0
    assert ".SH COMMANDS" in result.output


def test_man_unknown_command_errors() -> None:
    result = runner.invoke(app, ["man", "nosuchcmd"])
    assert result.exit_code == 1
    assert "No such command" in result.output


def test_man_options_include_defaults_and_required() -> None:
    result = runner.invoke(app, ["man", "skills", "feedback"])
    assert result.exit_code == 0
    assert "[required]" in result.output
