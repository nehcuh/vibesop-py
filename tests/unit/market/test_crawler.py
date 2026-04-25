"""Tests for GitHubSkillCrawler."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from vibesop.market.crawler import GitHubSkillCrawler, SkillRepo

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


@pytest.fixture
def crawler() -> GitHubSkillCrawler:
    return GitHubSkillCrawler(token=None)


class TestInit:
    def test_init_without_token(self) -> None:
        crawler = GitHubSkillCrawler(token=None)
        assert crawler.token is None
        assert "Authorization" not in crawler.headers

    def test_init_with_token(self) -> None:
        crawler = GitHubSkillCrawler(token="ghp_test")
        assert crawler.token == "ghp_test"
        assert crawler.headers["Authorization"] == "Bearer ghp_test"


class TestSearch:
    def test_search_returns_skill_repos(self, mocker: MockerFixture, crawler: GitHubSkillCrawler) -> None:
        mock_response = mocker.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "total_count": 2,
            "items": [
                {
                    "name": "skill-git",
                    "full_name": "user/skill-git",
                    "description": "Git skill",
                    "stargazers_count": 42,
                    "topics": ["vibesop-skill", "git"],
                    "html_url": "https://github.com/user/skill-git",
                },
                {
                    "name": "skill-docker",
                    "full_name": "user/skill-docker",
                    "description": None,
                    "stargazers_count": 10,
                    "topics": ["vibesop-skill", "docker"],
                    "html_url": "https://github.com/user/skill-docker",
                },
            ],
        }
        mock_client = mocker.patch("httpx.Client")
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response

        results = crawler.search("git")

        assert len(results) == 2
        assert results[0].name == "skill-git"
        assert results[0].full_name == "user/skill-git"
        assert results[0].description == "Git skill"
        assert results[0].stars == 42
        assert results[0].topics == ["vibesop-skill", "git"]
        assert results[0].html_url == "https://github.com/user/skill-git"
        assert results[0].has_skill_md is False

        assert results[1].name == "skill-docker"
        assert results[1].description == ""
        assert results[1].stars == 10

    def test_search_empty_results(self, mocker: MockerFixture, crawler: GitHubSkillCrawler) -> None:
        mock_response = mocker.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"total_count": 0, "items": []}
        mock_client = mocker.patch("httpx.Client")
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response

        results = crawler.search("nonexistent")

        assert results == []

    def test_search_http_error_returns_empty(self, mocker: MockerFixture, crawler: GitHubSkillCrawler) -> None:
        mock_response = mocker.Mock()
        mock_response.status_code = 403
        mock_client = mocker.patch("httpx.Client")
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response

        results = crawler.search("git")

        assert results == []

    def test_search_pagination(self, mocker: MockerFixture, crawler: GitHubSkillCrawler) -> None:
        mock_response = mocker.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "total_count": 1,
            "items": [
                {
                    "name": "skill-git",
                    "full_name": "user/skill-git",
                    "description": "Git skill",
                    "stargazers_count": 42,
                    "topics": ["vibesop-skill"],
                    "html_url": "https://github.com/user/skill-git",
                },
            ],
        }
        mock_client = mocker.patch("httpx.Client")
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response

        results = crawler.search("git", page=2)

        assert len(results) == 1
        call_args = mock_client.return_value.__enter__.return_value.get.call_args
        assert call_args.kwargs["params"]["page"] == 2


class TestValidate:
    def test_validate_skill_md_exists(self, mocker: MockerFixture, crawler: GitHubSkillCrawler) -> None:
        mock_response = mocker.Mock()
        mock_response.status_code = 200
        mock_client = mocker.patch("httpx.Client")
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response

        repo = SkillRepo(
            name="skill-git",
            full_name="user/skill-git",
            description="Git skill",
            stars=42,
            topics=["vibesop-skill"],
            html_url="https://github.com/user/skill-git",
        )

        assert crawler.validate(repo) is True

    def test_validate_skill_md_missing(self, mocker: MockerFixture, crawler: GitHubSkillCrawler) -> None:
        mock_response = mocker.Mock()
        mock_response.status_code = 404
        mock_client = mocker.patch("httpx.Client")
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response

        repo = SkillRepo(
            name="skill-git",
            full_name="user/skill-git",
            description="Git skill",
            stars=42,
            topics=["vibesop-skill"],
            html_url="https://github.com/user/skill-git",
        )

        assert crawler.validate(repo) is False

    def test_validate_other_error(self, mocker: MockerFixture, crawler: GitHubSkillCrawler) -> None:
        mock_response = mocker.Mock()
        mock_response.status_code = 500
        mock_client = mocker.patch("httpx.Client")
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response

        repo = SkillRepo(
            name="skill-git",
            full_name="user/skill-git",
            description="Git skill",
            stars=42,
            topics=["vibesop-skill"],
            html_url="https://github.com/user/skill-git",
        )

        assert crawler.validate(repo) is False
