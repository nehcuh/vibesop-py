"""Tests for vibe market subcommands."""

from typing import Any
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from vibesop.cli.main import app
from vibesop.market.crawler import SkillRepo

runner = CliRunner()


def _repo(
    full_name: str,
    stars: int = 0,
    tier: str = "unknown",
    channel: str = "github",
) -> SkillRepo:
    return SkillRepo(
        name=full_name.rsplit("/", 1)[-1],
        full_name=full_name,
        description="desc",
        stars=stars,
        topics=[],
        html_url=f"https://github.com/{full_name}",
        tier=tier,
        source_channel=channel,
    )


class TestMarketSearch:
    """Tests for vibe market search."""

    @patch("vibesop.cli.commands.market_cmd.fetch_awesome_lists", return_value=[])
    @patch("vibesop.cli.commands.market_cmd.GitHubSkillCrawler")
    def test_search_basic(self, mock_crawler_cls: Any, mock_awesome: Any) -> None:
        mock_crawler = MagicMock()
        mock_crawler.search.return_value = [_repo("user/skill-a", stars=42)]
        mock_crawler_cls.return_value = mock_crawler

        result = runner.invoke(app, ["market", "search", "skill-a"])
        assert result.exit_code == 0
        assert "skill-a" in result.output
        assert "desc" in result.output
        assert "42" in result.output
        assert "未知" in result.output

    @patch("vibesop.cli.commands.market_cmd.fetch_awesome_lists", return_value=[])
    @patch("vibesop.cli.commands.market_cmd.GitHubSkillCrawler")
    def test_search_json(self, mock_crawler_cls: Any, mock_awesome: Any) -> None:
        mock_crawler = MagicMock()
        mock_crawler.search.return_value = [_repo("user/skill-a", stars=42)]
        mock_crawler_cls.return_value = mock_crawler

        result = runner.invoke(app, ["market", "search", "skill-a", "--json"])
        assert result.exit_code == 0
        assert '"full_name": "user/skill-a"' in result.output
        assert '"tier": "unknown"' in result.output
        assert '"source": "github"' in result.output
        assert '"stars": 42' in result.output

    @patch("vibesop.cli.commands.market_cmd.fetch_awesome_lists", return_value=[])
    @patch("vibesop.cli.commands.market_cmd.GitHubSkillCrawler")
    def test_search_no_results(self, mock_crawler_cls: Any, mock_awesome: Any) -> None:
        mock_crawler = MagicMock()
        mock_crawler.search.return_value = []
        mock_crawler_cls.return_value = mock_crawler

        result = runner.invoke(app, ["market", "search", "nonexistent"])
        assert result.exit_code == 0
        assert "No skills found" in result.output

    @patch("vibesop.cli.commands.market_cmd.fetch_awesome_lists", return_value=[])
    @patch("vibesop.cli.commands.market_cmd.GitHubSkillCrawler")
    def test_search_pagination(self, mock_crawler_cls: Any, mock_awesome: Any) -> None:
        mock_crawler = MagicMock()
        mock_crawler.search.return_value = []
        mock_crawler_cls.return_value = mock_crawler

        result = runner.invoke(app, ["market", "search", "test", "--page", "2"])
        assert result.exit_code == 0
        mock_crawler.search.assert_called_once_with("test", page=2)

    @patch("vibesop.cli.commands.market_cmd.fetch_awesome_lists")
    @patch("vibesop.cli.commands.market_cmd.GitHubSkillCrawler")
    def test_search_merges_curated_and_sorts_tier_first(
        self, mock_crawler_cls: Any, mock_awesome: Any
    ) -> None:
        mock_crawler = MagicMock()
        mock_crawler.search.return_value = [_repo("user/popular", stars=9999)]
        mock_crawler_cls.return_value = mock_crawler
        mock_awesome.return_value = [
            _repo("alice/popular", stars=0, tier="curated", channel="awesome-list"),
        ]

        result = runner.invoke(app, ["market", "search", "popular"])
        assert result.exit_code == 0
        # Curated entry ranks above the higher-starred unknown entry.
        assert result.output.index("alice/popular") < result.output.index("user/popular")
        assert "curated" in result.output

    @patch("vibesop.cli.commands.market_cmd.fetch_awesome_lists", return_value=[])
    @patch("vibesop.cli.commands.market_cmd.GitHubSkillCrawler")
    def test_search_dedupes_github_and_awesome(
        self, mock_crawler_cls: Any, mock_awesome: Any
    ) -> None:
        mock_crawler = MagicMock()
        mock_crawler.search.return_value = [_repo("user/skill-a", stars=42)]
        mock_crawler_cls.return_value = mock_crawler
        mock_awesome.return_value = [
            _repo("user/skill-a", stars=0, tier="curated", channel="awesome-list"),
        ]

        result = runner.invoke(app, ["market", "search", "skill-a", "--json"])
        assert result.exit_code == 0
        assert result.output.count('"full_name": "user/skill-a"') == 1
        # GitHub entry wins but inherits the curated tier.
        assert '"tier": "curated"' in result.output
        assert '"stars": 42' in result.output

    @patch("vibesop.cli.commands.market_cmd.fetch_awesome_lists", return_value=[])
    @patch("vibesop.cli.commands.market_cmd.GitHubSkillCrawler")
    def test_search_trusted_pack_marked_official(
        self, mock_crawler_cls: Any, mock_awesome: Any
    ) -> None:
        mock_crawler = MagicMock()
        mock_crawler.search.return_value = [_repo("obra/superpowers", stars=1000)]
        mock_crawler_cls.return_value = mock_crawler

        result = runner.invoke(app, ["market", "search", "superpowers"])
        assert result.exit_code == 0
        assert "官方" in result.output

    @patch("vibesop.cli.commands.market_cmd.fetch_awesome_lists")
    @patch("vibesop.cli.commands.market_cmd.GitHubSkillCrawler")
    def test_search_no_experimental_warning(self, mock_crawler_cls: Any, mock_awesome: Any) -> None:
        mock_crawler = MagicMock()
        mock_crawler.search.return_value = []
        mock_crawler_cls.return_value = mock_crawler
        mock_awesome.return_value = []

        result = runner.invoke(app, ["market", "search", "test"])
        assert result.exit_code == 0
        assert "experimental" not in result.output


class TestMarketInstall:
    """Tests for vibe market install."""

    @patch("vibesop.installer.pack_installer.PackInstaller")
    @patch("vibesop.cli.commands.market_cmd.GitHubSkillCrawler")
    def test_install_valid_repo(self, mock_crawler_cls: Any, mock_installer_cls: Any) -> None:
        mock_crawler = MagicMock()
        mock_crawler.validate.return_value = True
        mock_crawler_cls.return_value = mock_crawler

        mock_installer = MagicMock()
        mock_installer.install_pack.return_value = (True, "Installed")
        mock_installer_cls.return_value = mock_installer

        result = runner.invoke(app, ["market", "install", "user/repo", "--yes"])
        assert result.exit_code == 0
        assert "valid" in result.output
        assert "Successfully installed" in result.output

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

    @patch("vibesop.installer.pack_installer.PackInstaller")
    @patch("vibesop.cli.commands.market_cmd.GitHubSkillCrawler")
    def test_install_default_scope_is_global(
        self, mock_crawler_cls: Any, mock_installer_cls: Any
    ) -> None:
        mock_crawler = MagicMock()
        mock_crawler.validate.return_value = True
        mock_crawler_cls.return_value = mock_crawler

        mock_installer = MagicMock()
        mock_installer.install_pack.return_value = (True, "Installed")
        mock_installer_cls.return_value = mock_installer

        result = runner.invoke(app, ["market", "install", "user/repo", "--yes"])
        assert result.exit_code == 0
        mock_installer.install_pack.assert_called_once_with(
            "repo", "https://github.com/user/repo", scope="global"
        )

    @patch("vibesop.installer.pack_installer.PackInstaller")
    @patch("vibesop.cli.commands.market_cmd.GitHubSkillCrawler")
    def test_install_project_scope(self, mock_crawler_cls: Any, mock_installer_cls: Any) -> None:
        """--scope project is threaded through to PackInstaller.install_pack."""
        mock_crawler = MagicMock()
        mock_crawler.validate.return_value = True
        mock_crawler_cls.return_value = mock_crawler

        mock_installer = MagicMock()
        mock_installer.install_pack.return_value = (True, "Installed")
        mock_installer_cls.return_value = mock_installer

        result = runner.invoke(
            app, ["market", "install", "user/repo", "--yes", "--scope", "project"]
        )
        assert result.exit_code == 0
        assert "Successfully installed" in result.output
        assert "experimental" not in result.output
        mock_installer.install_pack.assert_called_once_with(
            "repo", "https://github.com/user/repo", scope="project"
        )

    def test_install_invalid_scope(self) -> None:
        result = runner.invoke(app, ["market", "install", "user/repo", "--scope", "bogus"])
        assert result.exit_code == 1
        assert "--scope must be 'global' or 'project'" in result.output

    @patch("vibesop.installer.pack_installer.PackInstaller")
    @patch("vibesop.cli.commands.market_cmd.fetch_awesome_lists")
    @patch("vibesop.cli.commands.market_cmd.GitHubSkillCrawler")
    def test_install_unknown_repo_shows_tier_panel(
        self, mock_crawler_cls: Any, mock_awesome: Any, mock_installer_cls: Any
    ) -> None:
        """Interactive install of an unknown repo shows tier/stars/description."""
        mock_crawler = MagicMock()
        mock_crawler.validate.return_value = True
        mock_crawler_cls.return_value = mock_crawler
        mock_awesome.return_value = []

        mock_installer = MagicMock()
        mock_installer.install_pack.return_value = (True, "Installed")
        mock_installer_cls.return_value = mock_installer

        with patch("questionary.confirm") as mock_confirm:
            mock_confirm.return_value.ask.return_value = True
            result = runner.invoke(app, ["market", "install", "user/repo"])

        assert result.exit_code == 0
        assert "未知来源 - 未经验证" in result.output
        assert "Stars:" in result.output
        assert "Description:" in result.output

    @patch("vibesop.installer.pack_installer.PackInstaller")
    @patch("vibesop.cli.commands.market_cmd.fetch_awesome_lists")
    @patch("vibesop.cli.commands.market_cmd.GitHubSkillCrawler")
    def test_install_curated_repo_shows_curated_badge(
        self, mock_crawler_cls: Any, mock_awesome: Any, mock_installer_cls: Any
    ) -> None:
        """Interactive install of a curated repo is labeled [curated]."""
        mock_crawler = MagicMock()
        mock_crawler.validate.return_value = True
        mock_crawler_cls.return_value = mock_crawler
        mock_awesome.return_value = [
            _repo("user/repo", stars=123, tier="curated", channel="awesome-list"),
        ]

        mock_installer = MagicMock()
        mock_installer.install_pack.return_value = (True, "Installed")
        mock_installer_cls.return_value = mock_installer

        with patch("questionary.confirm") as mock_confirm:
            mock_confirm.return_value.ask.return_value = True
            result = runner.invoke(app, ["market", "install", "user/repo"])

        assert result.exit_code == 0
        assert "[curated]" in result.output
        assert "123" in result.output
        assert "desc" in result.output
        assert "未知来源" not in result.output

    @patch("vibesop.installer.pack_installer.PackInstaller")
    @patch("vibesop.cli.commands.market_cmd.fetch_awesome_lists")
    @patch("vibesop.cli.commands.market_cmd.GitHubSkillCrawler")
    def test_install_official_repo_keeps_plain_confirm(
        self, mock_crawler_cls: Any, mock_awesome: Any, mock_installer_cls: Any
    ) -> None:
        """Official packs keep the existing confirmation without a tier panel."""
        mock_crawler = MagicMock()
        mock_crawler.validate.return_value = True
        mock_crawler_cls.return_value = mock_crawler

        mock_installer = MagicMock()
        mock_installer.install_pack.return_value = (True, "Installed")
        mock_installer_cls.return_value = mock_installer

        with patch("questionary.confirm") as mock_confirm:
            mock_confirm.return_value.ask.return_value = True
            result = runner.invoke(app, ["market", "install", "obra/superpowers"])

        assert result.exit_code == 0
        assert "Tier:" not in result.output
        assert "未知来源" not in result.output
        # Official short-circuits before the awesome-list lookup.
        mock_awesome.assert_not_called()


class TestMarketTrending:
    """Tests for vibe market trending."""

    @patch("vibesop.cli.commands.market_cmd.GitHubSkillCrawler")
    def test_trending_maps_category_to_topic(self, mock_crawler_cls: Any) -> None:
        mock_crawler = MagicMock()
        mock_crawler.search.return_value = [_repo("user/hot", stars=500)]
        mock_crawler_cls.return_value = mock_crawler

        result = runner.invoke(app, ["market", "trending", "agent"])
        assert result.exit_code == 0
        mock_crawler_cls.assert_called_once_with(topics=("agent-skills",))
        mock_crawler.search.assert_called_once_with("")
        assert "hot" in result.output
        assert "500" in result.output
        assert "agent-skills" in result.output

    @patch("vibesop.cli.commands.market_cmd.GitHubSkillCrawler")
    def test_trending_unknown_category_used_as_topic(self, mock_crawler_cls: Any) -> None:
        mock_crawler = MagicMock()
        mock_crawler.search.return_value = []
        mock_crawler_cls.return_value = mock_crawler

        result = runner.invoke(app, ["market", "trending", "rust-skills"])
        assert result.exit_code == 0
        mock_crawler_cls.assert_called_once_with(topics=("rust-skills",))
        assert "using it as a GitHub topic directly" in result.output
        assert "No skills found" in result.output

    @patch("vibesop.cli.commands.market_cmd.GitHubSkillCrawler")
    def test_trending_json(self, mock_crawler_cls: Any) -> None:
        mock_crawler = MagicMock()
        mock_crawler.search.return_value = [_repo("user/hot", stars=500)]
        mock_crawler_cls.return_value = mock_crawler

        result = runner.invoke(app, ["market", "trending", "claude", "--json"])
        assert result.exit_code == 0
        mock_crawler_cls.assert_called_once_with(topics=("claude-skills",))
        assert '"full_name": "user/hot"' in result.output
        assert '"stars": 500' in result.output


class TestMarketHelp:
    """Tests for vibe market --help."""

    def test_market_help(self) -> None:
        result = runner.invoke(app, ["market", "--help"])
        assert result.exit_code == 0
        assert "search" in result.output
        assert "install" in result.output

    def test_publish_removed(self) -> None:
        result = runner.invoke(app, ["market", "publish", "user/repo"])
        assert result.exit_code != 0
