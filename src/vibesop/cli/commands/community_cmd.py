"""Community skill sharing via GitHub Issues.

Usage:
    vibe skills share [skill_id]      Publish a skill to the community
    vibe skills discover [query]      Search community skills
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import urllib.parse
import webbrowser
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

logger = logging.getLogger(__name__)


console = Console()
GITHUB_REPO = "nehcuh/vibesop-py"
GITHUB_ISSUES_API = f"https://api.github.com/repos/{GITHUB_REPO}/issues"


def _open_issue_form(
    template: str,
    title: str,
    body: str,
    labels: str = "",
) -> None:
    """Open the GitHub new issue page with prefilled template."""
    params: dict[str, str] = {"template": template, "title": title, "body": body}
    if labels:
        params["labels"] = labels
    query = urllib.parse.urlencode(params)
    url = f"https://github.com/{GITHUB_REPO}/issues/new?{query}"

    console.print(Panel(f"Opening [cyan]{url}[/cyan]", title="Share Skill"))
    webbrowser.open(url)


def _fetch_community_skills(
    label: str = "skill-share",
    per_page: int = 20,
) -> list[dict]:
    """Fetch community skill issues from GitHub API."""
    token = os.environ.get("GITHUB_TOKEN", os.environ.get("GH_TOKEN", ""))

    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"{GITHUB_ISSUES_API}?labels={label}&state=open&per_page={per_page}&sort=reactions&direction=desc"

    try:
        import urllib.request

        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception:
        return []


def _read_skill_content(skill_id: str) -> tuple[str, str]:
    """Read a skill's name, description, and SKILL.md content."""
    search_paths = [
        Path(".vibe/skills"),
        Path("skills"),
        Path.home() / ".claude" / "skills",
        Path.home() / ".config" / "skills",
    ]

    for base in search_paths:
        skill_dir = base / skill_id
        if skill_dir.exists():
            # Try multiple SKILL.md locations
            for md_name in ("SKILL.md", "skill.md", "README.md"):
                md_path = skill_dir / md_name
                if md_path.exists():
                    content = md_path.read_text(encoding="utf-8")
                    return skill_id, content

            # Try namespace/path variant
            parts = skill_id.split("/")
            if len(parts) > 1:
                ns_path = base / parts[0] / parts[1]
                for md_name in ("SKILL.md", "skill.md", "README.md"):
                    md_path = ns_path / md_name
                    if md_path.exists():
                        content = md_path.read_text(encoding="utf-8")
                        return skill_id, content

    return skill_id, ""


def _try_gh_cli_issue(
    title: str,
    body: str,
    labels: str = "skill-share,community",
) -> bool:
    """Try to create issue via gh CLI directly. Returns True on success."""
    try:
        result = subprocess.run(
            [
                "gh",
                "issue",
                "create",
                "--repo",
                GITHUB_REPO,
                "--title",
                title,
                "--body",
                body,
                "--label",
                labels,
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if result.returncode == 0:
            console.print(f"[green]✓ Issue created:[/green] {result.stdout.strip()}")
            return True
        console.print(f"[yellow]gh CLI failed:[/yellow] {result.stderr.strip()[:200]}")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return False


def share(
    skill_id: str = typer.Argument(..., help="Skill ID to share"),
) -> None:
    """Publish a skill to the community via GitHub Issues.

    Opens a browser with a prefilled issue form.
    If `gh` CLI is installed, creates the issue directly.

    Examples:
        vibe skills share my-custom-skill
        vibe skills share gstack/custom-linter
    """
    name, content = _read_skill_content(skill_id)
    if not content:
        console.print(f"[red]Skill not found:[/red] {skill_id}")
        console.print("[dim]Make sure the skill is installed and has a SKILL.md file.[/dim]")
        raise typer.Exit(1)

    title = f"[技能分享] {name}"
    body = f"""## Skill: {name}

```markdown
{content[:5000]}
```
"""
    if len(content) > 5000:
        body += "\n\n> _Content truncated. Full SKILL.md exceeds 5000 characters._"

    # Try direct gh CLI first
    if not _try_gh_cli_issue(title, body):
        _open_issue_form("skill-share.yml", title, body)


def discover(
    query: str | None = typer.Argument(None, help="Search keywords for community skills"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Discover community-shared skills from GitHub Issues.

    Lists skills shared by the community, sorted by 👍 reactions.
    Use a search query to filter by name or description.

    Examples:
        vibe skills discover
        vibe skills discover debugging
        vibe skills discover "python lint"
    """
    skills = _fetch_community_skills(label="skill-share")

    if not skills:
        console.print(
            Panel(
                "[dim]No community skills found. Be the first to share!\n\n"
                "Use [cyan]vibe skills share <skill_id>[/cyan] to publish yours.[/dim]",
                title="Community Skills",
                border_style="dim",
            )
        )
        return

    # Filter by query if provided
    if query:
        q = query.lower()
        skills = [
            s for s in skills
            if q in s.get("title", "").lower() or q in (s.get("body") or "").lower()
        ]
        if not skills:
            console.print(f"[dim]No skills matching '{query}' found in community.[/dim]")
            return

    if json_output:
        result = [
            {
                "title": s["title"],
                "url": s["html_url"],
                "reactions": s.get("reactions", {}).get("+1", 0),
                "created_at": s.get("created_at", ""),
                "labels": [label["name"] for label in s.get("labels", [])],
            }
            for s in skills[:20]
        ]
        console.print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    table = Table(title="🌐 Community Skills", show_header=True)
    table.add_column("Skill", style="cyan")
    table.add_column("👍", justify="center", width=6)
    table.add_column("Date", style="dim", width=10)

    for s in skills[:20]:
        title = s.get("title", "Unknown").replace("[技能分享] ", "").strip()
        url = s.get("html_url", "")
        reactions = s.get("reactions", {}).get("+1", 0)
        created = s.get("created_at", "")[:10]

        table.add_row(f"[link={url}]{title}[/link]", str(reactions), created)

    console.print(table)
    console.print()
    console.print(
        f"[dim]{len(skills)} skills in community. "
        'Sort by reactions (github API sort=reactions).[/dim]'
    )
    console.print(
        "[dim]To install a community skill, copy its SKILL.md to "
        ".vibe/skills/<skill-id>/SKILL.md[/dim]"
    )
