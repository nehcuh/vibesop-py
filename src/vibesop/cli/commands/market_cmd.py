"""VibeSOP market command - Discover and install skills from the public ecosystem.

Usage:
    vibe market search <query>
    vibe market search <query> --json
    vibe market trending <category>
    vibe market install <user/repo>
    vibe market install <user/repo> --scope project
"""

from __future__ import annotations

import json
from typing import Literal

import typer
from rich.console import Console
from rich.table import Table

from vibesop.constants import TRUSTED_PACKS
from vibesop.market.awesome_list import fetch_awesome_lists
from vibesop.market.crawler import GitHubSkillCrawler, SkillRepo

console = Console()

app = typer.Typer(name="market", help="Discover and install skills from the public skill ecosystem")

#: Lower rank sorts first.
_TIER_RANK = {"official": 0, "curated": 1}


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query for skills"),
    page: int = typer.Option(1, "--page", "-p", help="Page number"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Search the public skill ecosystem on GitHub.

    Combines GitHub topic search (agent-skills, claude-skills, and friends)
    with curated awesome lists. Results are deduplicated by repository and
    sorted by trust tier (official/curated first), then by stars.

    \b
    Examples:
        # Search for git-related skills
        vibe market search git

        # Search with JSON output
        vibe market search git --json

        # Search page 2
        vibe market search git --page 2
    """
    crawler = GitHubSkillCrawler()
    results = crawler.search(query, page=page)
    results = _merge_results(results, _curated_matches(query))
    _apply_trusted_tier(results)
    results.sort(key=lambda r: (_TIER_RANK.get(r.tier, 2), -r.stars))

    if json_output:
        _print_results_json(results)
        return

    if not results:
        console.print("[yellow]No skills found.[/yellow]")
        return

    _render_results_table(results, f"Market Search Results for '{query}'")


#: Friendly category → GitHub topic mapping for ``vibe market trending``.
_CATEGORY_TOPICS: dict[str, str] = {
    "agent": "agent-skills",
    "claude": "claude-skills",
    "claude-code": "claude-code-skills",
    "skill-md": "skill-md",
}


@app.command()
def trending(
    category: str = typer.Argument(
        ...,
        help="Category: agent, claude, claude-code, skill-md, or any GitHub topic",
    ),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Show trending skill repositories for a category, sorted by stars.

    The category maps to a GitHub topic; unknown categories are used as
    topic names directly.

    \b
    Examples:
        # Trending agent skills
        vibe market trending agent

        # Trending Claude Code skills, as JSON
        vibe market trending claude-code --json
    """
    topic = _CATEGORY_TOPICS.get(category)
    if topic is None:
        topic = category
        console.print(
            f"[dim]Unknown category '{category}'; using it as a GitHub topic directly.[/dim]"
        )

    crawler = GitHubSkillCrawler(topics=(topic,))
    results = crawler.search("")
    _apply_trusted_tier(results)
    results.sort(key=lambda r: (_TIER_RANK.get(r.tier, 2), -r.stars))

    if json_output:
        _print_results_json(results)
        return

    if not results:
        console.print("[yellow]No skills found.[/yellow]")
        return

    _render_results_table(results, f"Trending Skills for '{category}' (topic: {topic})")


@app.command()
def install(
    repo: str = typer.Argument(..., help="GitHub repository in user/repo format"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
    scope: str = typer.Option(
        "global",
        "--scope",
        help="Install scope: 'global' (~/.config/skills, all projects) or "
        "'project' (.vibe/skills, current project only)",
    ),
) -> None:
    """Install a skill from a GitHub repository.

    Validates that the repository contains at least one SKILL.md file
    (root or subdirectory — skill packs keep skills in subdirectories),
    then installs it via the PackInstaller. Both scopes run the full
    security chain (pre-install audit, pack-lock integrity, build gate);
    project scope skips platform symlinks and the global index.

    \b
    Examples:
        # Install from GitHub repo (global, visible to all projects)
        vibe market install user/repo

        # Install into the current project's .vibe/skills/ only
        vibe market install user/repo --scope project

        # Install without confirmation prompt
        vibe market install user/repo --yes
    """
    import questionary

    from vibesop.installer.pack_installer import PackInstaller

    if scope not in ("global", "project"):
        console.print("[red]--scope must be 'global' or 'project'[/red]")
        raise typer.Exit(1)
    scope_value: Literal["global", "project"] = "project" if scope == "project" else "global"

    if "/" not in repo:
        console.print("[red]Repository must be in 'user/repo' format[/red]")
        raise typer.Exit(1)

    crawler = GitHubSkillCrawler()
    url = f"https://github.com/{repo}"
    skill_repo = SkillRepo(
        name=repo.rsplit("/", maxsplit=1)[-1],
        full_name=repo,
        description="",
        stars=0,
        topics=[],
        html_url=url,
    )

    with console.status("[bold green]Validating repository..."):
        has_skill_md = crawler.validate(skill_repo)

    if not has_skill_md:
        console.print(f"[red]Repository '{repo}' does not contain any SKILL.md file[/red]")
        raise typer.Exit(1)

    console.print(f"[green]Repository '{repo}' is valid[/green]")

    if not yes:
        dest = (
            f"~/.config/skills/{skill_repo.name} (global scope)"
            if scope_value == "global"
            else f".vibe/skills/{skill_repo.name} (project scope, current project only)"
        )
        tier_repo = _resolve_install_tier(repo, skill_repo)
        if tier_repo.tier != "official":
            _print_tier_panel(tier_repo)
        confirmed = questionary.confirm(
            f"Install skill pack from {url} into {dest}?",
            default=True,
        ).ask()
        if not confirmed:
            console.print("[yellow]Installation cancelled.[/yellow]")
            raise typer.Exit(0)

    installer = PackInstaller()
    try:
        success, message = installer.install_pack(skill_repo.name, url, scope=scope_value)
        if success:
            console.print(f"[green]Successfully installed {skill_repo.name}[/green]")
            for line in message.split("\n"):
                console.print(f"[dim]{line}[/dim]")
        else:
            console.print(f"[red]Installation failed: {message}[/red]")
            raise typer.Exit(1) from None
    except Exception as e:
        console.print(f"[red]Installation failed: {e}[/red]")
        raise typer.Exit(1) from e


def _merge_results(github_results: list[SkillRepo], curated: list[SkillRepo]) -> list[SkillRepo]:
    """Merge GitHub search results with curated awesome-list entries.

    Deduplicated by full_name. When a repo appears in both channels, the
    GitHub entry (which has real stars/description) wins and inherits the
    curated tier.
    """
    merged: dict[str, SkillRepo] = {}
    for repo in github_results:
        merged[repo.full_name] = repo
    for repo in curated:
        existing = merged.get(repo.full_name)
        if existing is None:
            merged[repo.full_name] = repo
        else:
            existing.tier = "curated"
    return list(merged.values())


def _curated_matches(query: str) -> list[SkillRepo]:
    """Return awesome-list entries whose repo name matches the query."""
    needle = query.lower()
    return [r for r in fetch_awesome_lists() if needle in r.full_name.lower()]


def _apply_trusted_tier(results: list[SkillRepo]) -> None:
    """Mark repos listed in TRUSTED_PACKS as official."""
    trusted = _trusted_full_names()
    for repo in results:
        if repo.full_name in trusted:
            repo.tier = "official"


def _trusted_full_names() -> set[str]:
    """Full names (owner/repo) of the hard-coded official packs."""
    return {url.split("github.com/", 1)[-1] for url in TRUSTED_PACKS.values()}


def _resolve_install_tier(full_name: str, fallback: SkillRepo) -> SkillRepo:
    """Determine the trust tier of a repo about to be installed.

    No extra network requests: official packs come from the hard-coded
    TRUSTED_PACKS, curated repos are matched against the cache-backed
    awesome-list channel. Anything else keeps the fallback's unknown tier.
    """
    if full_name in _trusted_full_names():
        fallback.tier = "official"
        return fallback
    for entry in fetch_awesome_lists():
        if entry.full_name == full_name:
            return entry
    return fallback


def _print_tier_panel(repo: SkillRepo) -> None:
    """Show trust metadata before installing a non-official repository."""
    if repo.tier == "curated":
        label = r"[cyan]\[curated][/cyan]"
    else:
        label = r"[red]\[未知来源 - 未经验证][/red]"
    console.print(f"  [dim]Tier:[/dim] {label}")
    console.print(f"  [dim]Stars:[/dim] {repo.stars}")
    console.print(f"  [dim]Description:[/dim] {repo.description or '—'}")


def _print_results_json(results: list[SkillRepo]) -> None:
    """Print search/trending results as JSON."""
    data = [
        {
            "source": r.source_channel,
            "tier": r.tier,
            "name": r.name,
            "full_name": r.full_name,
            "description": r.description,
            "stars": r.stars,
            "topics": r.topics,
            "html_url": r.html_url,
        }
        for r in results
    ]
    console.print(json.dumps(data, indent=2))


def _render_results_table(results: list[SkillRepo], title: str) -> None:
    """Render search/trending results as a table."""
    table = Table(title=title)
    table.add_column("Name", style="cyan")
    table.add_column("Tier", justify="center")
    table.add_column("Description", style="green")
    table.add_column("Stars", justify="right", style="yellow")
    table.add_column("Install Command", style="dim")

    for repo in results:
        table.add_row(
            repo.name,
            _tier_badge(repo.tier),
            repo.description or "—",
            str(repo.stars),
            f"vibe market install {repo.full_name}",
        )

    console.print(table)
    console.print(f"\n[dim]Found {len(results)} result(s)[/dim]")


def _tier_badge(tier: str) -> str:
    """Render a trust tier as a colored badge."""
    if tier == "official":
        return r"[green]\[官方][/green]"
    if tier == "curated":
        return r"[cyan]\[curated][/cyan]"
    return r"[dim]\[未知][/dim]"
