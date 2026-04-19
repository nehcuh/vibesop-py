"""VibeSOP feedback command - Collect and analyze routing feedback.

Usage:
    vibe feedback record <query> <skill> [--correct|--wrong <actual_skill>]
    vibe feedback report
    vibe feedback export <output_file>
    vibe feedback clear
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from vibesop.core.feedback import FeedbackCollector, get_feedback_report

console = Console()


def record(
    query: str = typer.Argument(..., help="User's query text"),
    skill: str = typer.Argument(..., help="Routed skill ID"),
    correct: bool = typer.Option(True, "--correct", "--wrong", help="Whether routing was correct"),
    actual_skill: str = typer.Option(None, help="Correct skill if routing was wrong"),
    confidence: float = typer.Option(0.0, "--confidence", "-c", help="Confidence score (0.0-1.0)"),
) -> None:
    """Record routing feedback.

    \b
    Examples:
        # Record correct routing
        vibe feedback record "帮我 review 代码" "superpowers/review" --correct

        # Record incorrect routing
        vibe feedback record "测试这个功能" "superpowers/tdd" \\
            --wrong "gstack/qa" --confidence 0.7
    """
    collector = FeedbackCollector()

    collector.collect_feedback(
        query=query,
        routed_skill=skill,
        was_correct=correct,
        actual_skill=actual_skill,
        confidence=confidence,
    )

    if correct:
        console.print(f"[green]✓[/green] Recorded correct routing: {query} → {skill}")
    else:
        console.print(f"[yellow]⚠[/yellow] Recorded incorrect routing: {query} → {skill} (should be: {actual_skill})")


def report() -> None:
    """Generate and display feedback report."""
    report = get_feedback_report()

    if report.total_records == 0:
        console.print("[yellow]No feedback records found.[/yellow]")
        console.print("\n[dim]Use 'vibe feedback record' to collect feedback.[/dim]")
        return

    # Overall statistics
    console.print(f"\n[bold]Feedback Report[/bold]")
    console.print(f"Total records: {report.total_records}")
    console.print(f"Correct: {report.correct_count} ({report.correct_count / report.total_records * 100:.1f}%)")
    console.print(f"Incorrect: {report.incorrect_count} ({report.incorrect_count / report.total_records * 100:.1f}%)")
    console.print(f"[cyan]Accuracy: {report.accuracy_rate:.1%}[/cyan]")

    # By skill breakdown
    if report.by_skill:
        console.print(f"\n[bold]Accuracy by Skill:[/bold]")
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Skill", style="cyan")
        table.add_column("Correct", style="green")
        table.add_column("Incorrect", style="red")
        table.add_column("Accuracy", style="yellow")

        for skill_id, counts in sorted(report.by_skill.items()):
            total = counts["correct"] + counts["incorrect"]
            accuracy = counts["correct"] / total * 100 if total > 0 else 0
            table.add_row(
                skill_id,
                str(counts["correct"]),
                str(counts["incorrect"]),
                f"{accuracy:.1f}%",
            )

        console.print(table)

    # By confidence breakdown
    if report.by_confidence:
        console.print(f"\n[bold]Accuracy by Confidence:[/bold]")
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Confidence", style="cyan")
        table.add_column("Correct", style="green")
        table.add_column("Incorrect", style="red")
        table.add_column("Accuracy", style="yellow")

        for conf_bucket, counts in report.by_confidence.items():
            total = counts["correct"] + counts["incorrect"]
            accuracy = counts["correct"] / total * 100 if total > 0 else 0
            table.add_row(
                conf_bucket,
                str(counts["correct"]),
                str(counts["incorrect"]),
                f"{accuracy:.1f}%",
            )

        console.print(table)

    # Common errors
    if report.common_errors:
        console.print(f"\n[bold]Most Common Errors:[/bold]")
        for i, (error, count) in enumerate(report.common_errors[:10], 1):
            console.print(f"{i}. {error}: {count} times")


def export(
    output_file: str = typer.Argument(..., help="Output file path"),
) -> None:
    """Export feedback records to JSON file.

    \b
    Examples:
        vibe feedback export feedback_export.json
    """
    collector = FeedbackCollector()

    if collector.get_records():
        collector.export_records(output_file)
        console.print(f"[green]✓[/green] Exported {len(collector.get_records())} records to {output_file}")
    else:
        console.print("[yellow]No feedback records to export.[/yellow]")


def clear(
    confirm: bool = typer.Option(False, "--confirm", "-y", help="Skip confirmation"),
) -> None:
    """Clear all feedback records.

    \b
    Examples:
        vibe feedback clear --confirm
    """
    if not confirm:
        typer.confirm("Are you sure you want to clear all feedback records?", abort=True)

    collector = FeedbackCollector()
    count = len(collector.get_records())
    collector.clear_records()

    console.print(f"[green]✓[/green] Cleared {count} feedback records")


def list_cmd(
    limit: int = typer.Option(10, "--limit", "-n", help="Maximum number of records to show"),
) -> None:
    """List recent feedback records.

    \b
    Examples:
        vibe feedback list
        vibe feedback list --limit 20
    """
    collector = FeedbackCollector()
    records = collector.get_records(limit=limit)

    if not records:
        console.print("[yellow]No feedback records found.[/yellow]")
        return

    console.print(f"\n[bold]Recent {len(records)} Feedback Records:[/bold]\n")

    for i, record in enumerate(records, 1):
        status = "[green]✓[/green]" if record.was_correct else "[red]✗[/red]"
        console.print(f"{i}. {status} {record.query[:60]}")
        console.print(f"   Routed: {record.routed_skill} (confidence: {record.confidence:.2f})")

        if not record.was_correct and record.actual_skill:
            console.print(f"   [dim]Should be: {record.actual_skill}[/dim]")

        console.print(f"   [dim]Time: {record.timestamp}[/dim]\n")
