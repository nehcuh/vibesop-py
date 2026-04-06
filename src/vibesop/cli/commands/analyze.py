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

import typer
from rich.console import Console
from rich.panel import Panel

from vibesop.core.ai_enhancer import EnhancedSkill
from vibesop.core.session_analyzer import SessionAnalyzer, SkillSuggestion

console = Console()


def analyze(
    action: str = typer.Argument(..., help="Action: session, patterns, suggestions"),
    source: Path | None = typer.Argument(  # noqa: B008
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
    use_ai: bool = typer.Option(
        False,
        "--ai",
        help="Use AI to enhance skill names and descriptions",
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

        # Use AI to enhance suggestions
        vibe analyze suggestions --ai

        # Auto-create AI-enhanced skills
        vibe analyze suggestions --ai --auto-craft
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
        _do_suggest_skills(analyzer, source, auto_craft, use_ai)
    else:
        console.print(
            f"[red]✗ Unknown action: {action}[/red]\n"
            f"[dim]Valid actions: session, patterns, suggestions[/dim]"
        )
        raise typer.Exit(1)


def _do_analyze_session(
    analyzer: SessionAnalyzer,
    source: Path | None,
) -> None:
    """Analyze a session file.

    Args:
        analyzer: SessionAnalyzer instance
        source: Session file path
    """
    console.print(f"\n[bold cyan]🔍 Session Analysis[/bold cyan]\n{'=' * 40}\n")

    # Find session file
    session_file = source or _find_current_session()

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
    source: Path | None,
) -> None:
    """Analyze patterns across multiple sessions.

    Args:
        analyzer: SessionAnalyzer instance
        source: Session directory
    """
    console.print(f"\n[bold cyan]📊 Pattern Analysis[/bold cyan]\n{'=' * 40}\n")

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
    all_suggestions: list[SkillSuggestion] = []
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
    source: Path | None,
    auto_craft: bool,
    use_ai: bool = False,
) -> None:
    """Generate and optionally create skill suggestions.

    Args:
        analyzer: SessionAnalyzer instance
        source: Session file or directory
        auto_craft: Whether to auto-create skills
        use_ai: Whether to use AI for enhancement
    """
    console.print(f"\n[bold cyan]💡 Skill Suggestions[/bold cyan]\n{'=' * 40}\n")

    # Analyze session
    suggestions: list[SkillSuggestion]
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
    high_value: list[SkillSuggestion] = [
        s for s in suggestions if s.estimated_value in ("high", "medium")
    ]
    to_display: list[SkillSuggestion | EnhancedSkill] = (
        list(high_value) if high_value else list(suggestions)
    )  # type: ignore[assignment]

    # Apply AI enhancement if requested
    if use_ai:
        console.print("[dim]🤖 Using AI to enhance suggestions...[/dim]\n")
        to_display = _ai_enhance_suggestions(to_display)  # type: ignore[reportArgumentType]
        console.print("[green]✓ AI enhancement complete[/green]\n")

    console.print(f"[green]Generated {len(to_display)} suggestions[/green]\n")

    if auto_craft:
        _auto_create_enhanced_skills(to_display)
    else:
        _display_enhanced_suggestions(to_display)
        console.print(
            "\n[dim]To auto-create these skills, run:[/dim]\n"
            "  [cyan]vibe analyze suggestions --auto-craft[/cyan]"
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
) -> list[SkillSuggestion]:
    """Analyze all session files in a directory."""
    all_suggestions: list[SkillSuggestion] = []

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
    created = 0

    for suggestion in suggestions:
        # Create all suggested skills (not just high/medium value)

        console.print(f"\n[cyan]Creating skill:[/cyan] {suggestion.skill_name}")

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


def _ai_enhance_suggestions(
    suggestions: list[SkillSuggestion],
) -> list[EnhancedSkill]:
    """Enhance skill suggestions using AI.

    Args:
        suggestions: List of skill suggestions

    Returns:
        List of enhanced skills
    """
    from vibesop.core.ai_enhancer import AIEnhancer

    enhancer = AIEnhancer()

    try:
        enhanced = enhancer.enhance_batch(suggestions)
        return enhanced
    except Exception as e:
        console.print(f"[yellow]AI enhancement failed: {e}[/yellow]")
        console.print("[dim]Using basic enhancement instead[/dim]\n")
        return []


def _display_enhanced_suggestions(
    enhanced_skills: list[SkillSuggestion | EnhancedSkill],
) -> None:
    """Display AI-enhanced skill suggestions.

    Args:
        enhanced_skills: List of enhanced skills
    """
    for i, enhanced in enumerate(enhanced_skills, 1):
        if isinstance(enhanced, EnhancedSkill):
            # Enhanced skill
            value_color = {
                "high": "green",
                "medium": "yellow",
                "low": "dim",
            }.get(enhanced.original.estimated_value, "dim")

            console.print(
                Panel(
                    f"[bold cyan]🤖 AI-Enhanced {i}. {enhanced.name}[/bold cyan]\n\n"
                    f"[dim]Category:[/dim] {enhanced.category}\n"
                    f"[dim]Description:[/dim] {enhanced.description}\n\n"
                    f"[dim]Frequency:[/dim] {enhanced.original.frequency} queries  "
                    f"[dim]Confidence:[/dim] {enhanced.original.confidence:.0%}  "
                    f"[dim]AI Confidence:[/dim] {enhanced.confidence:.0%}  "
                    f"[dim]Value:[/dim] [{value_color}]{enhanced.original.estimated_value}[/{value_color}]\n\n"
                    f"[dim]Tags:[/dim] {', '.join(enhanced.tags[:5])}\n\n"
                    f"[dim]Trigger Conditions:[/dim]\n"
                    + "\n".join(f"  • {cond}" for cond in enhanced.trigger_conditions[:3])
                    + "\n\n"
                    "[dim]Example queries:[/dim]\n"
                    + "\n".join(f"  • {q[:60]}..." for q in enhanced.original.trigger_queries[:3]),
                    title=f"[bold]AI-Enhanced Suggestion {i}[/bold]",
                    border_style="cyan" if enhanced.confidence > 0.7 else "blue",
                )
            )
        else:
            # Original skill (fallback)
            _display_suggestions([enhanced])

        console.print()


def _auto_create_enhanced_skills(
    enhanced_skills: list[SkillSuggestion | EnhancedSkill],
) -> None:
    """Auto-create enhanced skills with better content.

    Args:
        enhanced_skills: List of enhanced skills
    """
    created = 0

    for enhanced in enhanced_skills:
        if isinstance(enhanced, SkillSuggestion):
            # Use original auto-create
            _auto_create_skills([enhanced])
            return

        # enhanced is now narrowed to EnhancedSkill
        # Filter by value
        if enhanced.original.estimated_value not in ("high", "medium"):
            continue

        console.print(f"\n[cyan]Creating AI-enhanced skill:[/cyan] {enhanced.name}")

        # Generate enhanced skill content
        skill_content = f"""# {enhanced.name}

{enhanced.description}

## Category

{enhanced.category}

## Trigger When

{chr(10).join(f"- {cond}" for cond in enhanced.trigger_conditions)}

## Tags

{", ".join(enhanced.tags)}

## Steps

{chr(10).join(f"{i + 1}. {step}" for i, step in enumerate(enhanced.steps))}

## Examples

### Example 1

**User**: {enhanced.original.trigger_queries[0] if enhanced.original.trigger_queries else "help me"}

**Action**: {enhanced.steps[0] if enhanced.steps else "Assist the user"}

---

*AI-Enhanced by VibeSOP*
*Based on {enhanced.original.frequency} similar queries*
*AI Confidence: {enhanced.confidence:.0%}*
"""

        # Write skill file
        output_dir = Path(".vibe/skills")
        output_dir.mkdir(parents=True, exist_ok=True)

        # Create safe filename
        safe_name = enhanced.name.lower().replace(" ", "-").replace("/", "-")
        skill_file = output_dir / f"{safe_name}.md"
        skill_file.write_text(skill_content)

        console.print(f"[green]✓ Created:[/green] {skill_file}")
        created += 1

    if created > 0:
        console.print(
            f"\n[green]✓ Created {created} AI-enhanced skills[/green]"
            f"\n[dim]Run [cyan]vibe build[/cyan] to include them in your configuration.[/dim]"
        )
    else:
        console.print("[yellow]No skills created[/yellow]")
