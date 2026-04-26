"""VibeSOP market command - Discover and install skills from GitHub.

Usage:
    vibe market search <query>
    vibe market search <query> --json
    vibe market install <user/repo>
"""

from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.table import Table

from vibesop.market.crawler import GitHubSkillCrawler, SkillRepo

console = Console()

app = typer.Typer(name="market", help="Discover and install VibeSOP skills")


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

    if json_output:
        data = [
            {
                "name": r.name,
                "full_name": r.full_name,
                "description": r.description,
                "stars": r.stars,
                "topics": r.topics,
                "html_url": r.html_url,
                "quality_score": round(r.quality_score, 1),
            }
            for r in results
        ]
        console.print(json.dumps(data, indent=2))
        return

    if not results:
        console.print("[yellow]No skills found.[/yellow]")
        return

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
    console.print(f"\n[dim]Found {len(results)} result(s)[/dim]")


@app.command()
def install(
    repo: str = typer.Argument(..., help="GitHub repository in user/repo format"),
) -> None:
    """Install a skill from a GitHub repository.

    Validates that the repository has a SKILL.md file at the root.

    \b
    Examples:
        # Install from GitHub repo
        vibe market install user/repo
    """
    if "/" not in repo:
        console.print("[red]✗ Repository must be in 'user/repo' format[/red]")
        raise typer.Exit(1)

    crawler = GitHubSkillCrawler()
    skill_repo = SkillRepo(
        name=repo.rsplit("/", maxsplit=1)[-1],
        full_name=repo,
        description="",
        stars=0,
        topics=[],
        html_url=f"https://github.com/{repo}",
    )

    with console.status("[bold green]Validating repository..."):
        has_skill_md = crawler.validate(skill_repo)

    if not has_skill_md:
        console.print(
            f"[red]✗ Repository '{repo}' does not have a SKILL.md file at the root[/red]"
        )
        raise typer.Exit(1)

    console.print(f"[green]✓ Repository '{repo}' is valid[/green]")
    console.print("\n[bold]Install command:[/bold]")
    console.print(f"  [cyan]vibe install https://github.com/{repo}[/cyan]")


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
