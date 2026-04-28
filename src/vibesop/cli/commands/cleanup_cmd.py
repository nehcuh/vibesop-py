"""Interactive skill cleanup — review and remove low-quality/stale skills.

Usage:
    vibe skills cleanup           Interactive cleanup
    vibe skills cleanup --auto    Apply all suggested actions
    vibe skills cleanup --dry-run Preview without changes
"""

from __future__ import annotations

from pathlib import Path

import questionary
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def _run_feedback_analysis(project_root: Path) -> dict:
    """Run feedback analysis and return categorized suggestions."""
    from vibesop.core.skills.feedback_loop import FeedbackLoop

    loop = FeedbackLoop(project_root=project_root)
    suggestions = loop.analyze_all(auto_deprecate=False)

    to_deprecate = [s for s in suggestions if s.action == "deprecate"]
    to_archive = [s for s in suggestions if s.action == "archive"]
    to_warn = [s for s in suggestions if s.action == "warn"]

    return {
        "loop": loop,
        "deprecate": to_deprecate,
        "archive": to_archive,
        "warn": to_warn,
        "total": len(suggestions),
    }


def _render_cleanup_table(
    deprecate: list,
    archive: list,
    warn: list,
) -> Table:
    """Render a table of skills needing attention."""
    table = Table(title="Skills Needing Attention", show_header=True)
    table.add_column("#", style="dim", justify="right", width=3)
    table.add_column("Skill ID", style="cyan")
    table.add_column("Action", style="bold")
    table.add_column("Grade", justify="center", width=6)
    table.add_column("Quality", justify="right", width=8)
    table.add_column("Unused", justify="right", width=8)
    table.add_column("Reason", style="dim")

    idx = 0
    action_styles = {
        "deprecate": ("[red]DEPRECATE[/red]",),
        "archive": ("[red]ARCHIVE[/red]",),
        "warn": ("[yellow]WARN[/yellow]",),
    }

    for s in archive:
        idx += 1
        label = action_styles.get(s.action, (s.action.upper(),))[0]
        days = f"{s.days_since_last_use}d" if s.days_since_last_use else "?"
        table.add_row(
            str(idx), s.skill_id, label, s.grade,
            f"{s.quality_score:.0%}", days, s.reason[:60],
        )

    for s in deprecate:
        idx += 1
        label = action_styles.get(s.action, (s.action.upper(),))[0]
        days = f"{s.days_since_last_use}d" if s.days_since_last_use else "?"
        table.add_row(
            str(idx), s.skill_id, label, s.grade,
            f"{s.quality_score:.0%}", days, s.reason[:60],
        )

    for s in warn:
        idx += 1
        label = action_styles.get(s.action, (s.action.upper(),))[0]
        days = f"{s.days_since_last_use}d" if s.days_since_last_use else "?"
        table.add_row(
            str(idx), s.skill_id, label, s.grade,
            f"{s.quality_score:.0%}", days, s.reason[:60],
        )

    return table


def cleanup(
    auto: bool = typer.Option(
        False, "--auto", "-a", help="Apply all suggested deprecations and archives automatically"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-n", help="Preview what would be cleaned without making changes"
    ),
) -> None:
    """Interactively review and clean up low-quality or stale skills.

    Analyzes your skill ecosystem for skills that:
      - Have F-grade quality scores (auto-deprecation candidates)
      - Have been unused for 90+ days (auto-archive candidates)
      - Have D-grade quality scores (review candidates)

    Use --auto to skip interaction and apply all suggestions.
    Use --dry-run to preview without making changes.

    Examples:
        vibe skills cleanup               # Interactive review
        vibe skills cleanup --auto        # Apply all suggestions
        vibe skills cleanup --dry-run     # Preview only
    """
    project_root = Path.cwd()

    console.print()
    console.print("[bold cyan]Analyzing skill ecosystem...[/bold cyan]")

    analysis = _run_feedback_analysis(project_root)
    deprecate = analysis["deprecate"]
    archive = analysis["archive"]
    warn = analysis["warn"]
    all_needing_attention = archive + deprecate + warn

    if not all_needing_attention:
        console.print()
        console.print(Panel(
            "[green]Your skill ecosystem is healthy![/green]\n"
            "No low-quality or stale skills detected.",
            title="Skills Cleanup",
            border_style="green",
        ))
        console.print()
        return

    table = _render_cleanup_table(deprecate, archive, warn)
    console.print()
    console.print(table)

    # Summary
    summary_parts = []
    if archive:
        summary_parts.append(f"[red]{len(archive)} to archive[/red]")
    if deprecate:
        summary_parts.append(f"[red]{len(deprecate)} to deprecate[/red]")
    if warn:
        summary_parts.append(f"[yellow]{len(warn)} to review[/yellow]")
    console.print(f"\n[bold]Found:[/bold] {', '.join(summary_parts)}")
    console.print()

    if dry_run:
        console.print("[dim]Dry run — no changes made. Remove --dry-run to apply actions.[/dim]")
        console.print()
        return

    # Auto mode: apply all
    if auto:
        loop = analysis["loop"]
        applied = 0
        for s in archive:
            loop._apply_archive(s.skill_id, s.reason)
            console.print(f"  [dim]Archived:[/dim] {s.skill_id}")
            applied += 1
        for s in deprecate:
            loop._apply_deprecation(s.skill_id, s.reason)
            console.print(f"  [dim]Deprecated:[/dim] {s.skill_id}")
            applied += 1
        console.print(f"\n[green]Applied {applied} action(s).[/green]")
        console.print()
        return

    # Interactive mode: checkbox selection
    choices = []
    for s in archive:
        days = f"({s.days_since_last_use}d unused)" if s.days_since_last_use else ""
        choices.append(
            questionary.Choice(
                title=f"[red]ARCHIVE[/red]  {s.skill_id}  "
                      f"grade={s.grade}  quality={s.quality_score:.0%}  {days}",
                value=("archive", s.skill_id),
            )
        )
    for s in deprecate:
        days = f"({s.days_since_last_use}d unused)" if s.days_since_last_use else ""
        choices.append(
            questionary.Choice(
                title=f"[red]DEPRECATE[/red]  {s.skill_id}  "
                      f"grade={s.grade}  quality={s.quality_score:.0%}  {days}",
                value=("deprecate", s.skill_id),
            )
        )

    if not choices:
        console.print("[dim]Only warnings found — no automated actions available.[/dim]")
        if warn:
            console.print("[dim]Use [cyan]vibe skill stale[/cyan] to review warnings in detail.[/dim]")
        console.print()
        return

    selected = questionary.checkbox(
        "Select skills to clean up (space to select, enter to confirm):",
        choices=choices,
    ).ask()

    if selected is None or len(selected) == 0:
        console.print("[dim]No skills selected. Nothing changed.[/dim]")
        console.print()
        return

    # Confirm and apply
    console.print()
    confirmed = questionary.confirm(
        f"Apply actions to {len(selected)} skill(s)?", default=True
    ).ask()

    if not confirmed:
        console.print("[dim]Cancelled. No changes made.[/dim]")
        console.print()
        return

    loop = analysis["loop"]
    for action, skill_id in selected:
        if action == "archive":
            loop._apply_archive(skill_id, "User-initiated cleanup")
            console.print(f"  [dim]Archived:[/dim] {skill_id}")
        elif action == "deprecate":
            loop._apply_deprecation(skill_id, "User-initiated cleanup")
            console.print(f"  [dim]Deprecated:[/dim] {skill_id}")

    console.print(f"\n[green]Cleaned up {len(selected)} skill(s).[/green]")
    console.print(
        "[dim]Tip: run [cyan]vibe status[/cyan] to see the updated ecosystem health.[/dim]"
    )
    console.print()
