"""Skills recommendations command — personalized skill recommendations."""

import typer
from rich.console import Console

console = Console()


def recommended(
    collaborative: bool = typer.Option(False, "--collaborative", "-c", help="Show collaborative filtering recommendations"),
    install: bool = typer.Option(False, "--install", "-i", help="Install all recommended skills"),
) -> None:
    """Show personalized skill recommendations.

    Recommends skills based on your project's tech stack and
    what other users with similar setups have installed.

    \b
    Examples:
        # Stack-based recommendations
        vibe skills recommended

        # Collaborative filtering
        vibe skills recommended --collaborative

        # Install all in one go
        vibe skills recommended --install
    """
    from vibesop.core.skills.recommender import SkillRecommender

    recommender = SkillRecommender()

    if collaborative:
        recs = recommender.recommend_collaborative()
        title = "Collaborative Recommendations"
    else:
        stack_recs = recommender.recommend_for_project()
        missing_recs = recommender.detect_missing_skills()
        recs = stack_recs + [r for r in missing_recs if r.skill_id not in {s.skill_id for s in stack_recs}]
        title = "Recommended for This Project"

    if not recs:
        console.print("[dim]No recommendations available. You might have all essential skills installed![/dim]")
        return

    from rich.table import Table
    table = Table(title=title)
    table.add_column("#", style="dim", justify="right")
    table.add_column("Skill", style="cyan")
    table.add_column("Reason", style="dim")
    table.add_column("Status", justify="center")

    for i, r in enumerate(recs, 1):
        status = "[green]installed[/green]" if r.installed else "[yellow]not installed[/yellow]"
        table.add_row(str(i), r.skill_id, r.reason, status)

    console.print(table)

    uninstalled = [r for r in recs if not r.installed]
    if uninstalled:
        console.print(f"\n[bold]{len(uninstalled)}[/bold] skill(s) not installed.")
        if install:
            for r in uninstalled:
                try:
                    from vibesop.installer.pack_installer import PackInstaller
                    installer = PackInstaller()
                    installer.install_skill_from_github(r.skill_id)
                    console.print(f"[green]\u2713[/green] Installed: {r.skill_id}")
                except Exception as e:
                    console.print(f"[red]\u2717[/red] {r.skill_id}: {e}")
        else:
            console.print("[dim]Run with --install to install all recommendations.[/dim]")


__all__ = ["recommended"]
