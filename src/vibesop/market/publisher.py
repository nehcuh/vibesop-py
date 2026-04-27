"""GitHub Issues-based skill publisher.

Uses a designated repository's Issues as a lightweight "registry"
for skill discovery. No extra infrastructure needed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import httpx
import yaml

DEFAULT_REGISTRY_REPO = "nehcuh/vibesop-py"
PUBLISH_LABEL = "skill-publish"


@dataclass
class SkillListing:
    """A published skill from a GitHub Issue."""

    repo_name: str
    description: str
    tags: list[str] = field(default_factory=list)
    homepage: str = ""
    issue_url: str = ""
    issue_number: int = 0

    @property
    def install_source(self) -> str:
        return f"https://github.com/{self.repo_name}"


class SkillPublisher:
    """Publish and discover skills via GitHub Issues."""

    BASE_URL = "https://api.github.com"

    def __init__(
        self, token: str | None = None, registry_repo: str = DEFAULT_REGISTRY_REPO
    ) -> None:
        self.token = token or os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
        self.registry_repo = registry_repo
        self.headers: dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            self.headers["Authorization"] = f"Bearer {self.token}"

    def publish(
        self,
        repo_name: str,
        description: str | None = None,
        tags: list[str] | None = None,
        homepage: str = "",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Publish a skill by creating a labeled GitHub Issue.

        Args:
            repo_name: GitHub repo in 'owner/repo' format
            description: Skill description (auto-detected from SKILL.md if None)
            tags: Skill tags (auto-detected from SKILL.md if None)
            homepage: Optional project homepage URL
            dry_run: If True, return payload without creating issue

        Returns:
            Dict with issue_url, issue_number, repo_name
        """
        if "/" not in repo_name:
            return {"error": "repo_name must be in 'owner/repo' format"}

        if description is None or tags is None:
            detected = self._detect_from_skill_md(repo_name)
            if description is None:
                description = detected.get("description", "")
            if tags is None:
                tags = detected.get("tags", [])

        title = f"[{PUBLISH_LABEL}] {repo_name}"
        body_parts = [
            f"## {description or 'A VibeSOP skill'}",
            "",
            f"- **Repository**: [{repo_name}](https://github.com/{repo_name})",
            f"- **Install**: `vibe market install {repo_name}`",
        ]
        if tags:
            body_parts.append(f"- **Tags**: {', '.join(tags)}")
        if homepage:
            body_parts.append(f"- **Homepage**: {homepage}")
        body_parts.extend(
            [
                "",
                "---",
                "*Published via VibeSOP SkillPublisher. Close this issue to delist.*",
            ]
        )
        body = "\n".join(body_parts)

        payload: dict[str, Any] = {
            "title": title,
            "body": body,
            "labels": [PUBLISH_LABEL],
        }

        if dry_run:
            return {"dry_run": True, "payload": payload, "repo_name": repo_name}

        if not self.token:
            return {"error": "GITHUB_TOKEN or GH_TOKEN environment variable required for publish"}

        url = f"{self.BASE_URL}/repos/{self.registry_repo}/issues"
        try:
            with httpx.Client(headers=self.headers, timeout=30.0) as client:
                response = client.post(url, json=payload)
            if response.status_code == 201:
                data = response.json()
                return {
                    "issue_url": data.get("html_url", ""),
                    "issue_number": data.get("number", 0),
                    "repo_name": repo_name,
                }
            return {
                "error": f"GitHub API returned {response.status_code}",
                "detail": response.text[:200],
            }
        except httpx.RequestError as e:
            return {"error": str(e)}

    def search_issues(self, query: str = "", page: int = 1) -> list[SkillListing]:
        """Search published skills by querying labeled Issues.

        Args:
            query: Optional search keywords (searches issue title+body)
            page: Results page number

        Returns:
            List of SkillListing objects
        """
        q_parts = [f"repo:{self.registry_repo}", f"label:{PUBLISH_LABEL}", "state:open"]
        if query:
            q_parts.append(query)
        params: dict[str, Any] = {
            "q": " ".join(q_parts),
            "page": page,
            "per_page": 30,
            "sort": "created",
            "order": "desc",
        }
        url = f"{self.BASE_URL}/search/issues"

        with httpx.Client(headers=self.headers, timeout=30.0) as client:
            response = client.get(url, params=params)

        if response.status_code != 200:
            return []

        data = response.json()
        items = data.get("items", [])
        listings: list[SkillListing] = []

        for item in items:
            title = item.get("title", "")
            if not title.startswith(f"[{PUBLISH_LABEL}]"):
                continue
            repo_name = title[len(f"[{PUBLISH_LABEL}] ") :].strip()
            body = item.get("body", "")
            desc, tag_list, homepage = self._parse_issue_body(body)
            listings.append(
                SkillListing(
                    repo_name=repo_name,
                    description=desc,
                    tags=tag_list,
                    homepage=homepage,
                    issue_url=item.get("html_url", ""),
                    issue_number=item.get("number", 0),
                )
            )

        return listings

    def _detect_from_skill_md(self, repo_name: str) -> dict[str, Any]:
        """Try to fetch SKILL.md from the repo to auto-detect metadata."""
        result: dict[str, Any] = {"description": "", "tags": []}
        url = f"{self.BASE_URL}/repos/{repo_name}/contents/SKILL.md"
        try:
            with httpx.Client(headers=self.headers, timeout=10.0) as client:
                resp = client.get(url)
            if resp.status_code != 200:
                return result
            import base64

            content = base64.b64decode(resp.json()["content"]).decode("utf-8")
            frontmatter = self._parse_frontmatter(content)
            result["description"] = frontmatter.get("description", "")
            result["tags"] = frontmatter.get("tags", [])
        except (httpx.RequestError, KeyError, ValueError, UnicodeDecodeError):
            pass
        return result

    @staticmethod
    def _parse_frontmatter(content: str) -> dict[str, Any]:
        """Extract YAML frontmatter from SKILL.md."""
        if not content.startswith("---"):
            return {}
        parts = content.split("---", 2)
        if len(parts) < 3:
            return {}
        try:
            data = yaml.safe_load(parts[1])
            return data if isinstance(data, dict) else {}
        except yaml.YAMLError:
            return {}

    @staticmethod
    def _parse_issue_body(body: str) -> tuple[str, list[str], str]:
        """Extract description, tags, and homepage from issue body."""
        description = ""
        tags: list[str] = []
        homepage = ""

        for raw_line in body.split("\n"):
            stripped = raw_line.strip()
            if stripped.startswith("## ") and not description:
                description = stripped[3:].strip()
            elif stripped.startswith("- **Tags**:"):
                raw = stripped.split("**Tags**:", 1)[1].strip()
                tags = [t.strip() for t in raw.split(",") if t.strip()]
            elif stripped.startswith("- **Homepage**:"):
                homepage = stripped.split("**Homepage**:", 1)[1].strip()

        return description, tags, homepage
