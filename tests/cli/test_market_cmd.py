"""Tests for vibe market subcommands."""

from typing import Any
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from vibesop.cli.main import app

runner = CliRunner()


class TestMarketSearch:
    """Tests for vibe market search."""

    @patch("vibesop.cli.commands.market_cmd.GitHubSkillCrawler")
    def test_search_basic(self, mock_crawler_cls: Any) -> None:
        from vibesop.market.crawler import SkillRepo
        mock_crawler = MagicMock()
        mock_crawler.search.return_value = [
            SkillRepo(
                name="skill-a",
                full_name="user/skill-a",
                description="A test skill",
                stars=42,
                topics=["vibesop-skill"],
                html_url="https://github.com/user/skill-a",
            )
        ]
        mock_crawler_cls.return_value = mock_crawler

        result = runner.invoke(app, ["market", "search", "test"])
        assert result.exit_code == 0
        assert "skill-a" in result.output
        assert "A test skill" in result.output
        assert "42" in result.output

    @patch("vibesop.cli.commands.market_cmd.GitHubSkillCrawler")
    def test_search_json(self, mock_crawler_cls: Any) -> None:
        from vibesop.market.crawler import SkillRepo
        mock_crawler = MagicMock()
        mock_crawler.search.return_value = [
            SkillRepo(
                name="skill-a",
                full_name="user/skill-a",
                description="A test skill",
                stars=42,
                topics=["vibesop-skill"],
                html_url="https://github.com/user/skill-a",
            )
        ]
        mock_crawler_cls.return_value = mock_crawler

        result = runner.invoke(app, ["market", "search", "test", "--json"])
        assert result.exit_code == 0
        assert "skill-a" in result.output
        assert "user/skill-a" in result.output
        assert "42" in result.output

    @patch("vibesop.cli.commands.market_cmd.GitHubSkillCrawler")
    def test_search_no_results(self, mock_crawler_cls: Any) -> None:
        mock_crawler = MagicMock()
        mock_crawler.search.return_value = []
        mock_crawler_cls.return_value = mock_crawler

        result = runner.invoke(app, ["market", "search", "nonexistent"])
        assert result.exit_code == 0
        assert "No skills found" in result.output

    @patch("vibesop.cli.commands.market_cmd.GitHubSkillCrawler")
    def test_search_pagination(self, mock_crawler_cls: Any) -> None:
        mock_crawler = MagicMock()
        mock_crawler.search.return_value = []
        mock_crawler_cls.return_value = mock_crawler

        result = runner.invoke(app, ["market", "search", "test", "--page", "2"])
        assert result.exit_code == 0
        mock_crawler.search.assert_called_once_with("test", page=2)


class TestMarketInstall:
    """Tests for vibe market install."""

    @patch("vibesop.cli.commands.market_cmd.GitHubSkillCrawler")
    def test_install_valid_repo(self, mock_crawler_cls: Any) -> None:
        mock_crawler = MagicMock()
        mock_crawler.validate.return_value = True
        mock_crawler_cls.return_value = mock_crawler

        result = runner.invoke(app, ["market", "install", "user/repo"])
        assert result.exit_code == 0
        assert "valid" in result.output
        assert "vibe install https://github.com/user/repo" in result.output

    @patch("vibesop.cli.commands.market_cmd.GitHubSkillCrawler")
    def test_install_invalid_repo_format(self, mock_crawler_cls: Any) -> None:
        result = runner.invoke(app, ["market", "install", "invalid-repo"])
        assert result.exit_code == 1
        assert "user/repo" in result.output

    @patch("vibesop.cli.commands.market_cmd.GitHubSkillCrawler")
    def test_install_no_skill_md(self, mock_crawler_cls: Any) -> None:
        mock_crawler = MagicMock()
        mock_crawler.validate.return_value = False
        mock_crawler_cls.return_value = mock_crawler

        result = runner.invoke(app, ["market", "install", "user/repo"])
        assert result.exit_code == 1
        assert "SKILL.md" in result.output


class TestMarketHelp:
    """Tests for vibe market --help."""

    def test_market_help(self) -> None:
        result = runner.invoke(app, ["market", "--help"])
        assert result.exit_code == 0
        assert "search" in result.output
        assert "install" in result.output
