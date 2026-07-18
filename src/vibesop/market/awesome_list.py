"""Awesome-list channel — curated skill catalogs fetched without GitHub API calls.

Pulls one or more curated awesome lists from raw.githubusercontent.com and
parses GitHub repository links out of the markdown. Results carry
``tier="curated"`` and ``source_channel="awesome-list"``; stars are left at 0
(no API enrichment).
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict

import httpx

from vibesop.market.cache import get_cached, set_cached
from vibesop.market.crawler import SkillRepo

logger = logging.getLogger(__name__)

#: Curated awesome lists to fetch, in order. A list that fails to fetch or
#: yields no repo links is skipped silently (after logging a warning).
DEFAULT_LIST_URLS: tuple[str, ...] = (
    "https://raw.githubusercontent.com/addyosmani/agent-skills/main/README.md",
    "https://raw.githubusercontent.com/ComposioHQ/awesome-claude-skills/main/README.md",
)

#: Matches ``https://github.com/owner/repo`` links; trailing path segments,
#: anchors and query strings are ignored because ``/`` is outside the charset.
GITHUB_REPO_RE = re.compile(r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)")

#: Markdown image links (``![alt](url)``) — stripped before repo matching so
#: badge/logo URLs pointing at github.com are not mistaken for repo links.
_IMAGE_LINK_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")

FETCH_TIMEOUT_SECONDS = 15.0

#: Repos that host the lists themselves — meta content, not skills.
_META_REPOS: frozenset[str] = frozenset(
    {
        "addyosmani/agent-skills",
        "ComposioHQ/awesome-claude-skills",
    }
)


def fetch_awesome_lists(urls: tuple[str, ...] = DEFAULT_LIST_URLS) -> list[SkillRepo]:
    """Fetch curated awesome lists and parse GitHub repo links into SkillRepos.

    Fetch failures, timeouts, and non-200 responses degrade to an empty
    contribution (logged as a warning), never an exception.
    """
    repos: dict[str, SkillRepo] = {}
    for url in urls:
        for repo in _fetch_one(url):
            repos.setdefault(repo.full_name, repo)
    return list(repos.values())


def _fetch_one(url: str) -> list[SkillRepo]:
    """Fetch and parse a single awesome list, using the on-disk cache."""
    cache_key = f"awesome:{url}"
    cached = get_cached(cache_key)
    if cached is not None:
        return [SkillRepo(**item) for item in cached]

    try:
        response = httpx.get(url, timeout=FETCH_TIMEOUT_SECONDS, follow_redirects=True)
    except httpx.RequestError as e:
        logger.warning("Failed to fetch awesome list %s: %s", url, e)
        return []
    if response.status_code != 200:
        logger.warning("Awesome list %s returned HTTP %s; skipping", url, response.status_code)
        return []

    repos = parse_awesome_markdown(response.text)
    if not repos:
        logger.warning("Awesome list %s yielded no repo links; skipping", url)
        return []
    set_cached(cache_key, [asdict(r) for r in repos])
    return repos


def parse_awesome_markdown(text: str) -> list[SkillRepo]:
    """Extract GitHub repo links from awesome-list markdown.

    Meta repos (the lists themselves) are excluded; official collections such
    as anthropics/skills are kept as curated entries. Image links
    (``![alt](https://github.com/...)``) are ignored.
    """
    repos: dict[str, SkillRepo] = {}
    for owner, raw_name in GITHUB_REPO_RE.findall(_IMAGE_LINK_RE.sub("", text)):
        name = raw_name.removesuffix(".git")
        full_name = f"{owner}/{name}"
        if full_name in repos or full_name in _META_REPOS:
            continue
        repos[full_name] = SkillRepo(
            name=name,
            full_name=full_name,
            description="",
            stars=0,
            topics=[],
            html_url=f"https://github.com/{full_name}",
            tier="curated",
            source_channel="awesome-list",
        )
    return list(repos.values())
