"""VibeSOP analyze command - Analyze sessions and suggest improvements.

This command analyzes session history to:
- Detect repeated patterns
- Suggest new skills to create
- Improve routing accuracy

Usage:
    vibe analyze session
    vibe analyze patterns
    vibe analyze suggestions
    vibe analyze --help
"""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from vibesop.core.session_analyzer import SessionAnalyzer, SkillSuggestion

console = Console()


def analyze(
    action: str = typer.Argument(..., help="Action: session, patterns, suggestions"),
    source: Optional[Path] = typer.Argument(
        None,
        help="Source session file or directory",
        exists=True,
    ),
    min_frequency: int = typer.Option(
        3,
        "--min-frequency",
        "-f",
        help="Minimum times a pattern must appear",
    ),
    min_confidence: float = typer.Option(
        0.7,
        "--min-confidence",
        "-c",
        help="Minimum confidence threshold [0.0, 1.0]",
    ),
    auto_craft: bool = typer.Option(
        False,
        "--auto-craft",
        "-a",
        help="Automatically create suggested skills",
    ),
) -> None:
    """Analyze sessions and suggest improvements.

    This command analyzes conversation history to find patterns
    and suggest new skills that could improve your workflow.

    \b
    Examples:
        # Analyze current session
        vibe analyze session

        # Analyze specific session file
        vibe analyze session session.jsonl

        # Generate skill suggestions
        vibe analyze suggestions

        # Auto-create suggested skills
        vibe analyze suggestions --auto-craft
    """
    analyzer = SessionAnalyzer(
        min_frequency=min_frequency,
        min_confidence=min_confidence,
    )

    if action == "session":
        _do_analyze_session(analyzer, source)
    elif action == "patterns":
        _do_analyze_patterns(analyzer, source)
    elif action == "suggestions":
        _do_suggest_skills(analyzer, source, auto_craft)
    else:
        console.print(
            f"[red]✗ Unknown action: {action}[/red]\n"
            f"[dim]Valid actions: session, patterns, suggestions[/dim]"
        )
        raise typer.Exit(1)


def _do_analyze_session(
    analyzer: SessionAnalyzer,
    source: Optional[Path],
) -> None:
    """Analyze a session file.

    Args:
        analyzer: SessionAnalyzer instance
        source: Session file path
    """
    console.print(
        f"\n[bold cyan]🔍 Session Analysis[/bold cyan]"
        f"\n{'=' * 40}\n"
    )

    # Find session file
    if source:
        session_file = source
    else:
        # Try to find current session
        session_file = _find_current_session()

    if not session_file or not session_file.exists():
        console.print("[yellow]No session file found[/yellow]")
        console.print("[dim]Run: vibe analyze session <path-to-session>[/dim]")
        return

    console.print(f"[dim]Analyzing: {session_file}[/dim]\n")

    # Analyze
    suggestions = analyzer.analyze_session_file(session_file)

    if not suggestions:
        console.print("[green]✓ No strong patterns detected[/green]")
        console.print("[dim]Your session doesn't show repeated patterns yet.[/dim]")
        return

    # Show summary
    console.print(f"[green]Found {len(suggestions)} potential skills[/green]\n")

    _display_suggestions(suggestions)


def _do_analyze_patterns(
    analyzer: SessionAnalyzer,
    source: Optional[Path],
) -> None:
    """Analyze patterns across multiple sessions.

    Args:
        analyzer: SessionAnalyzer instance
        source: Session directory
    """
    console.print(
        f"\n[bold cyan]📊 Pattern Analysis[/bold cyan]"
        f"\n{'=' * 40}\n"
    )

    if not source:
        # Use default session directory
        source = Path.cwd()

    # Find all session files
    session_files = list(source.glob("**/*.jsonl")) + list(source.glob("**/*.json"))

    if not session_files:
        console.print("[yellow]No session files found[/yellow]")
        return

    console.print(f"[dim]Found {len(session_files)} session files[/dim]\n")

    # Analyze each session
    all_suggestions = []
    for session_file in session_files[:10]:  # Limit to 10 sessions
        suggestions = analyzer.analyze_session_file(session_file)
        all_suggestions.extend(suggestions)

    if not all_suggestions:
        console.print("[green]✓ No strong patterns detected[/green]")
        return

    console.print(f"[green]Found {len(all_suggestions)} potential skills[/green]\n")

    _display_suggestions(all_suggestions[:10])  # Top 10


def _do_suggest_skills(
    analyzer: SessionAnalyzer,
    source: Optional[Path],
    auto_craft: bool,
) -> None:
    """Generate and optionally create skill suggestions.

    Args:
        analyzer: SessionAnalyzer instance
        source: Session file or directory
        auto_craft: Whether to auto-create skills
    """
    console.print(
        f"\n[bold cyan]💡 Skill Suggestions[/bold cyan]"
        f"\n{'=' * 40}\n"
    )

    # Analyze session
    if source and source.is_file():
        suggestions = analyzer.analyze_session_file(source)
    elif source:
        suggestions = _analyze_directory(analyzer, source)
    else:
        # Try current directory
        session_file = _find_current_session()
        if session_file and session_file.exists():
            suggestions = analyzer.analyze_session_file(session_file)
        else:
            suggestions = []

    if not suggestions:
        console.print("[yellow]No suggestions generated[/yellow]")
        console.print("[dim]Need more session data to detect patterns.[/dim]")
        return

    # Filter by value (but show all if none high/medium)
    high_value = [s for s in suggestions if s.estimated_value in ("high", "medium")]
    to_display = high_value if high_value else suggestions

    console.print(f"[green]Generated {len(to_display)} suggestions[/green]\n")

    if auto_craft:
        _auto_create_skills(to_display)
    else:
        _display_suggestions(to_display)
        console.print(
            f"\n[dim]To auto-create these skills, run:[/dim]\n"
            f"  [cyan]vibe analyze suggestions --auto-craft[/cyan]"
        )


def _find_current_session() -> Path | None:
    """Try to find current session file."""
    # Try Claude Code session location
    candidates = [
        Path.cwd() / ".claude" / "projects" / "*" / "*.jsonl",
        Path.cwd() / "session.jsonl",
        Path.cwd() / ".vibe" / "session.jsonl",
    ]

    for pattern in candidates:
        matches = list(Path.cwd().glob(str(pattern)))
        if matches:
            # Get most recent
            return max(matches, key=lambda p: p.stat().st_mtime)

    return None


def _analyze_directory(
    analyzer: SessionAnalyzer,
    directory: Path,
) -> list:
    """Analyze all session files in a directory."""
    all_suggestions = []

    for session_file in directory.glob("**/*.jsonl"):
        suggestions = analyzer.analyze_session_file(session_file)
        all_suggestions.extend(suggestions)

    return all_suggestions


def _display_suggestions(suggestions: list[SkillSuggestion]) -> None:
    """Display skill suggestions.

    Args:
        suggestions: List of skill suggestions
    """
    for i, suggestion in enumerate(suggestions, 1):
        # Value badge
        value_color = {
            "high": "green",
            "medium": "yellow",
            "low": "dim",
        }.get(suggestion.estimated_value, "dim")

        console.print(
            Panel(
                f"[bold]{i}. {suggestion.skill_name}[/bold]\n\n"
                f"[dim]Description:[/dim] {suggestion.description}\n\n"
                f"[dim]Frequency:[/dim] {suggestion.frequency} queries  "
                f"[dim]Confidence:[/dim] {suggestion.confidence:.0%}  "
                f"[dim]Value:[/dim] [{value_color}]{suggestion.estimated_value}[/{value_color}]\n\n"
                f"[dim]Example queries:[/dim]\n"
                + "\n".join(f"  • {q[:60]}..." for q in suggestion.trigger_queries),
                title=f"[bold]Skill Suggestion {i}[/bold]",
                border_style="cyan" if suggestion.estimated_value == "high" else "blue",
            )
        )
        console.print()


def _auto_create_skills(suggestions: list[SkillSuggestion]) -> None:
    """Automatically create suggested skills.

    Args:
        suggestions: List of skill suggestions
    """
    from vibesop.cli.commands.skill_craft import _do_create

    created = 0

    for suggestion in suggestions:
        # Create all suggested skills (not just high/medium value)

        console.print(
            f"\n[cyan]Creating skill:[/cyan] {suggestion.skill_name}"
        )

        # Create skill using skill-craft
        # Note: This is a simplified version
        # In real implementation, would generate better content
        skill_content = f"""# {suggestion.skill_name}

{suggestion.description}

## Trigger When

User asks for help with:
{chr(10).join(f"- {q}" for q in suggestion.trigger_queries[:3])}

## Steps

1. Understand the user's request
2. Analyze the context
3. Provide appropriate assistance

## Examples

### Example 1

**User**: {suggestion.trigger_queries[0] if suggestion.trigger_queries else "help me"}

**Action**: Assist the user

---

*Auto-generated by VibeSOP analyze*
*Based on {suggestion.frequency} similar queries*
"""

        # Write skill file
        output_dir = Path(".vibe/skills")
        output_dir.mkdir(parents=True, exist_ok=True)

        skill_file = output_dir / f"{suggestion.skill_name.lower().replace(' ', '-')}.md"
        skill_file.write_text(skill_content)

        console.print(f"[green]✓ Created:[/green] {skill_file}")
        created += 1

    if created > 0:
        console.print(
            f"\n[green]✓ Created {created} skills[/green]"
            f"\n[dim]Run [cyan]vibe build[/cyan] to include them in your configuration.[/dim]"
        )
    else:
        console.print("[yellow]No skills created[/yellow]")
