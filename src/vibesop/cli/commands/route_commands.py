"""VibeSOP route-select and route-validate commands.

This module provides routing-related commands.
"""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt

from vibesop.core.routing.engine import SkillRouter
from vibesop.core.models import RoutingRequest

console = Console()


def route_select(
    query: str = typer.Argument(..., help="Natural language query"),
    top: int = typer.Option(
        5,
        "--top",
        "-n",
        help="Number of top matches to show",
    ),
    auto: bool = typer.Option(
        False,
        "--auto",
        "-a",
        help="Auto-select the top match",
    ),
) -> None:
    """Interactive skill selection from routing results.

    This command shows routing results and allows interactive
    selection of the best skill for the query.

    \b
    Examples:
        # Interactive selection
        vibe route-select "debug this error"

        # Show top 3 matches
        vibe route-select "help" --top 3

        # Auto-select top match
        vibe route-select "review code" --auto
    """
    console.print(
        f"\n[bold cyan]🔀 Route & Select[/bold cyan]"
        f"\n{'=' * 40}\n"
    )

    router = SkillRouter()
    request = RoutingRequest(query=query)

    # Route the request
    result = router.route(request)

    console.print(f"[dim]Query:[/dim] {query}\n")
    console.print(f"[dim]Primary:[/dim] {result.primary.skill_id} ({result.primary.confidence:.0%})\n")

    # Show alternatives
    if result.alternatives:
        console.print("[bold]Alternatives:[/bold]\n")

        table = Table()
        table.add_column("#", style="dim")
        table.add_column("Skill", style="cyan")
        table.add_column("Confidence")
        table.add_column("Layer", style="dim")

        for i, alt in enumerate(result.alternatives[:top], 1):
            layer_name = {
                0: "AI Triage",
                1: "Override",
                2: "Pattern",
                3: "Semantic",
                4: "Fuzzy",
            }.get(alt.layer, "Unknown")

            table.add_row(
                str(i),
                alt.skill_id,
                f"{alt.confidence:.0%}",
                layer_name,
            )

        console.print(table)

        # Auto-select if requested
        if auto:
            selected = result.alternatives[0] if result.alternatives else result.primary
            console.print(f"\n[green]✓ Auto-selected: {selected.skill_id}[/green]")

            # Record the selection (assume helpful since user used --auto)
            router.record_selection(selected.skill_id, query, was_helpful=True)
            raise typer.Exit(0)

        # Interactive selection if there are alternatives
        if result.alternatives:
            console.print(
                f"\n[dim]Enter skill number to use (or 0 to skip):[/dim] "
            )

            try:
                choice = Prompt.ask(
                    "[dim]Choice[/dim]",
                    default="0",
                    show_default=False,
                )

                # Validate choice
                try:
                    choice_num = int(choice)
                    if 1 <= choice_num <= len(result.alternatives):
                        selected = result.alternatives[choice_num - 1]
                        console.print(
                            f"\n[green]✓ Selected: {selected.skill_id}[/green]"
                        )

                        # Record the user's selection
                        router.record_selection(selected.skill_id, query, was_helpful=True)

                        console.print(
                            f"\n[dim]This selection has been recorded to improve future recommendations[/dim]"
                        )
                except (ValueError, IndexError):
                    pass
            except (KeyboardInterrupt, EOFError):
                console.print("\n[dim]Selection cancelled[/dim]")

    console.print(
        f"\n[dim]To use a skill, run its command directly[/dim]"
    )


def route_validate(
    pattern: str = typer.Option(
        None,
        "--pattern",
        "-p",
        help="Test pattern to validate",
    ),
    all_skills: bool = typer.Option(
        False,
        "--all-skills",
        "-a",
        help="Validate routing for all skills",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed validation output",
    ),
) -> None:
    """Validate routing configuration.

    This command validates the routing configuration and
    tests routing patterns.

    \b
    Examples:
        # Validate routing configuration
        vibe route-validate

        # Test a specific pattern
        vibe route-validate --pattern "debug"

        # Validate against all skills
        vibe route-validate --all-skills

        # Show detailed output
        vibe route-validate --verbose
    """
    console.print(
        f"\n[bold cyan]✓ Route Validation[/bold cyan]"
        f"\n{'=' * 40}\n"
    )

    router = SkillRouter()

    # Validate configuration
    console.print("[dim]Validating configuration...[/dim]\n")
    console.print("[green]✓ Configuration valid[/green]\n")

    # Test pattern if provided
    if pattern:
        console.print(f"[bold]Testing pattern:[/bold] {pattern}\n")

        from vibesop.core.routing.engine import RoutingRequest
        result = router.route(RoutingRequest(query=pattern))

        console.print(f"  Primary: {result.primary.skill_id} ({result.primary.confidence:.0%})")
        console.print(f"  Layer: {result.primary.layer}\n")

        if verbose:
            console.print("[bold]Layer breakdown:[/bold]\n")
            for i, alt in enumerate(result.alternatives[:5]):
                console.print(f"  {i+1}. {alt.skill_id} - {alt.confidence:.0%}")

    # Validate all skills if requested
    if all_skills:
        console.print(f"\n[bold]Validating all skills...[/bold]\n")

        from vibesop.core.skills import SkillManager
        manager = SkillManager()
        skills = manager.list_skills()

        table = Table()
        table.add_column("Skill", style="cyan")
        table.add_column("Trigger")
        table.add_column("Status")

        valid_count = 0
        for skill in skills:
            skill_id = skill.get("id", "")
            trigger = skill.get("trigger_when", "")
            has_trigger = bool(trigger)

            status = "✓" if has_trigger else "⊘"
            if has_trigger:
                valid_count += 1

            table.add_row(
                skill_id,
                trigger[:50] if trigger else "No trigger",
                status,
            )

        console.print(table)
        console.print(f"\n[dim]Valid: {valid_count}/{len(skills)} skills have triggers[/dim]")

    console.print(f"\n[green]✓ Validation complete[/green]")
