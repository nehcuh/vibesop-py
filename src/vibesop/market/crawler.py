"""GitHub topic crawler for discovering vibesop-skill repositories."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class SkillRepo:
    """A GitHub repository tagged with vibesop-skill."""

    name: str
    full_name: str
    description: str
    stars: int
    topics: list[str]
    html_url: str
    has_skill_md: bool = False
    quality_score: float = 0.0

    def infer_skill_id(self) -> str:
        """Infer local skill ID from GitHub repo name."""
        return self.full_name.replace("/", "/", 1).rsplit("/", 1)[-1]

    @property
    def install_source(self) -> str:
        """Return the installable source (git URL) for this repo."""
        return f"https://github.com/{self.full_name}"


class GitHubSkillCrawler:
    """Search GitHub for repositories tagged with topic:vibesop-skill."""

    BASE_URL = "https://api.github.com"

    def __init__(self, token: str | None = None) -> None:
        self.token = token
        self.headers: dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    def search(self, query: str, page: int = 1) -> list[SkillRepo]:
        """Search GitHub for repos with topic:vibesop-skill + query."""
        q = f"{query}+topic:vibesop-skill"
        params: dict[str, Any] = {"q": q, "page": page, "per_page": 30}
        url = f"{self.BASE_URL}/search/repositories"

        with httpx.Client(headers=self.headers, timeout=30.0) as client:
            response = client.get(url, params=params)

        if response.status_code != 200:
            return []

        data = response.json()
        items = data.get("items", [])

        return [
            SkillRepo(
                name=item["name"],
                full_name=item["full_name"],
                description=item.get("description") or "",
                stars=item.get("stargazers_count", 0),
                topics=item.get("topics", []),
                html_url=item["html_url"],
            )
            for item in items
        ]

    def validate(self, repo: SkillRepo) -> bool:
        """Check if repo has SKILL.md at root."""
        url = f"{self.BASE_URL}/repos/{repo.full_name}/contents/SKILL.md"

        with httpx.Client(headers=self.headers, timeout=30.0) as client:
            response = client.get(url)

        return response.status_code == 200
