"""Automatic session analysis for session-end integration.

This module provides non-interactive analysis that can be called
from hooks to automatically detect patterns and suggest improvements.
"""

from pathlib import Path

import typer
from rich.console import Console

from vibesop.core.session_analyzer import SessionAnalyzer

console = Console()


def auto_analyze_session(
    session_file: Path | None = typer.Argument(  # noqa: B008
        None,
        help="Session file to analyze",
        exists=True,
    ),
    min_frequency: int = typer.Option(
        3,
        "--min-frequency",
        "-f",
        help="Minimum times a pattern must appear",
    ),
    min_confidence: float = typer.Option(
        0.4,
        "--min-confidence",
        "-c",
        help="Minimum confidence threshold [0.0, 1.0]",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Minimal output (for hooks)",
    ),
) -> None:
    """Automatically analyze session and detect patterns (non-interactive).

    This command is designed to be called from hooks for automatic
    session analysis at session-end.

    \b
    Examples:
        # Auto-analyze current session
        vibe auto-analyze-session session.jsonl

        # Quiet mode (for hooks)
        vibe auto-analyze-session session.jsonl --quiet

        # Custom thresholds
        vibe auto-analyze-session session.jsonl --min-frequency 5 --min-confidence 0.6
    """
    if not session_file:
        if not quiet:
            console.print("[yellow]No session file provided[/yellow]")
        return

    analyzer = SessionAnalyzer(
        min_frequency=min_frequency,
        min_confidence=min_confidence,
    )

    # Analyze session
    suggestions = analyzer.analyze_session_file(session_file)

    if not suggestions:
        if not quiet:
            console.print("[dim]No patterns detected[/dim]")
        return

    # Filter to high-value suggestions
    high_value = [s for s in suggestions if s.estimated_value in ("high", "medium")]

    if not high_value:
        if not quiet:
            console.print(
                f"[dim]Found {len(suggestions)} low-value patterns "
                f"(need {min_frequency}+ occurrences for high-value)[/dim]"
            )
        return

    # Display suggestions
    if not quiet:
        console.print(
            f"\n[bold cyan]💡 Session Analysis[/bold cyan]"
            f"\nFound {len(high_value)} skill creation opportunities\n"
        )

        for i, suggestion in enumerate(high_value, 1):
            console.print(
                f"[cyan]{i}.[/cyan] {suggestion.skill_name}\n"
                f"   [dim]Frequency:[/dim] {suggestion.frequency} queries  "
                f"[dim]Value:[/dim] {suggestion.estimated_value}\n"
                f"   [dim]Example:[/dim] {suggestion.trigger_queries[0][:50]}...\n"
            )

        console.print(
            f"\n[dim]To create these skills, run:[/dim]\n"
            f"  [cyan]vibe analyze suggestions {session_file} --auto-craft[/cyan]\n"
        )
    else:
        # Quiet mode: just output count
        console.print(f"[VibeSOP] Found {len(high_value)} skill creation opportunities")


def create_suggested_skills(
    session_file: Path = typer.Argument(  # noqa: B008
        ...,
        help="Session file to analyze",
        exists=True,
    ),
    min_frequency: int = typer.Option(
        3,
        "--min-frequency",
        "-f",
        help="Minimum times a pattern must appear",
    ),
    min_confidence: float = typer.Option(
        0.4,
        "--min-confidence",
        "-c",
        help="Minimum confidence threshold [0.0, 1.0]",
    ),
) -> None:
    """Automatically create skills from detected patterns.

    This is a non-interactive version of --auto-craft that can be
    called from scripts or hooks.

    \b
    Examples:
        # Auto-create from session
        vibe create-suggested-skills session.jsonl

        # With custom thresholds
        vibe create-suggested-skills session.jsonl --min-frequency 5
    """
    analyzer = SessionAnalyzer(
        min_frequency=min_frequency,
        min_confidence=min_confidence,
    )

    # Analyze session
    suggestions = analyzer.analyze_session_file(session_file)

    if not suggestions:
        console.print("[yellow]No patterns detected[/yellow]")
        raise typer.Exit(0)

    # Filter to high-value suggestions
    high_value = [s for s in suggestions if s.estimated_value in ("high", "medium")]

    if not high_value:
        console.print(
            f"[yellow]No high-value patterns found[/yellow]\n"
            f"[dim]Found {len(suggestions)} low-value patterns "
            f"(increase --min-frequency or lower --min-confidence)[/dim]"
        )
        raise typer.Exit(0)

    # Create skills
    from vibesop.cli.commands.analyze import _auto_create_skills

    _auto_create_skills(high_value)

    console.print(
        f"\n[green]✓ Created {len(high_value)} skills[/green]\n"
        f"[dim]Run [cyan]vibe build[/cyan] to include them in your configuration.[/dim]"
    )
