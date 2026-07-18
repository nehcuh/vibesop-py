"""Tests for the awesome-list channel."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest

from vibesop.market import cache
from vibesop.market.awesome_list import (
    DEFAULT_LIST_URLS,
    fetch_awesome_lists,
    parse_awesome_markdown,
)

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


@pytest.fixture(autouse=True)
def _tmp_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the market search cache at a temp dir so tests stay isolated."""
    monkeypatch.setattr(cache, "CACHE_FILE", tmp_path / "market_search.json")


SAMPLE_MARKDOWN = """# Awesome Agent Skills

- [Code Review Pro](https://github.com/alice/code-review-pro) — reviews code
- [alice/code-review-pro](https://github.com/alice/code-review-pro) — duplicate link
- [Debugger](https://github.com/bob/debugger.git) — git suffix
- [Meta](https://github.com/addyosmani/agent-skills) — the list itself
- [Official](https://github.com/anthropics/skills) — official collection
- [Deep link](https://github.com/carol/tools/tree/main/skills) — subpath ignored
"""


class TestParseAwesomeMarkdown:
    def test_parses_repo_links(self) -> None:
        repos = parse_awesome_markdown(SAMPLE_MARKDOWN)
        full_names = {r.full_name for r in repos}
        assert "alice/code-review-pro" in full_names
        assert "anthropics/skills" in full_names
        assert "carol/tools" in full_names

    def test_deduplicates_repos(self) -> None:
        repos = parse_awesome_markdown(SAMPLE_MARKDOWN)
        assert len([r for r in repos if r.full_name == "alice/code-review-pro"]) == 1

    def test_strips_git_suffix(self) -> None:
        repos = parse_awesome_markdown(SAMPLE_MARKDOWN)
        assert "bob/debugger" in {r.full_name for r in repos}

    def test_excludes_meta_repos(self) -> None:
        repos = parse_awesome_markdown(SAMPLE_MARKDOWN)
        assert "addyosmani/agent-skills" not in {r.full_name for r in repos}

    def test_tier_and_channel(self) -> None:
        repos = parse_awesome_markdown(SAMPLE_MARKDOWN)
        for repo in repos:
            assert repo.tier == "curated"
            assert repo.source_channel == "awesome-list"
            assert repo.stars == 0

    def test_empty_markdown_yields_nothing(self) -> None:
        assert parse_awesome_markdown("# No links here") == []

    def test_ignores_image_links(self) -> None:
        markdown = (
            "![logo](https://github.com/dave/logo-repo)\n"
            "![CI](https://github.com/carol/tools/workflows/CI/badge.svg)\n"
            "- [Real](https://github.com/eve/real-skill) — a real skill\n"
        )
        repos = parse_awesome_markdown(markdown)
        assert {r.full_name for r in repos} == {"eve/real-skill"}


class TestFetchAwesomeLists:
    def test_fetch_success(self, mocker: MockerFixture) -> None:
        response = mocker.Mock()
        response.status_code = 200
        response.text = SAMPLE_MARKDOWN
        mock_get = mocker.patch("httpx.get", return_value=response)

        repos = fetch_awesome_lists(urls=("https://example.com/list.md",))

        assert mock_get.call_count == 1
        assert any(r.full_name == "alice/code-review-pro" for r in repos)

    def test_fetch_404_skipped(self, mocker: MockerFixture) -> None:
        response = mocker.Mock()
        response.status_code = 404
        mocker.patch("httpx.get", return_value=response)

        assert fetch_awesome_lists(urls=("https://example.com/missing.md",)) == []

    def test_fetch_timeout_tolerated(self, mocker: MockerFixture) -> None:
        mocker.patch("httpx.get", side_effect=httpx.TimeoutException("slow"))

        assert fetch_awesome_lists(urls=("https://example.com/slow.md",)) == []

    def test_fetch_merges_and_dedupes_across_lists(self, mocker: MockerFixture) -> None:
        resp_a = mocker.Mock()
        resp_a.status_code = 200
        resp_a.text = "- [A](https://github.com/alice/shared-skill)\n"
        resp_b = mocker.Mock()
        resp_b.status_code = 200
        resp_b.text = (
            "- [A](https://github.com/alice/shared-skill)\n"
            "- [B](https://github.com/bob/other-skill)\n"
        )
        mocker.patch("httpx.get", side_effect=[resp_a, resp_b])

        repos = fetch_awesome_lists(urls=("https://example.com/a.md", "https://example.com/b.md"))

        assert {r.full_name for r in repos} == {"alice/shared-skill", "bob/other-skill"}

    def test_fetch_uses_cache_on_second_call(self, mocker: MockerFixture) -> None:
        response = mocker.Mock()
        response.status_code = 200
        response.text = SAMPLE_MARKDOWN
        mock_get = mocker.patch("httpx.get", return_value=response)

        url = "https://example.com/list.md"
        first = fetch_awesome_lists(urls=(url,))
        second = fetch_awesome_lists(urls=(url,))

        assert mock_get.call_count == 1
        assert {r.full_name for r in first} == {r.full_name for r in second}

    def test_default_urls_cover_expected_lists(self) -> None:
        assert any("addyosmani/agent-skills" in url for url in DEFAULT_LIST_URLS)
