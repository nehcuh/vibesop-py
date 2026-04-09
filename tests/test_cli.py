"""Test CLI module."""

from typer.testing import CliRunner

from vibesop.cli.main import (
    _check_config,  # type: ignore[attr-defined]
    _check_dependencies,  # type: ignore[attr-defined]
    _check_llm_provider,  # type: ignore[attr-defined]
    _check_python_version,  # type: ignore[attr-defined]
    app,
)

runner = CliRunner()


class TestCLICommands:
    """Test CLI commands."""

    def test_version_command(self) -> None:
        """Test version command."""
        result = runner.invoke(app, ["version"])

        assert result.exit_code == 0
        assert "VibeSOP" in result.stdout
        assert "Python" in result.stdout

    def test_doctor_command(self) -> None:
        """Test doctor command."""
        result = runner.invoke(app, ["doctor"])

        assert result.exit_code in (0, 1)  # May fail if env not set up
        assert "Python version" in result.stdout
        assert "Dependencies" in result.stdout

    def test_doctor_checks_python_version(self) -> None:
        """Test Python version check."""
        status, message = _check_python_version()

        assert isinstance(status, bool)
        assert isinstance(message, str)

    def test_doctor_checks_dependencies(self) -> None:
        """Test dependencies check."""
        status, message = _check_dependencies()

        assert isinstance(status, bool)
        assert isinstance(message, str)

    def test_doctor_checks_config(self) -> None:
        """Test config check."""
        status, message = _check_config()

        assert isinstance(status, bool)
        assert isinstance(message, str)

    def test_doctor_checks_llm_provider(self) -> None:
        """Test LLM provider check."""
        status, message = _check_llm_provider()

        assert isinstance(status, bool)
        assert isinstance(message, str)


class TestRouteCommand:
    """Test route command."""

    def test_route_command_basic(self) -> None:
        """Test basic route command."""
        result = runner.invoke(app, ["route", "help me debug"])

        assert result.exit_code == 0

    def test_route_command_with_json(self) -> None:
        """Test route command with JSON output."""
        result = runner.invoke(app, ["route", "help me debug", "--json"])

        assert result.exit_code == 0

    def test_route_command_short_option(self) -> None:
        """Test route command with short -j option."""
        result = runner.invoke(app, ["route", "help me debug", "-j"])

        assert result.exit_code == 0


class TestRecordCommand:
    """Test record command."""

    def test_record_command_helpful(self) -> None:
        """Test recording a helpful selection."""
        result = runner.invoke(app, ["record", "test-skill", "test query"])

        assert result.exit_code == 0

    def test_record_command_not_helpful(self) -> None:
        """Test recording a not helpful selection."""
        result = runner.invoke(app, ["record", "test-skill", "test query", "--not-helpful"])

        assert result.exit_code == 0

    def test_record_command_short_option(self) -> None:
        """Test record command with short -H option."""
        result = runner.invoke(app, ["record", "test-skill", "test query", "-H"])

        assert result.exit_code == 0


class TestPreferencesCommand:
    """Test preferences command."""

    def test_preferences_command(self) -> None:
        """Test preferences command."""
        result = runner.invoke(app, ["preferences"])

        assert result.exit_code == 0

    def test_preferences_shows_stats(self) -> None:
        """Test preferences shows statistics."""
        result = runner.invoke(app, ["preferences"])

        assert "Preference Learning Statistics" in result.stdout


class TestTopSkillsCommand:
    """Test top-skills command."""

    def test_top_skills_command(self) -> None:
        """Test top-skills command."""
        result = runner.invoke(app, ["top-skills"])

        assert result.exit_code == 0

    def test_top_skills_with_limit(self) -> None:
        """Test top-skills with custom limit."""
        result = runner.invoke(app, ["top-skills", "--limit", "3"])

        assert result.exit_code == 0

    def test_top_skills_short_option(self) -> None:
        """Test top-skills with short -l option."""
        result = runner.invoke(app, ["top-skills", "-l", "5"])

        assert result.exit_code == 0


class TestSkillsCommand:
    """Test skills command."""

    def test_skills_command(self) -> None:
        """Test skills list command."""
        result = runner.invoke(app, ["skills", "list"])

        assert result.exit_code == 0

    def test_skills_with_all(self) -> None:
        """Test skills list with --all option."""
        result = runner.invoke(app, ["skills", "list", "--all"])

        assert result.exit_code == 0

    def test_skills_with_platform(self) -> None:
        """Test skills filtered by platform."""
        result = runner.invoke(app, ["skills", "list", "--platform", "claude-code"])

        assert result.exit_code == 0

    def test_skills_short_options(self) -> None:
        """Test skills with short options."""
        result = runner.invoke(app, ["skills", "list", "-a", "-p", "claude-code"])

        assert result.exit_code == 0


class TestSkillInfoCommand:
    """Test skills info command (moved from skill-info)."""

    def test_skill_info_command(self) -> None:
        """Test skills info command."""
        result = runner.invoke(app, ["skills", "info", "systematic-debugging"])

        # May fail if skill not found
        assert result.exit_code in (0, 1)

    def test_skill_info_not_found(self) -> None:
        """Test skills info with non-existent skill."""
        result = runner.invoke(app, ["skills", "info", "non-existent-skill-xyz"])

        assert result.exit_code == 1
        assert "not found" in result.stdout.lower()


class TestCLIEdgeCases:
    """Test CLI edge cases."""

    def test_no_args_is_help(self) -> None:
        """Test that no args shows help."""
        result = runner.invoke(app, [])

        # no_args_is_help=True causes exit code 2
        assert result.exit_code == 2
        assert "help" in result.stdout.lower()

    def test_help_command(self) -> None:
        """Test explicit help command."""
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "VibeSOP" in result.stdout

    def test_invalid_command(self) -> None:
        """Test invalid command."""
        result = runner.invoke(app, ["invalid-command"])

        assert result.exit_code != 0
