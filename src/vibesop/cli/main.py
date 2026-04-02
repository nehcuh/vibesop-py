"""VibeSOP CLI - Main entry point.

Built with Typer for modern CLI UX.
"""

import importlib.util
import os
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from vibesop import __version__
from vibesop.core.models import RoutingRequest
from vibesop.core.routing.engine import SkillRouter
from vibesop.core.skills import SkillManager

app = typer.Typer(
    name="vibe",
    help="VibeSOP - AI-powered workflow SOP",
    no_args_is_help=True,
)
console = Console()


@app.command()
def route(
    query: str = typer.Argument(..., help="Natural language query to route"),
    json_output: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Output as JSON",
    ),
) -> None:
    """Route a query to the appropriate skill using AI-powered routing.

    Example:
        vibe route "帮我评审代码"
        vibe route "debug this error" --json
    """
    router = SkillRouter()

    # Create routing request
    request = RoutingRequest(query=query)

    # Route the request
    result = router.route(request)

    # Output
    if json_output:
        console.print_json(result.model_dump_json(indent=2))
    else:
        console.print(
            Panel(
                f"[bold green]✅ Matched:[/bold green] {result.primary.skill_id}\n"
                f"[dim]Confidence:[/dim] {result.primary.confidence:.0%}\n"
                f"[dim]Layer:[/dim] {result.primary.layer}\n"
                f"[dim]Source:[/dim] {result.primary.source}",
                title="[bold]Routing Result[/bold]",
                border_style="blue",
            )
        )

        if result.alternatives:
            console.print("\n[bold]💡 Alternatives:[/bold]")
            for alt in result.alternatives[:3]:
                console.print(f"  • {alt.skill_id} ({alt.confidence:.0%})")


@app.command()
def doctor() -> None:
    """Check environment and configuration.

    Example:
        vibe doctor
    """
    console.print("[bold]🔍 Checking VibeSOP environment...[/bold]\n")

    checks = [
        ("Python version", _check_python_version()),
        ("Dependencies", _check_dependencies()),
        ("Configuration", _check_config()),
        ("LLM Provider", _check_llm_provider()),
    ]

    for name, (status, message) in checks:
        icon = "✅" if status else "❌"
        color = "green" if status else "red"
        console.print(f"{icon} [{color}]{name}[/{color}]: {message}")

    # Overall status
    all_ok = all(status for status, _ in checks)
    if all_ok:
        console.print("\n[bold green]✨ All checks passed![/bold green]")
        raise typer.Exit(0)
    else:
        console.print("\n[bold red]⚠️  Some checks failed. Please fix the issues above.[/bold red]")
        raise typer.Exit(1)


@app.command()
def version() -> None:
    """Show version information.

    Example:
        vibe version
    """
    console.print(
        Panel(
            f"[bold]VibeSOP[/bold] Python Edition\n\n"
            f"Version: {__version__}\n"
            f"Python: 3.12+\n"
            f"Pydantic: v2",
            title="[bold]Version Information[/bold]",
            border_style="blue",
        )
    )


def _check_python_version() -> tuple[bool, str]:
    """Check Python version."""
    version = sys.version_info
    if version >= (3, 12):
        return True, f"{version.major}.{version.minor}.{version.micro}"
    return False, f"{version.major}.{version.minor} (requires 3.12+)"


def _check_dependencies() -> tuple[bool, str]:
    """Check if dependencies are installed."""

    missing = []
    for module in ("pydantic", "typer", "rich"):
        if importlib.util.find_spec(module) is None:
            missing.append(module)

    if missing:
        return False, f"Missing: {', '.join(missing)}"
    return True, "All dependencies installed"


def _check_config() -> tuple[bool, str]:
    """Check configuration."""
    config_dir = Path.cwd() / ".vibe"
    if config_dir.exists():
        return True, f"Found at {config_dir}"
    return False, "No .vibe directory found"


def _check_llm_provider() -> tuple[bool, str]:
    """Check LLM provider configuration."""
    if os.getenv("ANTHROPIC_API_KEY"):
        return True, "Anthropic (API key found)"
    if os.getenv("OPENAI_API_KEY"):
        return True, "OpenAI (API key found)"
    return False, "No API key found (set ANTHROPIC_API_KEY or OPENAI_API_KEY)"


@app.command()
def record(
    skill_id: str = typer.Argument(..., help="Skill ID that was selected"),
    query: str = typer.Argument(..., help="Original user query"),
    helpful: bool = typer.Option(True, "--helpful/--not-helpful", "-h/-H"),
) -> None:
    """Record a skill selection for preference learning.

    Example:
        vibe record /review "review my code"
        vibe record systematic-debugging "debug this error" --not-helpful
    """
    router = SkillRouter()

    router.record_selection(skill_id, query, was_helpful=helpful)

    if helpful:
        console.print(f"[green]✓[/green] Recorded selection: [bold]{skill_id}[/bold]")
    else:
        console.print(
            f"[yellow]✓[/yellow] Recorded selection: [bold]{skill_id}[/bold] (not helpful)"
        )

    # Show updated preference score
    score = router._preference_learner.get_preference_score(skill_id)
    if score > 0:
        console.print(f"   Preference score: {score:.2%}")
    console.print("   This will improve future recommendations.")


@app.command("preferences")
def preferences() -> None:
    """Show preference learning statistics.

    Example:
        vibe preferences
    """
    router = SkillRouter()
    stats = router.get_preference_stats()

    console.print("[bold]📊 Preference Learning Statistics[/bold]\n")

    console.print(f"Total selections: {stats['total_selections']}")
    console.print(f"Helpful rate: {stats['helpful_rate']:.1%}")
    console.print(f"Unique skills: {stats['unique_skills']}")

    if stats["top_skills"]:
        console.print("\n[bold]Top Skills:[/bold]")
        for skill_id, count in stats["top_skills"][:5]:
            console.print(f"  • {skill_id}: {count} selections")

    console.print(f"\nStorage: {stats['storage_path']}")


@app.command("top-skills")
def top_skills(
    limit: int = typer.Option(5, "--limit", "-l", min=1, max=10),
) -> None:
    """Show most preferred skills.

    Example:
        vibe top-skills
        vibe top-skills --limit 10
    """
    router = SkillRouter()
    top_skills = router.get_top_skills(limit=limit, min_selections=1)

    console.print(f"[bold]🏆 Top {len(top_skills)} Preferred Skills[/bold]\n")

    for i, pref in enumerate(top_skills, 1):
        # Create a nice display
        bar_length = int(pref.score * 20)
        bar = "█" * bar_length + "░" * (20 - bar_length)

        console.print(
            f"{i}. [bold cyan]{pref.skill_id}[/bold cyan]\n"
            f"   Score: [green]{pref.score:.1%}[/green]  "
            f"[dim]{bar}[/dim]\n"
            f"   Selected: {pref.selection_count}x  "
            f"Helpful: {pref.helpful_count}x"
        )


@app.command("skills")
def skills_list(
    namespace: str | None = typer.Option(None, "--namespace", "-n", help="Filter by namespace"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed information"),
) -> None:
    """List all available skills.

    Example:
        vibe skills
        vibe skills --namespace gstack
        vibe skills --verbose
    """
    manager = SkillManager()

    all_skills = manager.list_skills(namespace=namespace)

    if not all_skills:
        console.print("[yellow]No skills found.[/yellow]")
        raise typer.Exit(0)

    console.print(f"[bold]📚 Available Skills[/bold] ({len(all_skills)} total)\n")

    # Group by namespace
    by_namespace: dict[str, list[dict]] = {}
    for skill in all_skills:
        ns = skill.get("namespace", "builtin")
        if ns not in by_namespace:
            by_namespace[ns] = []
        by_namespace[ns].append(skill)

    for ns in sorted(by_namespace.keys()):
        ns_skills = by_namespace[ns]
        console.print(f"[bold cyan]{ns}[/bold cyan] ({len(ns_skills)} skills)")

        for skill in ns_skills:
            skill_id = skill.get("id", "unknown")
            name = skill.get("name", skill_id)
            desc = skill.get("description", "")
            skill_type = skill.get("type", "prompt")

            if verbose:
                console.print(
                    f"  • [bold]{skill_id}[/bold] ([dim]{skill_type}[/dim])\n"
                    f"    Name: {name}\n"
                    f"    Description: {desc}\n"
                    f"    Tags: {skill.get('tags', [])}\n"
                    f"    Source: {skill.get('source', 'unknown')}"
                )
            else:
                console.print(f"  • [bold]{skill_id}[/bold] - {desc}")

        console.print()  # Blank line between namespaces

    # Show stats
    stats = manager.get_stats()
    console.print(f"[dim]Namespaces: {', '.join(stats['namespaces'])}[/dim]")


@app.command("skill-info")
def skill_info(
    skill_id: str = typer.Argument(..., help="Skill ID (e.g., gstack/review)"),
) -> None:
    """Show detailed information about a skill.

    Example:
        vibe skill-info gstack/review
    """
    manager = SkillManager()

    info = manager.get_skill_info(skill_id)

    if not info:
        console.print(f"[red]Skill not found: {skill_id}[/red]")
        raise typer.Exit(1)

    console.print(
        Panel.fit(
            f"[bold]{info.get('name', info['id'])}[/bold]\n\n"
            f"[dim]ID:[/dim] {info['id']}\n"
            f"[dim]Type:[/dim] {info.get('type', 'prompt')}\n"
            f"[dim]Namespace:[/dim] {info.get('namespace', 'builtin')}\n"
            f"[dim]Version:[/dim] {info.get('version', '1.0.0')}\n"
            f"[dim]Author:[/dim] {info.get('author', 'N/A')}\n"
            f"[dim]Source:[/dim] {info.get('source', 'unknown')}\n"
            f"\n"
            f"[bold]Description[/bold]\n"
            f"{info.get('description', 'No description')}\n"
            f"\n"
            f"[bold]Intent[/bold]\n"
            f"{info.get('intent', 'No intent specified')}\n"
            f"\n"
            f"[bold]Tags[/bold]\n"
            f"{', '.join(info.get('tags') or []) or 'None'}",
            title="[bold]Skill Info[/bold]",
            border_style="blue",
        )
    )

    if info.get("source_file"):
        console.print(f"\n[dim]Source file: {info['source_file']}[/dim]")


if __name__ == "__main__":
    app()
