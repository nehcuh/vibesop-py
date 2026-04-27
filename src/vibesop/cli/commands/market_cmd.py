"""VibeSOP market command - Discover, publish, and install skills from GitHub.

Usage:
    vibe market search <query>
    vibe market search <query> --json
    vibe market install <user/repo>
    vibe market publish [user/repo]
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from vibesop.market.crawler import GitHubSkillCrawler, SkillRepo
from vibesop.market.publisher import SkillPublisher, SkillListing

console = Console()

app = typer.Typer(name="market", help="Discover, publish, and install VibeSOP skills")


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query for skills"),
    page: int = typer.Option(1, "--page", "-p", help="Page number"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Search for VibeSOP skills on GitHub.

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
    results = _enrich_with_local_quality(results)

    # Also search published skills (GitHub Issues)
    publisher = SkillPublisher()
    listings = publisher.search_issues(query, page=page)

    if json_output:
        data = []
        for r in results:
            data.append({
                "source": "github",
                "name": r.name,
                "full_name": r.full_name,
                "description": r.description,
                "stars": r.stars,
                "topics": r.topics,
                "html_url": r.html_url,
                "quality_score": round(r.quality_score, 1),
            })
        for listing in listings:
            data.append({
                "source": "published",
                "repo_name": listing.repo_name,
                "description": listing.description,
                "tags": listing.tags,
                "homepage": listing.homepage,
                "issue_url": listing.issue_url,
            })
        console.print(json.dumps(data, indent=2))
        return

    if not results and not listings:
        console.print("[yellow]No skills found.[/yellow]")
        return

    if results:
        table = Table(title=f"Market Search Results for '{query}'")
        table.add_column("Name", style="cyan")
        table.add_column("Description", style="green")
        table.add_column("Stars", justify="right", style="yellow")
        table.add_column("Quality", justify="center")
        table.add_column("Install Command", style="dim")

        for repo in results:
            quality_display = _quality_icon(repo.quality_score)
            table.add_row(
                repo.name,
                repo.description or "\u2014",
                str(repo.stars),
                quality_display,
                f"vibe market install {repo.full_name}",
            )

        console.print(table)

    if listings:
        console.print(f"\n[bold]Published Skills ({len(listings)}):[/bold]")
        for listing in listings:
            console.print(f"  [cyan]{listing.repo_name}[/cyan] — {listing.description or 'no description'}")
            console.print(f"    [dim]Published: {listing.issue_url}[/dim]")
            if listing.tags:
                console.print(f"    [dim]Tags: {', '.join(listing.tags)}[/dim]")

    total = len(results) + len(listings)
    console.print(f"\n[dim]Found {total} result(s)[/dim]")


@app.command()
def install(
    repo: str = typer.Argument(..., help="GitHub repository in user/repo format"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Install a skill from a GitHub repository.

    Validates that the repository has a SKILL.md file at the root,
    then installs it via the PackInstaller.

    \b
    Examples:
        # Install from GitHub repo
        vibe market install user/repo

        # Install without confirmation prompt
        vibe market install user/repo --yes
    """
    import questionary

    from vibesop.installer.pack_installer import PackInstaller

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
        console.print(
            f"[red]Repository '{repo}' does not have a SKILL.md file at the root[/red]"
        )
        raise typer.Exit(1)

    console.print(f"[green]Repository '{repo}' is valid[/green]")

    if not yes:
        confirmed = questionary.confirm(
            f"Install skill pack from {url}?",
            default=True,
        ).ask()
        if not confirmed:
            console.print("[yellow]Installation cancelled.[/yellow]")
            raise typer.Exit(0)

    installer = PackInstaller()
    try:
        result = installer.install_pack(skill_repo.name, url)
        console.print(
            f"[green]Successfully installed {result.pack_name} "
            f"({result.skill_count} skills)[/green]"
        )
    except Exception as e:
        console.print(f"[red]Installation failed: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def publish(
    repo: str = typer.Argument(
        "",
        help="GitHub repository in user/repo format (auto-detected from git remote if omitted)",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview the issue without creating it"),
) -> None:
    """Publish a skill to the VibeSOP marketplace via GitHub Issue.

    Creates a labeled Issue on the VibeSOP registry repository.
    Requires GITHUB_TOKEN or GH_TOKEN environment variable.

    \b
    Examples:
        # Auto-detect repo from git remote
        vibe market publish

        # Specify repo explicitly
        vibe market publish user/my-skill

        # Preview without publishing
        vibe market publish --dry-run
    """
    if not repo:
        repo = _detect_git_remote()
        if not repo:
            console.print(
                "[red]Could not detect GitHub repo. "
                "Run from a git repo or specify user/repo.[/red]"
            )
            raise typer.Exit(1)

    publisher = SkillPublisher()
    result = publisher.publish(repo, dry_run=dry_run)

    if "error" in result:
        console.print(f"[red]Publish failed: {result['error']}[/red]")
        if "detail" in result:
            console.print(f"[dim]{result['detail']}[/dim]")
        raise typer.Exit(1)

    if dry_run:
        console.print("[bold]Dry run — issue payload:[/bold]")
        console.print_json(json.dumps(result["payload"], indent=2))
        return

    console.print(f"[green]Skill published![/green]")
    console.print(f"  Issue: {result['issue_url']}")
    console.print(f"  Install: [cyan]vibe market install {repo}[/cyan]")


def _detect_git_remote() -> str:
    """Detect GitHub owner/repo from git remote origin."""
    import subprocess

    try:
        output = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            cwd=Path.cwd(),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        for prefix in ("https://github.com/", "git@github.com:"):
            if prefix in output:
                path = output.split(prefix, 1)[1]
                if path.endswith(".git"):
                    path = path[:-4]
                return path
    except (subprocess.CalledProcessError, FileNotFoundError, IndexError):
        pass
    return ""


def _enrich_with_local_quality(results: list[SkillRepo]) -> list[SkillRepo]:
    """Enrich market search results with local quality data.

    Combines GitHub stars (30%), local ratings (40%), and usage frequency (30%)
    into a composite quality_score (0-100) and sorts by descending score.
    """
    if not results:
        return results

    local_ratings = _get_local_ratings()
    local_usage = _get_local_usage()
    max_stars = max((r.stars for r in results), default=1)

    for repo in results:
        skill_id = repo.infer_skill_id()

        stars_norm = min(repo.stars / max(max_stars, 1), 1.0) * 30
        rating_norm = local_ratings.get(skill_id, 0.5) * 40
        usage_count = local_usage.get(skill_id, 0)
        usage_norm = min(usage_count / max(max(local_usage.values(), default=1), 1), 1.0) * 30

        repo.quality_score = stars_norm + rating_norm + usage_norm

    results.sort(key=lambda r: r.quality_score, reverse=True)
    return results


def _get_local_ratings() -> dict[str, float]:
    """Get local skill ratings, normalized to 0-1."""
    try:
        from vibesop.core.skills.ratings import SkillRatingStore
        store = SkillRatingStore()
        top = store.get_top_rated(limit=100, min_reviews=1)
        return {skill_id: score / 5.0 for skill_id, score, _count in top}
    except (ImportError, OSError):
        return {}


def _get_local_usage() -> dict[str, int]:
    """Get local skill usage counts."""
    try:
        from vibesop.core.analytics import AnalyticsStore
        store = AnalyticsStore()
        popular = store.get_popular_skills(limit=100)
        return {skill_id: count for skill_id, count, _satisfaction in popular}
    except (ImportError, OSError):
        return {}


def _quality_icon(score: float) -> str:
    """Display a quality score as a colored icon."""
    if score >= 70:
        return f"[green]\u2605 {score:.0f}[/green]"
    elif score >= 40:
        return f"[yellow]\u2605 {score:.0f}[/yellow]"
    elif score > 0:
        return f"[dim]{score:.0f}[/dim]"
    return "\u2014"
