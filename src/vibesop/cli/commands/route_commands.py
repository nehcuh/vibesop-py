"""VibeSOP route commands - Unified routing interface.

This module provides the unified routing command that replaces
vibe auto and vibe route from v2.x.
"""

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from vibesop.core.routing import UnifiedRouter

console = Console()


def route(
    query: str = typer.Argument(..., help="Natural language query"),
    top: int = typer.Option(
        3,
        "--top",
        "-n",
        help="Number of top matches to show",
    ),
    min_confidence: float = typer.Option(
        None,
        "--min-confidence",
        "-c",
        help="Minimum confidence threshold (0.0-1.0)",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Output results as JSON",
    ),
) -> None:
    """Route a query to the best matching skill.

    This is the unified routing command that replaces:
    - vibe auto (v2.x)
    - vibe route (v2.x)

    \b
    Examples:
        # Route to best matching skill
        vibe route "debug this error"

        # Show top 5 matches
        vibe route "help" --top 5

        # Set minimum confidence
        vibe route "review code" --min-confidence 0.5

        # Output as JSON
        vibe route "test this" --json
    """
    # Initialize router
    router = UnifiedRouter(project_root=Path.cwd())

    # Override min_confidence if specified
    if min_confidence is not None:
        from vibesop.core.config import RoutingConfig

        config = RoutingConfig(min_confidence=min_confidence)
        router = UnifiedRouter(project_root=Path.cwd(), config=config)

    # Route the query
    result = router.route(query)

    if json_output:
        import json

        console.print(json.dumps(result.to_dict(), indent=2))
        return

    # Display results
    console.print(f"\n[bold cyan]🔀 Route: {query}[/bold cyan]\n{'=' * 40}\n")

    if result.has_match:
        # Show primary match
        primary = result.primary
        console.print(f"[dim]Primary:[/dim] [bold green]{primary.skill_id}[/bold green]")
        console.print(f"[dim]Confidence:[/dim] {primary.confidence:.1%}")
        console.print(f"[dim]Layer:[/dim] {primary.layer.value}")
        console.print(f"[dim]Source:[/dim] {primary.source}")
        console.print(f"[dim]Duration:[/dim] {result.duration_ms:.1f}ms\n")

        # Show alternatives
        if result.alternatives:
            console.print("[bold]Alternatives:[/bold]\n")

            table = Table()
            table.add_column("#", style="dim")
            table.add_column("Skill", style="cyan")
            table.add_column("Confidence")
            table.add_column("Layer", style="dim")

            for i, alt in enumerate(result.alternatives[:top], 1):
                table.add_row(
                    str(i),
                    alt.skill_id,
                    f"{alt.confidence:.1%}",
                    alt.layer.value,
                )

            console.print(table)
    else:
        console.print("[yellow]No suitable match found[/yellow]")
        console.print(
            f"[dim]Routing path: {' → '.join([layer.value for layer in result.routing_path])}[/dim]"
        )
        console.print("\n[dim]Try:[/dim]")
        console.print("  [dim]- Lowering the threshold with --min-confidence[/dim]")
        console.print("  [dim]- Using more specific keywords[/dim]")
        console.print("  [dim]- Listing available skills with [cyan]vibe skills list[/cyan][/dim]")

    console.print()


# Legacy command aliases (deprecated)
def route_select(
    query: str = typer.Argument(..., help="Natural language query"),
    top: int = typer.Option(
        5,
        "--top",
        "-n",
        help="Number of top matches to show",
    ),
    _auto: bool = typer.Option(
        False,
        "--auto",
        "-a",
        help="Auto-select the top match",
    ),
) -> None:
    """[DEPRECATED] Use 'vibe route' instead.

    This command is deprecated and will be removed in v4.0.0.
    Use 'vibe route' for the same functionality.
    """
    import warnings

    warnings.warn(
        "route-select is deprecated. Use 'vibe route' instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    # Call route with the query and top parameter
    # Note: We duplicate logic here because calling route() directly
    # doesn't work within Typer's command context
    router = UnifiedRouter(project_root=Path.cwd())
    result = router.route(query)

    if result.has_match:
        console.print(f"\n[bold cyan]🔀 Route: {query}[/bold cyan]")
        console.print(f"[dim]Primary:[/dim] [bold green]{result.primary.skill_id}[/bold green]")
        console.print(f"[dim]Confidence:[/dim] {result.primary.confidence:.1%}\n")

        if result.alternatives and top > 1:
            console.print("[bold]Alternatives:[/bold]\n")
            table = Table()
            table.add_column("#", style="dim")
            table.add_column("Skill", style="cyan")
            table.add_column("Confidence")

            for i, alt in enumerate(result.alternatives[: top - 1], 1):
                table.add_row(str(i), alt.skill_id, f"{alt.confidence:.1%}")

            console.print(table)
    else:
        console.print("[yellow]No suitable match found[/yellow]")

    console.print()


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
    console.print(f"\n[bold cyan]✓ Route Validation[/bold cyan]\n{'=' * 40}\n")

    router = UnifiedRouter(project_root=Path.cwd())

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

    # Test pattern if provided
    if pattern:
        console.print(f"\n[bold]Testing pattern:[/bold] {pattern}\n")
        result = router.route(pattern)

        if result.has_match:
            console.print(f"  Primary: {result.primary.skill_id} ({result.primary.confidence:.0%})")
            console.print(f"  Layer: {result.primary.layer.value}")
        else:
            console.print("  [yellow]No match found[/yellow]")

        if verbose and result.alternatives:
            console.print("\n[bold]Alternatives:[/bold]")
            for i, alt in enumerate(result.alternatives[:5], 1):
                console.print(f"  {i}. {alt.skill_id} - {alt.confidence:.0%}")

    # Validate all skills if requested
    if all_skills:
        console.print("\n[bold]Validating all skills...[/bold]\n")

        from vibesop.core.skills import SkillManager

        manager = SkillManager()
        skills = manager.list_skills()

        table = Table()
        table.add_column("Skill", style="cyan")
        table.add_column("Description")
        table.add_column("Status")

        for skill in skills[:10]:  # Limit to 10 for display
            skill_id = skill.metadata.id
            description = skill.metadata.description[:50] if skill.metadata.description else ""
            status = "✓"

            table.add_row(
                skill_id,
                description,
                status,
            )

        if len(skills) > 10:
            console.print(table)
            console.print(f"\n[dim]... and {len(skills) - 10} more skills[/dim]")
        else:
            console.print(table)

    console.print("\n[green]✓ Validation complete[/green]")
