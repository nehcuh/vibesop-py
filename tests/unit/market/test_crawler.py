"""Tests for GitHubSkillCrawler."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from vibesop.market import cache
from vibesop.market.crawler import DEFAULT_TOPICS, GitHubSkillCrawler, SkillRepo

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


@pytest.fixture(autouse=True)
def _tmp_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the market search cache at a temp dir so tests stay isolated."""
    monkeypatch.setattr(cache, "CACHE_FILE", tmp_path / "market_search.json")


@pytest.fixture
def crawler() -> GitHubSkillCrawler:
    return GitHubSkillCrawler(token=None, topics=("agent-skills",))


def _repo_item(name: str, full_name: str, stars: int = 0) -> dict:
    return {
        "name": name,
        "full_name": full_name,
        "description": f"{name} description",
        "stargazers_count": stars,
        "topics": ["agent-skills"],
        "html_url": f"https://github.com/{full_name}",
    }


def _mock_response(mocker: MockerFixture, status: int, items: list[dict] | None = None) -> object:
    response = mocker.Mock()
    response.status_code = status
    response.json.return_value = {"total_count": len(items or []), "items": items or []}
    return response


def _patch_client(mocker: MockerFixture, responses: list[object]) -> object:
    mock_client = mocker.patch("httpx.Client")
    mock_client.return_value.__enter__.return_value.get.side_effect = responses
    return mock_client


class TestInit:
    def test_init_without_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.delenv("GH_TOKEN", raising=False)
        crawler = GitHubSkillCrawler(token=None)
        assert crawler.token is None
        assert "Authorization" not in crawler.headers

    def test_init_with_token(self) -> None:
        crawler = GitHubSkillCrawler(token="ghp_test")
        assert crawler.token == "ghp_test"
        assert crawler.headers["Authorization"] == "Bearer ghp_test"

    def test_init_token_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_env")
        crawler = GitHubSkillCrawler()
        assert crawler.token == "ghp_env"
        assert crawler.headers["Authorization"] == "Bearer ghp_env"

    def test_init_gh_token_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.setenv("GH_TOKEN", "ghp_gh")
        crawler = GitHubSkillCrawler()
        assert crawler.token == "ghp_gh"

    def test_default_topics(self) -> None:
        crawler = GitHubSkillCrawler(token=None)
        assert crawler.topics == DEFAULT_TOPICS
        assert "vibesop-skill" not in crawler.topics


class TestSearch:
    def test_search_returns_skill_repos(
        self, mocker: MockerFixture, crawler: GitHubSkillCrawler
    ) -> None:
        response = _mock_response(
            mocker,
            200,
            [
                _repo_item("skill-git", "user/skill-git", stars=42),
                _repo_item("skill-docker", "user/skill-docker", stars=10),
            ],
        )
        _patch_client(mocker, [response])

        results = crawler.search("git")

        assert len(results) == 2
        assert results[0].full_name == "user/skill-git"
        assert results[0].stars == 42
        assert results[0].tier == "unknown"
        assert results[0].source_channel == "github"

    def test_search_sorted_by_stars_desc(
        self, mocker: MockerFixture, crawler: GitHubSkillCrawler
    ) -> None:
        response = _mock_response(
            mocker,
            200,
            [
                _repo_item("low", "user/low", stars=1),
                _repo_item("high", "user/high", stars=999),
            ],
        )
        _patch_client(mocker, [response])

        results = crawler.search("git")

        assert [r.full_name for r in results] == ["user/high", "user/low"]

    def test_search_sends_sort_and_topic_params(
        self, mocker: MockerFixture, crawler: GitHubSkillCrawler
    ) -> None:
        response = _mock_response(mocker, 200, [])
        mock_client = _patch_client(mocker, [response])

        crawler.search("git", page=2)

        call_args = mock_client.return_value.__enter__.return_value.get.call_args
        params = call_args.kwargs["params"]
        assert params["q"] == "git topic:agent-skills"
        assert params["sort"] == "stars"
        assert params["page"] == 2
        assert params["per_page"] == 10

    def test_search_merges_topics_or_semantics(self, mocker: MockerFixture) -> None:
        crawler = GitHubSkillCrawler(token=None, topics=("agent-skills", "claude-skills"))
        resp_a = _mock_response(
            mocker,
            200,
            [_repo_item("a", "user/a", stars=5), _repo_item("shared", "user/shared", stars=3)],
        )
        resp_b = _mock_response(
            mocker,
            200,
            [_repo_item("b", "user/b", stars=7), _repo_item("shared", "user/shared", stars=3)],
        )
        mock_client = _patch_client(mocker, [resp_a, resp_b])

        results = crawler.search("git")

        assert mock_client.return_value.__enter__.return_value.get.call_count == 2
        assert {r.full_name for r in results} == {"user/a", "user/b", "user/shared"}

    def test_search_partial_topic_failure_tolerated(self, mocker: MockerFixture) -> None:
        crawler = GitHubSkillCrawler(token=None, topics=("agent-skills", "claude-skills"))
        resp_fail = _mock_response(mocker, 403)
        resp_ok = _mock_response(mocker, 200, [_repo_item("a", "user/a", stars=5)])
        _patch_client(mocker, [resp_fail, resp_ok])

        results = crawler.search("git")

        assert [r.full_name for r in results] == ["user/a"]

    def test_search_all_topics_fail_returns_empty(self, mocker: MockerFixture) -> None:
        crawler = GitHubSkillCrawler(token=None, topics=("agent-skills", "claude-skills"))
        _patch_client(mocker, [_mock_response(mocker, 403), _mock_response(mocker, 500)])

        assert crawler.search("git") == []

    def test_search_uses_cache_on_second_call(
        self, mocker: MockerFixture, crawler: GitHubSkillCrawler
    ) -> None:
        response = _mock_response(mocker, 200, [_repo_item("a", "user/a", stars=5)])
        mock_client = _patch_client(mocker, [response])

        first = crawler.search("git")
        second = crawler.search("git")

        assert mock_client.return_value.__enter__.return_value.get.call_count == 1
        assert [r.full_name for r in first] == [r.full_name for r in second]
        assert second[0].stars == 5

    def test_search_cache_miss_when_expired(
        self,
        mocker: MockerFixture,
        crawler: GitHubSkillCrawler,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        response = _mock_response(mocker, 200, [_repo_item("a", "user/a", stars=5)])
        mock_client = _patch_client(mocker, [response, response])

        crawler.search("git")
        # Age the cache entry beyond the TTL.
        data = json.loads(cache.CACHE_FILE.read_text(encoding="utf-8"))
        for entry in data.values():
            entry["timestamp"] = 0
        cache.CACHE_FILE.write_text(json.dumps(data), encoding="utf-8")

        crawler.search("git")

        assert mock_client.return_value.__enter__.return_value.get.call_count == 2

    def test_search_corrupt_cache_treated_as_miss(
        self, mocker: MockerFixture, crawler: GitHubSkillCrawler
    ) -> None:
        cache.CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        cache.CACHE_FILE.write_text("{not json", encoding="utf-8")
        response = _mock_response(mocker, 200, [_repo_item("a", "user/a", stars=5)])
        _patch_client(mocker, [response])

        results = crawler.search("git")

        assert [r.full_name for r in results] == ["user/a"]

    def test_search_failure_not_cached(self, mocker: MockerFixture) -> None:
        crawler = GitHubSkillCrawler(token=None, topics=("agent-skills",))
        _patch_client(mocker, [_mock_response(mocker, 403)])

        crawler.search("git")

        assert not cache.CACHE_FILE.exists()

    def test_search_cache_key_includes_topics(self, mocker: MockerFixture) -> None:
        crawler_a = GitHubSkillCrawler(token=None, topics=("agent-skills",))
        crawler_b = GitHubSkillCrawler(token=None, topics=("claude-skills",))
        mock_client = _patch_client(
            mocker,
            [
                _mock_response(mocker, 200, [_repo_item("a", "user/a", stars=5)]),
                _mock_response(mocker, 200, [_repo_item("b", "user/b", stars=7)]),
            ],
        )

        crawler_a.search("git")
        crawler_b.search("git")

        # Different topic sets must not share a cache entry.
        assert mock_client.return_value.__enter__.return_value.get.call_count == 2
        keys = json.loads(cache.CACHE_FILE.read_text(encoding="utf-8"))
        assert any("topics:agent-skills" in key for key in keys)
        assert any("topics:claude-skills" in key for key in keys)

    def test_search_partial_failure_uses_short_ttl(self, mocker: MockerFixture) -> None:
        crawler = GitHubSkillCrawler(token=None, topics=("agent-skills", "claude-skills"))
        mock_client = _patch_client(
            mocker,
            [
                _mock_response(mocker, 403),
                _mock_response(mocker, 200, [_repo_item("a", "user/a", stars=5)]),
                # Second round after the short TTL expires.
                _mock_response(mocker, 200, [_repo_item("a", "user/a", stars=5)]),
                _mock_response(mocker, 200, [_repo_item("c", "user/c", stars=9)]),
            ],
        )

        crawler.search("git")

        data = json.loads(cache.CACHE_FILE.read_text(encoding="utf-8"))
        (entry,) = data.values()
        assert entry["ttl"] == cache.PARTIAL_CACHE_TTL_SECONDS

        # Age the entry past the short TTL but well below 24h.
        entry["timestamp"] -= cache.PARTIAL_CACHE_TTL_SECONDS + 1
        cache.CACHE_FILE.write_text(json.dumps(data), encoding="utf-8")

        results = crawler.search("git")

        # The failed topic is retried instead of being masked for 24h.
        assert mock_client.return_value.__enter__.return_value.get.call_count == 4
        assert {r.full_name for r in results} == {"user/a", "user/c"}

    def test_search_full_success_uses_long_ttl(
        self, mocker: MockerFixture, crawler: GitHubSkillCrawler
    ) -> None:
        response = _mock_response(mocker, 200, [_repo_item("a", "user/a", stars=5)])
        mock_client = _patch_client(mocker, [response])

        crawler.search("git")

        data = json.loads(cache.CACHE_FILE.read_text(encoding="utf-8"))
        (entry,) = data.values()
        assert entry["ttl"] == cache.CACHE_TTL_SECONDS

        # Age the entry past the short TTL but below 24h: still a cache hit.
        entry["timestamp"] -= cache.PARTIAL_CACHE_TTL_SECONDS + 1
        cache.CACHE_FILE.write_text(json.dumps(data), encoding="utf-8")

        results = crawler.search("git")

        assert mock_client.return_value.__enter__.return_value.get.call_count == 1
        assert [r.full_name for r in results] == ["user/a"]


class TestValidate:
    @staticmethod
    def _repo() -> SkillRepo:
        return SkillRepo(
            name="skill-git",
            full_name="user/skill-git",
            description="Git skill",
            stars=42,
            topics=["agent-skills"],
            html_url="https://github.com/user/skill-git",
        )

    @staticmethod
    def _tree_response(mocker: MockerFixture, status: int, payload: dict | None = None) -> object:
        response = mocker.Mock()
        response.status_code = status
        response.json.return_value = payload or {}
        return response

    def test_validate_skill_md_at_root(
        self, mocker: MockerFixture, crawler: GitHubSkillCrawler
    ) -> None:
        payload = {"tree": [{"type": "blob", "path": "SKILL.md"}]}
        _patch_client(mocker, [self._tree_response(mocker, 200, payload)])

        assert crawler.validate(self._repo()) is True

    def test_validate_skill_md_in_subdirectory(
        self, mocker: MockerFixture, crawler: GitHubSkillCrawler
    ) -> None:
        # Skill packs keep skills in per-skill subdirectories — must be accepted.
        payload = {
            "tree": [
                {"type": "blob", "path": "README.md"},
                {"type": "blob", "path": "skills/pdf/SKILL.md"},
            ]
        }
        _patch_client(mocker, [self._tree_response(mocker, 200, payload)])

        assert crawler.validate(self._repo()) is True

    def test_validate_skill_md_missing(
        self, mocker: MockerFixture, crawler: GitHubSkillCrawler
    ) -> None:
        payload = {"tree": [{"type": "blob", "path": "README.md"}]}
        _patch_client(mocker, [self._tree_response(mocker, 200, payload)])

        assert crawler.validate(self._repo()) is False

    def test_validate_request_failure(
        self, mocker: MockerFixture, crawler: GitHubSkillCrawler
    ) -> None:
        _patch_client(mocker, [self._tree_response(mocker, 404)])

        assert crawler.validate(self._repo()) is False

    def test_validate_rate_limit_raises_actionable_error(
        self, mocker: MockerFixture, crawler: GitHubSkillCrawler
    ) -> None:
        _patch_client(mocker, [self._tree_response(mocker, 403)])

        with pytest.raises(RuntimeError, match="GITHUB_TOKEN"):
            crawler.validate(self._repo())
