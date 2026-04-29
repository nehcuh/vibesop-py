"""Tests for SkillPublisher."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from vibesop.market.publisher import (
    DEFAULT_REGISTRY_REPO,
    PUBLISH_LABEL,
    SkillListing,
    SkillPublisher,
)

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


@pytest.fixture
def publisher() -> SkillPublisher:
    return SkillPublisher(token="ghp_test")


class TestInit:
    def test_init_with_token(self) -> None:
        pub = SkillPublisher(token="ghp_test")
        assert pub.token == "ghp_test"
        assert pub.headers["Authorization"] == "Bearer ghp_test"

    def test_init_without_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.delenv("GH_TOKEN", raising=False)
        pub = SkillPublisher()
        assert pub.token is None
        assert "Authorization" not in pub.headers

    def test_init_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GITHUB_TOKEN", "env_token")
        pub = SkillPublisher()
        assert pub.token == "env_token"

    def test_default_registry_repo(self) -> None:
        pub = SkillPublisher(token="t")
        assert pub.registry_repo == DEFAULT_REGISTRY_REPO

    def test_custom_registry_repo(self) -> None:
        pub = SkillPublisher(token="t", registry_repo="custom/repo")
        assert pub.registry_repo == "custom/repo"


class TestPublish:
    def test_publish_dry_run(self, publisher: SkillPublisher) -> None:
        result = publisher.publish(
            repo_name="owner/repo",
            description="Test skill",
            tags=["debug", "test"],
            dry_run=True,
        )

        assert result["dry_run"] is True
        assert result["repo_name"] == "owner/repo"
        assert result["payload"]["title"] == f"[{PUBLISH_LABEL}] owner/repo"
        assert "Test skill" in result["payload"]["body"]
        assert PUBLISH_LABEL in result["payload"]["labels"]

    def test_publish_invalid_repo_name(self, publisher: SkillPublisher) -> None:
        result = publisher.publish(repo_name="invalid")
        assert "error" in result

    def test_publish_no_token(self) -> None:
        pub = SkillPublisher(token=None)
        result = pub.publish(repo_name="owner/repo", description="Test")
        assert "error" in result
        assert "GITHUB_TOKEN" in result["error"]

    def test_publish_success(self, mocker: MockerFixture, publisher: SkillPublisher) -> None:
        mock_response = mocker.Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "html_url": "https://github.com/nehcuh/vibesop-py/issues/42",
            "number": 42,
        }
        mock_client = mocker.patch("httpx.Client")
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response

        result = publisher.publish(repo_name="owner/repo", description="Test skill")

        assert result["issue_url"] == "https://github.com/nehcuh/vibesop-py/issues/42"
        assert result["issue_number"] == 42
        assert result["repo_name"] == "owner/repo"

    def test_publish_api_error(self, mocker: MockerFixture, publisher: SkillPublisher) -> None:
        mock_response = mocker.Mock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"
        mock_client = mocker.patch("httpx.Client")
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response

        result = publisher.publish(repo_name="owner/repo", description="Test")

        assert "error" in result
        assert "403" in result["error"]

    def test_publish_request_error(self, mocker: MockerFixture, publisher: SkillPublisher) -> None:
        import httpx

        mock_client = mocker.patch("httpx.Client")
        mock_client.return_value.__enter__.return_value.post.side_effect = httpx.RequestError("Network error")

        result = publisher.publish(repo_name="owner/repo", description="Test")

        assert "error" in result
        assert "Network error" in result["error"]

    def test_publish_auto_detect_description(self, mocker: MockerFixture, publisher: SkillPublisher) -> None:
        # Mock _detect_from_skill_md
        mocker.patch.object(
            publisher,
            "_detect_from_skill_md",
            return_value={"description": "Auto-detected", "tags": ["auto"]},
        )

        result = publisher.publish(repo_name="owner/repo", dry_run=True)

        assert result["dry_run"] is True
        assert "Auto-detected" in result["payload"]["body"]
        assert "auto" in result["payload"]["body"]


class TestSearchIssues:
    def test_search_success(self, mocker: MockerFixture, publisher: SkillPublisher) -> None:
        mock_response = mocker.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "total_count": 1,
            "items": [
                {
                    "title": f"[{PUBLISH_LABEL}] owner/skill-git",
                    "body": "## Git skill\n\n- **Repository**: [owner/skill-git](https://github.com/owner/skill-git)\n- **Install**: `vibe market install owner/skill-git`\n- **Tags**: git, vcs\n- **Homepage**: https://example.com\n",
                    "html_url": "https://github.com/nehcuh/vibesop-py/issues/1",
                    "number": 1,
                },
            ],
        }
        mock_client = mocker.patch("httpx.Client")
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response

        results = publisher.search_issues("git")

        assert len(results) == 1
        assert results[0].repo_name == "owner/skill-git"
        assert results[0].description == "Git skill"
        assert results[0].tags == ["git", "vcs"]
        assert results[0].homepage == "https://example.com"
        assert results[0].issue_number == 1

    def test_search_empty_results(self, mocker: MockerFixture, publisher: SkillPublisher) -> None:
        mock_response = mocker.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"total_count": 0, "items": []}
        mock_client = mocker.patch("httpx.Client")
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response

        results = publisher.search_issues()
        assert results == []

    def test_search_http_error(self, mocker: MockerFixture, publisher: SkillPublisher) -> None:
        mock_response = mocker.Mock()
        mock_response.status_code = 403
        mock_client = mocker.patch("httpx.Client")
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response

        results = publisher.search_issues()
        assert results == []

    def test_search_skips_invalid_titles(self, mocker: MockerFixture, publisher: SkillPublisher) -> None:
        mock_response = mocker.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "total_count": 2,
            "items": [
                {
                    "title": "[other-label] owner/skill-a",
                    "body": "",
                    "html_url": "",
                    "number": 1,
                },
                {
                    "title": f"[{PUBLISH_LABEL}] owner/skill-b",
                    "body": "## Valid skill",
                    "html_url": "https://github.com/issue/2",
                    "number": 2,
                },
            ],
        }
        mock_client = mocker.patch("httpx.Client")
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response

        results = publisher.search_issues()

        assert len(results) == 1
        assert results[0].repo_name == "owner/skill-b"


class TestParseFrontmatter:
    def test_valid_frontmatter(self, publisher: SkillPublisher) -> None:
        content = "---\ndescription: A test skill\ntags:\n  - test\n  - debug\n---\n# Skill\n"
        result = publisher._parse_frontmatter(content)
        assert result["description"] == "A test skill"
        assert result["tags"] == ["test", "debug"]

    def test_no_frontmatter(self, publisher: SkillPublisher) -> None:
        content = "# Skill\nNo frontmatter here.\n"
        result = publisher._parse_frontmatter(content)
        assert result == {}

    def test_invalid_yaml(self, publisher: SkillPublisher) -> None:
        content = "---\ninvalid: yaml: [\n---\n# Skill\n"
        result = publisher._parse_frontmatter(content)
        assert result == {}

    def test_incomplete_frontmatter(self, publisher: SkillPublisher) -> None:
        content = "---\nonly one separator\n"
        result = publisher._parse_frontmatter(content)
        assert result == {}


class TestParseIssueBody:
    def test_full_body(self, publisher: SkillPublisher) -> None:
        body = "## My Skill\n\n- **Repository**: [owner/repo](...)\n- **Tags**: test, debug\n- **Homepage**: https://example.com\n"
        desc, tags, homepage = publisher._parse_issue_body(body)
        assert desc == "My Skill"
        assert tags == ["test", "debug"]
        assert homepage == "https://example.com"

    def test_minimal_body(self, publisher: SkillPublisher) -> None:
        body = "## Simple Skill\n"
        desc, tags, homepage = publisher._parse_issue_body(body)
        assert desc == "Simple Skill"
        assert tags == []
        assert homepage == ""

    def test_empty_body(self, publisher: SkillPublisher) -> None:
        desc, tags, homepage = publisher._parse_issue_body("")
        assert desc == ""
        assert tags == []
        assert homepage == ""


class TestSkillListing:
    def test_install_source(self) -> None:
        listing = SkillListing(repo_name="owner/repo", description="Test")
        assert listing.install_source == "https://github.com/owner/repo"
