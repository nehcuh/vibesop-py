"""VibeSOP CLI - Main entry point.

Built with Typer for modern CLI UX.

Note: v4.1.0 removed the `execute` command and `--run` flag from `route`.
Skills should be executed by AI Agents (Claude Code, OpenCode), not VibeSOP.
VibeSOP is a routing engine, not an executor.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

import questionary
import typer
from rich.console import Console
from rich.panel import Panel

from vibesop import __version__
from vibesop.cli.routing_report import render_compact_report, render_routing_report
from vibesop.cli.subcommands import register
from vibesop.core.routing import UnifiedRouter

app = typer.Typer(
    name="vibe",
    help="VibeSOP - AI-powered workflow SOP",
    no_args_is_help=True,
)
console = Console()


# -- Core routing commands --


@app.command()
def route(
    query: str = typer.Argument(..., help="Natural language query to route"),
    min_confidence: float | None = typer.Option(
        None,
        "--min-confidence",
        "-c",
        help="Minimum confidence threshold (0.0-1.0)",
    ),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
    validate: bool = typer.Option(False, "--validate", "-V", help="Validate routing configuration"),
    explain: bool = typer.Option(False, "--explain", "-e", help="Explain routing decision with per-layer details"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt (alias for confirmation_mode=never)"),
) -> None:
    """Route a query to the appropriate skill using unified routing.

    VibeSOP is a routing engine - it tells you which skill to use,
    but does not execute skills. Use your AI Agent (Claude Code, OpenCode)
    to execute the recommended skill.

    By default, VibeSOP asks for confirmation before selecting a skill.
    Set routing.confirmation_mode to 'never' for automatic selection,
    or use --yes to skip once.

    Use --explain to inspect the full routing decision tree.
    """
    from pathlib import Path

    from vibesop.core.routing import RoutingConfig, UnifiedRouter

    # Set up router with optional min_confidence override
    if min_confidence is not None:
        config = RoutingConfig(min_confidence=min_confidence)
        router = UnifiedRouter(project_root=Path.cwd(), config=config)
    else:
        router = UnifiedRouter(project_root=Path.cwd())

    result = router.route(query)

    # --explain mode: show full decision tree and exit
    if explain:
        render_routing_report(result, console=console)
        raise typer.Exit(0)

    # Determine if confirmation is needed
    confirmation_mode = router._config.confirmation_mode
    need_confirm = (
        not yes
        and not json_output
        and not validate
        and confirmation_mode != "never"
        and sys.stdin.isatty()
    )

    # ambiguous_only: only confirm when confidence is below auto_select_threshold
    if need_confirm and confirmation_mode == "ambiguous_only" and result.primary:
        if result.primary.confidence >= router._config.auto_select_threshold:
            need_confirm = False

    # Show decision report and ask for confirmation
    if need_confirm:
        render_routing_report(result, console=console)

        choices = [
            questionary.Choice("✅ Confirm selected skill", value="confirm"),
            questionary.Choice("🔀 Choose a different skill", value="alternative"),
            questionary.Choice("📝 Skip skill, use raw LLM", value="skip"),
        ]

        choice = questionary.select(
            "How would you like to proceed?",
            choices=choices,
        ).ask()

        if choice == "alternative" and result.alternatives:
            alt_choices = [
                questionary.Choice(
                    f"{alt.skill_id} ({alt.confidence:.0%} via {alt.layer.value})",
                    value=alt.skill_id,
                )
                for alt in result.alternatives[:5]
            ]
            alt_choices.append(questionary.Choice("↩️  Back", value="back"))
            alt_id = questionary.select("Select a skill:", choices=alt_choices).ask()

            if alt_id == "back":
                # Re-prompt (simplified: just confirm the original)
                pass
            elif alt_id:
                # Update primary to selected alternative
                for alt in result.alternatives:
                    if alt.skill_id == alt_id:
                        result.primary = alt
                        break
        elif choice == "skip":
            result.primary = None  # Signal: no skill selected

    # Output result
    if json_output:
        import json

        console.print(json.dumps(result.to_dict(), indent=2))
    elif result.primary is not None:
        primary = result.primary
        console.print(
            Panel(
                f"[bold green]✅ Matched:[/bold green] {primary.skill_id}\n"
                f"[dim]Confidence:[/dim] {primary.confidence:.0%}\n"
                f"[dim]Layer:[/dim] {primary.layer.value}\n"
                f"[dim]Source:[/dim] {primary.source}\n"
                f"[dim]Duration:[/dim] {result.duration_ms:.1f}ms",
                title="[bold]Routing Result[/bold]",
                border_style="blue",
            )
        )
        if result.alternatives:
            console.print("\n[bold]💡 Alternatives:[/bold]")
            for alt in result.alternatives[:3]:
                console.print(f"  • {alt.skill_id} ({alt.confidence:.0%})")
    else:
        console.print(
            Panel(
                f"[yellow]❓ No suitable match found[/yellow]\n\n"
                f"[dim]Query:[/dim] {query}\n"
                f"[dim]Routing path:[/dim] {' → '.join([layer.value for layer in result.routing_path])}\n\n"
                f"[dim]Try:[/dim]\n"
                f"  • Using more specific keywords\n"
                f"  • Lowering the threshold\n"
                f"  • Listing available skills",
                title="[bold]Routing Result[/bold]",
                border_style="yellow",
            )
        )

    # Handle validation mode (legacy, less detailed than --explain)
    if validate:
        console.print(f"\n[bold cyan]✓ Route Validation[/bold cyan]\n{'=' * 40}\n")

        # Show router capabilities
        caps = router.get_capabilities()
        console.print("[dim]Router capabilities:[/dim]")
        console.print(f"  Matchers: {len(caps['matchers'])}")
        for matcher_info in caps["matchers"]:
            console.print(f"    - {matcher_info['layer']}: {matcher_info['matcher']}")

        config = caps.get("config", {})
        console.print("\n[dim]Configuration:[/dim]")
        console.print(f"  min_confidence: {config.get('min_confidence', 0.3)}")
        console.print(f"  auto_select_threshold: {config.get('auto_select_threshold', 0.6)}")
        console.print(f"  enable_embedding: {config.get('enable_embedding', False)}")

        # Test the query
        console.print(f"\n[bold]Testing query:[/bold] {query}\n")
        if result.primary is not None:
            console.print(f"  Primary: {result.primary.skill_id} ({result.primary.confidence:.0%})")
            console.print(f"  Layer: {result.primary.layer.value}")
        else:
            console.print("  [yellow]No match found[/yellow]")

        if result.alternatives:
            console.print("\n[bold]Alternatives:[/bold]")
            for i, alt in enumerate(result.alternatives[:5], 1):
                console.print(f"  {i}. {alt.skill_id} - {alt.confidence:.0%}")

        console.print("\n[green]✓ Validation complete[/green]")
        raise typer.Exit(0)


@app.command()
def doctor() -> None:
    """Check environment and configuration."""
    console.print("[bold]🔍 Checking VibeSOP environment...[/bold]\n")

    checks = [
        ("Python version", _check_python_version()),
        ("Dependencies", _check_dependencies()),
        ("Configuration", _check_config()),
        ("LLM Provider", _check_llm_provider()),
        ("Platform Integrations", _check_integrations()),
        ("Hook Status", _check_hooks()),
        ("Skill Health", _check_skill_health()),
    ]

    for name, (status, message) in checks:
        icon = (
            "✅" if status else "⚠️ " if name in ["Platform Integrations", "Hook Status"] else "❌"
        )
        color = (
            "green"
            if status
            else "yellow"
            if name in ["Platform Integrations", "Hook Status"]
            else "red"
        )
        console.print(f"{icon} [{color}]{name}[/{color}]: {message}")

    all_ok = all(status for status, _ in checks)
    if all_ok:
        console.print("\n[bold green]✨ All checks passed![/bold green]")
        raise typer.Exit(0)
    else:
        console.print("\n[bold red]⚠️  Some checks failed. Please fix the issues above.[/bold red]")
        raise typer.Exit(1)


@app.command()
def version() -> None:
    """Show version information."""
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


@app.command()
def record(
    skill_id: str = typer.Argument(..., help="Skill ID that was selected"),
    query: str = typer.Argument(..., help="Original user query"),
    helpful: bool = typer.Option(True, "--helpful/--not-helpful", "-h/-H"),
) -> None:
    """Record a skill selection for preference learning."""
    router = UnifiedRouter()
    router.record_selection(skill_id, query, was_helpful=helpful)

    if helpful:
        console.print(f"[green]✓[/green] Recorded selection: [bold]{skill_id}[/bold]")
    else:
        console.print(
            f"[yellow]✓[/yellow] Recorded selection: [bold]{skill_id}[/bold] (not helpful)"
        )
    console.print("   This will improve future recommendations.")


@app.command("route-stats")
def route_stats() -> None:
    """Show routing statistics."""
    router = UnifiedRouter()
    stats = router.get_stats()

    console.print("[bold]📊 Routing Statistics[/bold]\n")
    total_routes = stats["total_routes"]
    console.print(f"Total routes: {total_routes}")

    if isinstance(total_routes, int) and total_routes > 0:
        console.print("\n[bold]Layer Distribution:[/bold]")
        layer_dist = stats["layer_distribution"]
        if isinstance(layer_dist, dict):
            for layer, count in layer_dist.items():
                pct = count / total_routes * 100
                console.print(f"  • {layer}: {count} ({pct:.0f}%)")

    console.print(f"\nCache: {stats.get('cache_dir', 'N/A')}")


@app.command("preferences")
def preferences() -> None:
    """Show preference learning statistics."""
    router = UnifiedRouter()
    stats = router.get_preference_stats()

    console.print("[bold]📊 Preference Learning Statistics[/bold]\n")
    console.print(f"Total selections: {stats['total_selections']}")
    console.print(f"Helpful rate: {stats['helpful_rate']:.1%}")
    console.print(f"Unique skills: {stats['unique_skills']}")

    top_skills = stats.get("top_skills")
    if isinstance(top_skills, list) and top_skills:
        console.print("\n[bold]Top Skills:[/bold]")
        for skill_id, count in top_skills[:5]:
            console.print(f"  • {skill_id}: {count} selections")

    console.print(f"\nStorage: {stats['storage_path']}")


@app.command("top-skills")
def top_skills(
    limit: int = typer.Option(5, "--limit", "-l", min=1, max=10),
) -> None:
    """Show most preferred skills."""
    router = UnifiedRouter()
    top = router.get_top_skills(limit=limit, min_selections=1)

    console.print(f"[bold]🏆 Top {len(top)} Preferred Skills[/bold]\n")
    for i, pref in enumerate(top, 1):
        bar_length = int(pref.score * 20)
        bar = "█" * bar_length + "░" * (20 - bar_length)
        console.print(
            f"{i}. [bold cyan]{pref.skill_id}[/bold cyan]\n"
            f"   Score: [green]{pref.score:.1%}[/green]  "
            f"[dim]{bar}[/dim]\n"
            f"   Selected: {pref.selection_count}x  "
            f"Helpful: {pref.helpful_count}x"
        )


# -- Health check helpers --


def _check_python_version() -> tuple[bool, str]:
    version = sys.version_info
    if version >= (3, 12):
        return True, f"{version.major}.{version.minor}.{version.micro}"
    return False, f"{version.major}.{version.minor} (requires 3.12+)"


def _check_dependencies() -> tuple[bool, str]:
    missing: list[str] = []
    for module in ("pydantic", "typer", "rich"):
        if importlib.util.find_spec(module) is None:
            missing.append(module)
    if missing:
        return False, f"Missing: {', '.join(missing)}"
    return True, "All dependencies installed"


def _check_config() -> tuple[bool, str]:
    config_dir = Path.cwd() / ".vibe"
    if config_dir.exists():
        return True, f"Found at {config_dir}"
    return False, "No .vibe directory found"


def _check_llm_provider() -> tuple[bool, str]:
    if os.getenv("ANTHROPIC_API_KEY"):
        return True, "Anthropic (API key found)"
    if os.getenv("OPENAI_API_KEY"):
        return True, "OpenAI (API key found)"
    if os.getenv("KIMI_API_KEY"):
        return True, "Kimi / Moonshot (API key found)"
    return False, "No API key found (set ANTHROPIC_API_KEY, OPENAI_API_KEY, or KIMI_API_KEY)"


def _check_integrations() -> tuple[bool, str]:
    try:
        from vibesop.integrations import IntegrationManager

        manager = IntegrationManager()
        installed = manager.get_installed_integrations()
        total = len(manager.list_integrations())
        if installed:
            names = [info.name for info in installed]
            return True, f"{len(installed)}/{total} installed ({', '.join(names)})"
        return False, f"No integrations installed (0/{total})"
    except Exception as e:
        return False, f"Failed to check: {e}"


def _check_skill_health() -> tuple[bool, str]:
    try:
        from vibesop.integrations.health_monitor import SkillHealthMonitor

        monitor = SkillHealthMonitor()
        summary = monitor.get_health_summary()
        total = summary.get("total", 0)
        healthy = summary.get("healthy", 0)
        critical = summary.get("critical", 0)
        total_skills = summary.get("total_skills", 0)

        if critical > 0:
            return False, f"{healthy}/{total} packs healthy, {critical} critical ({total_skills} skills)"
        if healthy == 0 and total == 0:
            return False, "No skill packs detected"
        return True, f"{healthy}/{total} packs healthy ({total_skills} skills)"
    except Exception as e:
        return False, f"Failed to check: {e}"


def _check_hooks() -> tuple[bool, str]:
    try:
        from vibesop.installer import VibeSOPInstaller

        installer = VibeSOPInstaller()
        platforms = installer.list_platforms()
        results: list[str] = []
        for platform_info in platforms:
            platform_name: str = platform_info["name"]
            verify_result: dict[str, Any] = installer.verify(platform_name)  # type: ignore[reportUnknownVariableType]
            if verify_result["installed"]:
                hooks_status: dict[str, Any] = verify_result.get("hooks_installed", {})
                hook_count = sum(1 for s in hooks_status.values() if s)
                total_hooks = len(hooks_status)
                results.append(f"{platform_name}: {hook_count}/{total_hooks}")
            else:
                results.append(f"{platform_name}: not installed")
        if results:
            return any("installed" not in r for r in results), "; ".join(results)
        return False, "No platforms checked"
    except Exception as e:
        return False, f"Failed to check: {e}"


# Register all subcommands
register(app)

if __name__ == "__main__":
    app()
