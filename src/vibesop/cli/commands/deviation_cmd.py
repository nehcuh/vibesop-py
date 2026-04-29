"""Deviation tracking CLI command.

Records and analyzes when Agent skips routing recommendations.
"""

import json
import logging
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from vibesop.cli.commands.deviation import (
    REASON_CODES,
    analyze_deviations,
    get_deviation_summary,
    record_deviation,
)

app = typer.Typer(
    name="deviation",
    help="Track and analyze routing deviations (when Agent skips recommendations)",
)
console = Console()
logger = logging.getLogger(__name__)


@app.command("record")
def record_cmd(
    query: str = typer.Argument(..., help="Original user query"),
    routed_skill: str = typer.Argument(..., help="What VibeSOP recommended"),
    confidence: float = typer.Argument(..., help="Confidence score (0.0-1.0)"),
    layer: str = typer.Argument(..., help="Routing layer that made the match"),
    reason_code: str = typer.Option(..., "--reason", "-r", help="Reason code for skipping"),
    actual_action: str = typer.Option(..., "--action", "-a", help="What Agent did instead"),
    justification: str = typer.Option("", "--justification", "-j", help="Agent's explanation"),
    storage_path: str = typer.Option(".vibe/memory/deviations.jsonl", "--path", "-p"),
) -> None:
    """Record a routing deviation."""
    from vibesop.core.models import RoutingLayer, RoutingResult, SkillRoute

    # Reconstruct RoutingResult for recording
    try:
        routing_layer = RoutingLayer(layer)
    except ValueError:
        routing_layer = RoutingLayer.NO_MATCH

    skill_route = SkillRoute(
        skill_id=routed_skill,
        confidence=confidence,
        layer=routing_layer,
    )

    routing_result = RoutingResult(
        primary=skill_route,
        alternatives=[],
        routing_path=[routing_layer],
        layer_details=[],
        query=query,
        duration_ms=0.0,
    )

    success = record_deviation(
        query=query,
        routing_result=routing_result,
        actual_action=actual_action,
        reason_code=reason_code,
        justification=justification,
        storage_path=storage_path,
    )

    if success:
        console.print(
            f'[green]✓[/green] Recorded deviation: [bold]{reason_code}[/bold] for query: "{query[:50]}..."'
        )
    else:
        console.print("[red]✗[/red] Failed to record deviation")
        raise typer.Exit(1)


@app.command("analyze")
def analyze_cmd(
    storage_path: str = typer.Option(".vibe/memory/deviations.jsonl", "--path", "-p"),
    min_records: int = typer.Option(5, "--min", "-m", help="Minimum records for analysis"),
) -> None:
    """Analyze deviation patterns."""
    result = analyze_deviations(storage_path=storage_path, min_records=min_records)

    if "error" in result:
        console.print(f"[red]✗[/red] {result['error']}")
        raise typer.Exit(1)

    console.print("[bold]📊 Deviation Analysis[/bold]\n")

    if "total_records" in result:
        console.print(f"Total records: {result['total_records']}")

        if "analysis_period" in result:
            console.print(f"Period: {result['analysis_period']}")

        if "deviation_rate" in result:
            console.print(f"Deviation rate: {result['deviation_rate']:.1%}")

        console.print("\n[bold]Breakdown by reason:[/bold]")
        for reason, count in result.get("reason_breakdown", {}).items():
            description = REASON_CODES.get(reason, reason)
            console.print(f"  • [bold]{reason}[/bold] ({count}): {description}")

        if result.get("top_mismatched_skills"):
            console.print("\n[bold]Most mismatched skills:[/bold]")
            for skill, count in result["top_mismatched_skills"].items():
                console.print(f"  • {skill}: {count} mismatches")

        if result.get("recommendations"):
            console.print("\n[bold]💡 Recommendations:[/bold]")
            for rec in result["recommendations"]:
                console.print(f"  • {rec}")
    else:
        console.print(result.get("message", "No analysis available"))


@app.command("summary")
def summary_cmd(
    storage_path: str = typer.Option(".vibe/memory/deviations.jsonl", "--path", "-p"),
) -> None:
    """Show a human-readable summary of deviations."""
    summary = get_deviation_summary(storage_path=storage_path)
    console.print(summary)


@app.command("list")
def list_cmd(
    storage_path: str = typer.Option(".vibe/memory/deviations.jsonl", "--path", "-p"),
    limit: int = typer.Option(10, "--limit", "-l", help="Number of records to show"),
    reason_filter: str | None = typer.Option(None, "--reason", "-r", help="Filter by reason code"),
) -> None:
    """List recent deviations."""
    path = Path(storage_path)
    if not path.exists():
        console.print("[dim]No deviation records found.[/dim]")
        return

    records = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    records.append(json.loads(stripped))
    except (OSError, ValueError, json.JSONDecodeError) as e:
        console.print(f"[red]Error reading deviation records: {e}[/red]")
        raise typer.Exit(1) from e

    if reason_filter:
        records = [r for r in records if r.get("reason_code") == reason_filter]

    records = records[-limit:]

    if not records:
        console.print("[dim]No deviation records found.[/dim]")
        return

    table = Table(title=f"Recent Deviations (showing last {len(records)})")
    table.add_column("Time", style="dim")
    table.add_column("Routed Skill")
    table.add_column("Confidence")
    table.add_column("Reason")
    table.add_column("Query")

    for record in records:
        timestamp = record.get("timestamp", "")[:16].replace("T", " ")
        skill = record.get("routed_skill", "N/A")
        conf = f"{record.get('confidence', 0):.0%}"
        reason = record.get("reason_code", "unknown")
        query = record.get("query", "")[:40]
        table.add_row(timestamp, skill, conf, reason, query)

    console.print(table)


@app.command("reasons")
def reasons_cmd() -> None:
    """List all available reason codes."""
    console.print("[bold]Available Reason Codes:[/bold]\n")

    table = Table()
    table.add_column("Code")
    table.add_column("Description")
    table.add_column("Severity")

    for code, description in REASON_CODES.items():
        severity = (
            "high" if code == "skill_mismatch" else "medium" if code == "context_ignored" else "low"
        )
        severity_color = (
            "red" if severity == "high" else "yellow" if severity == "medium" else "green"
        )
        table.add_row(
            f"[bold]{code}[/bold]", description, f"[{severity_color}]{severity}[/{severity_color}]"
        )

    console.print(table)


@app.command("reset")
def reset_cmd(
    storage_path: Path = typer.Option(".vibe/memory/deviations.jsonl", "--path", "-p"),
    confirm: bool = typer.Option(False, "--confirm", "-y", help="Skip confirmation"),
) -> None:
    """Reset deviation records."""
    if not confirm:
        confirm_reset = typer.confirm("Are you sure you want to reset all deviation records?")
        if not confirm_reset:
            console.print("[dim]Reset cancelled.[/dim]")
            raise typer.Exit(0)

    path = Path(storage_path)
    if path.exists():
        storage_path.unlink()
        console.print("[green]✓[/green] Deviation records reset")
    else:
        console.print("[dim]No deviation records to reset.[/dim]")
