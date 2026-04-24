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

    if json_output:
        data = [
            {
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
        return

    if not results:
        console.print("[yellow]No skills found.[/yellow]")
        return

    table = Table(title=f"Market Search Results for '{query}'")
    table.add_column("Name", style="cyan")
    table.add_column("Description", style="green")
    table.add_column("Stars", justify="right", style="yellow")
    table.add_column("Install Command", style="dim")

    for repo in results:
        table.add_row(
            repo.name,
            repo.description or "—",
            str(repo.stars),
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
        name=repo.split("/")[-1],
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
    console.print(f"\n[bold]Install command:[/bold]")
    console.print(f"  [cyan]vibe install https://github.com/{repo}[/cyan]")
