"""GitHub topic crawler for discovering agent skill repositories.

Searches the public skill ecosystem topics (agent-skills, claude-skills,
claude-skill, claude-code-skills, skill-md) instead of the self-referential
``vibesop-skill`` topic, which matches zero repositories.
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass
from typing import Any

import httpx

from vibesop.market.cache import (
    CACHE_TTL_SECONDS,
    PARTIAL_CACHE_TTL_SECONDS,
    get_cached,
    normalize_query,
    set_cached,
)

logger = logging.getLogger(__name__)

#: Public-ecosystem topics searched by default.
DEFAULT_TOPICS: tuple[str, ...] = (
    "agent-skills",
    "claude-skills",
    "claude-skill",
    "claude-code-skills",
    "skill-md",
)

#: Results requested per topic. Kept small to stay within the GitHub search
#: rate limit (30 req/min authenticated, 10 req/min unauthenticated).
PER_TOPIC_PER_PAGE = 10


@dataclass
class SkillRepo:
    """A GitHub repository that provides agent skills."""

    name: str
    full_name: str
    description: str
    stars: int
    topics: list[str]
    html_url: str
    has_skill_md: bool = False
    quality_score: float = 0.0
    #: Trust tier: "official" | "curated" | "unknown".
    tier: str = "unknown"
    #: Discovery channel: "github" | "awesome-list".
    source_channel: str = "github"

    def infer_skill_id(self) -> str:
        """Infer local skill ID from GitHub repo name."""
        return self.full_name.replace("/", "/", 1).rsplit("/", 1)[-1]

    @property
    def install_source(self) -> str:
        """Return the installable source (git URL) for this repo."""
        return f"https://github.com/{self.full_name}"


class GitHubSkillCrawler:
    """Search GitHub for agent-skill repositories across public ecosystem topics."""

    BASE_URL = "https://api.github.com"

    def __init__(
        self,
        token: str | None = None,
        topics: tuple[str, ...] = DEFAULT_TOPICS,
    ) -> None:
        self.token = token or os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
        self.topics = topics
        self.headers: dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            self.headers["Authorization"] = f"Bearer {self.token}"

    def search(self, query: str, page: int = 1) -> list[SkillRepo]:
        """Search public ecosystem topics for repos matching query.

        GitHub treats multiple ``topic:`` qualifiers as AND, so OR semantics
        require one request per topic; results are merged and deduplicated by
        full_name, sorted by stars descending. Results are cached on disk to
        stay within the search API rate limit: full successes for 24h,
        partial successes (some topics failed) for 5 minutes so the failed
        topics are retried soon. Total failures are never cached.
        """
        topics_key = ",".join(sorted(self.topics))
        cache_key = f"gh:{normalize_query(query)}#topics:{topics_key}#page{page}"
        cached = get_cached(cache_key)
        if cached is not None:
            return [SkillRepo(**item) for item in cached]

        repos: dict[str, SkillRepo] = {}
        failed_topics = 0
        with httpx.Client(headers=self.headers, timeout=30.0) as client:
            for topic in self.topics:
                params: dict[str, Any] = {
                    "q": f"{query} topic:{topic}",
                    "page": page,
                    "per_page": PER_TOPIC_PER_PAGE,
                    "sort": "stars",
                }
                try:
                    response = client.get(f"{self.BASE_URL}/search/repositories", params=params)
                except httpx.RequestError as e:
                    logger.warning("GitHub topic search failed for %s: %s", topic, e)
                    failed_topics += 1
                    continue
                if response.status_code != 200:
                    logger.warning(
                        "GitHub topic search for %s returned HTTP %s",
                        topic,
                        response.status_code,
                    )
                    failed_topics += 1
                    continue
                for item in response.json().get("items", []):
                    full_name = item["full_name"]
                    if full_name in repos:
                        continue
                    repos[full_name] = SkillRepo(
                        name=item["name"],
                        full_name=full_name,
                        description=item.get("description") or "",
                        stars=item.get("stargazers_count", 0),
                        topics=item.get("topics", []),
                        html_url=item["html_url"],
                    )

        results = sorted(repos.values(), key=lambda r: r.stars, reverse=True)
        if failed_topics < len(self.topics):
            ttl = CACHE_TTL_SECONDS if failed_topics == 0 else PARTIAL_CACHE_TTL_SECONDS
            set_cached(cache_key, [asdict(r) for r in results], ttl=ttl)
        return results

    def validate(self, repo: SkillRepo) -> bool:
        """Check if the repo contains any SKILL.md (root or subdirectory).

        Uses the git trees API (one recursive request) so skill *pack* repos —
        whose skills live in per-skill subdirectories rather than a root
        SKILL.md — are also accepted. Very large repos may return a truncated
        tree; in that case a missed SKILL.md only rejects an otherwise
        installable repo, which fails safe.
        """
        url = f"{self.BASE_URL}/repos/{repo.full_name}/git/trees/HEAD"
        params: dict[str, Any] = {"recursive": "1"}

        with httpx.Client(headers=self.headers, timeout=30.0) as client:
            response = client.get(url, params=params)

        if response.status_code == 403:
            raise RuntimeError(
                "GitHub API rate limit or permission error (403) while checking "
                f"{repo.full_name}. Set GITHUB_TOKEN or GH_TOKEN to raise the limit."
            )
        if response.status_code != 200:
            return False

        tree = response.json().get("tree", [])
        return any(
            item.get("type") == "blob" and str(item.get("path", "")).endswith("SKILL.md")
            for item in tree
        )
