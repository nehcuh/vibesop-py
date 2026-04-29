"""Instinct learning system CLI commands.

Provides:
- vibe instinct learn <pattern> <action> [--context] [--tags]: Record a pattern
- vibe instinct eval: Review and approve detected sequence patterns
- vibe instinct status [--tag]: View all learned instincts
- vibe instinct export [--output]: Export instincts to JSON
- vibe instinct import <file> [--force]: Import instincts from JSON
- vibe instinct evolve [--index]: Upgrade a high-confidence instinct to a formal skill
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
import logging

logger = logging.getLogger(__name__)


app = typer.Typer(name="instinct", help="Instinct learning system", no_args_is_help=False)
console = Console()


def _get_storage_path() -> Path:
    return Path.cwd() / ".vibe" / "instincts.jsonl"


@app.callback(invoke_without_command=True)
def _instinct_overview(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is not None:
        return

    from vibesop.core.instinct.learner import InstinctLearner

    learner = InstinctLearner(_get_storage_path())
    stats = learner.get_stats()
    instincts = learner.get_reliable_instincts()
    candidates = learner.get_sequence_candidates()

    console.rule("[bold cyan]Instinct Learning System[/bold cyan]")
    console.print()

    console.print(
        f"  [bold]{stats['total_instincts']}[/bold] total instincts "
        f"([green]{stats['reliable_instincts']}[/green] reliable, "
        f"[yellow]{stats['sequence_candidates']}[/yellow] candidates)"
    )
    console.print()

    if instincts:
        high = [i for i in instincts if i.confidence >= 0.8]
        if high:
            console.print("[bold]High Confidence (>= 0.8):[/bold]")
            for i in high:
                console.print(f"  [cyan]{i.pattern}[/cyan] ({i.confidence:.0%}, {i.total_applications} uses)")

    console.print()
    console.print("[dim]Quick actions:[/dim]")
    console.print("  [cyan]vibe instinct learn[/cyan]    [dim]— record a pattern[/dim]")
    console.print("  [cyan]vibe instinct eval[/cyan]     [dim]— review candidates[/dim]")
    console.print("  [cyan]vibe instinct status[/cyan]   [dim]— view all instincts[/dim]")
    console.print("  [cyan]vibe instinct export[/cyan]   [dim]— backup to JSON[/dim]")
    console.print("  [cyan]vibe instinct import[/cyan]   [dim]— restore from JSON[/dim]")
    console.print("  [cyan]vibe instinct evolve[/cyan]   [dim]— upgrade to skill[/dim]")
    console.print()


@app.command()
def learn(
    pattern: str = typer.Argument(..., help="One-sentence pattern description"),
    action: str = typer.Argument(..., help="What action to take when pattern matches"),
    context: str = typer.Option("", "--context", "-c", help="When this instinct applies"),
    tags: list[str] | None = typer.Option(None, "--tag", "-t", help="Categories (repeatable)"),
    source: str = typer.Option("manual", "--source", "-s", help="Where this instinct came from"),
) -> None:
    """Record a successful workflow pattern as an instinct."""
    from vibesop.core.instinct.learner import InstinctLearner

    learner = InstinctLearner(_get_storage_path())
    instinct = learner.learn(
        pattern=pattern,
        action=action,
        context=context,
        tags=tags or [],
        source=source,
    )
    console.print(f"[green]Learned:[/green] {instinct.pattern} (id: [dim]{instinct.id[:16]}...[/dim])")


@app.command()
def eval(
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Review detected sequence patterns and convert to skill suggestions."""
    from vibesop.core.instinct.learner import InstinctLearner
    from vibesop.core.skills.suggestion_collector import SkillSuggestionCollector

    learner = InstinctLearner(_get_storage_path())
    candidates = learner.get_sequence_candidates()

    if json_output:
        data = {
            "candidates": [
                {
                    "steps": c.steps,
                    "total_count": c.total_count,
                    "success_rate": c.success_rate,
                    "context_tags": c.context_tags,
                }
                for c in candidates
            ],
            "total": len(candidates),
        }
        console.print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
        return

    if not candidates:
        console.print("[dim]No pattern candidates ready yet.[/dim]")
        console.print("[dim]Need 5+ occurrences with 80%+ success rate.[/dim]")
        return

    table = Table(title="Pattern Candidates")
    table.add_column("#", style="bold")
    table.add_column("Steps", style="cyan")
    table.add_column("Count", justify="right")
    table.add_column("Success", justify="right")
    table.add_column("Tags")

    for i, c in enumerate(candidates, 1):
        table.add_row(
            str(i),
            " → ".join(c.steps),
            str(c.total_count),
            f"{c.success_rate:.0%}",
            ", ".join(c.context_tags) if c.context_tags else "-",
        )

    console.print(table)

    if candidates:
        console.print()
        collector = SkillSuggestionCollector()
        for c in candidates:
            try:
                collector.add_from_pattern(c)
                console.print(f"[green]Approved:[/green] {' → '.join(c.steps)}")
            except Exception as e:
                logger.warning("Unhandled error: %s", e)
        pending = collector.get_pending()
        if pending:
            console.print(f"[green]✓[/green] [bold]{len(pending)}[/bold] suggestion(s) pending. Run [cyan]vibe skills suggestions[/cyan] to review.")


@app.command()
def status(
    tag: str | None = typer.Option(None, "--tag", "-t", help="Filter instincts by tag"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """View all learned instincts with confidence scores and usage statistics."""
    from vibesop.core.instinct.learner import InstinctLearner

    learner = InstinctLearner(_get_storage_path())
    instincts = learner.get_reliable_instincts(tag=tag)

    if json_output:
        data = {
            "total": len(instincts),
            "instincts": [i.to_dict() for i in instincts],
        }
        console.print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
        return

    if not instincts:
        console.print("[dim]No reliable instincts yet. Use [cyan]vibe instinct learn[/cyan] to build your knowledge base.[/dim]")
        return

    high = [i for i in instincts if i.confidence >= 0.8]
    mid = [i for i in instincts if 0.6 <= i.confidence < 0.8]
    low = [i for i in instincts if i.confidence < 0.6]

    console.print(f"[bold]Active Instincts:[/bold] [green]{len(instincts)}[/green] total")
    if tag:
        console.print(f"[dim]Filtered by tag: {tag}[/dim]")
    console.print()

    if high:
        console.print("[bold]High Confidence (>= 0.8):[/bold]")
        for i in high:
            console.print(
                f"  [cyan]{i.pattern}[/cyan]\n"
                f"    Action: {i.action}  |  Uses: {i.total_applications}  |  Tags: {', '.join(i.tags) if i.tags else '-'}"
            )
    if mid:
        console.print("\n[bold]Medium Confidence (0.6-0.8):[/bold]")
        for i in mid:
            console.print(f"  [{i.confidence:.0%}] {i.pattern}")
    if low:
        console.print("\n[dim]Low Confidence (<0.6):[/dim]")
        for i in low:
            console.print(f"  [dim][{i.confidence:.0%}] {i.pattern}[/dim]")

    stats = learner.get_stats()
    console.print()
    console.print(f"[dim]Total: {stats['total_instincts']} | Candidates: {len(learner.get_sequence_candidates())}[/dim]")


@app.command()
def export(
    output: Path = typer.Option(
        Path("instincts-export.json"),
        "--output",
        "-o",
        help="Output file path",
    ),
    min_confidence: float = typer.Option(0.0, "--min-confidence", "-c", help="Minimum confidence filter"),
    tag: str | None = typer.Option(None, "--tag", "-t", help="Filter by tag"),
) -> None:
    """Export reliable instincts to JSON for backup or team sharing."""
    from vibesop.core.instinct.learner import InstinctLearner

    learner = InstinctLearner(_get_storage_path())
    instincts = learner.get_reliable_instincts()

    if min_confidence > 0:
        instincts = [i for i in instincts if i.confidence >= min_confidence]
    if tag:
        instincts = [i for i in instincts if tag.lower() in [t.lower() for t in i.tags]]

    data: dict[str, Any] = {
        "version": "1.0",
        "exported_at": datetime.now().isoformat(),
        "instincts": [i.to_dict() for i in instincts],
    }

    output_path = Path.cwd() / output if not output.is_absolute() else output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str))
    console.print(f"[green]Exported[/green] [bold]{len(instincts)}[/bold] instincts to [cyan]{output_path}[/cyan]")


@app.command(name="import")
def import_(
    file: Path = typer.Argument(..., help="Path to the JSON export file"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing instincts with same ID"),
) -> None:
    """Import instincts from a JSON export file (team sharing or backup restore)."""
    from vibesop.core.instinct.learner import Instinct, InstinctLearner

    input_path = file if file.is_absolute() else Path.cwd() / file
    if not input_path.exists():
        console.print(f"[red]✗[/red] File not found: {input_path}")
        raise typer.Exit(1)

    try:
        data = json.loads(input_path.read_text())
        incoming = [Instinct.from_dict(i) for i in data.get("instincts", [])]
    except (json.JSONDecodeError, KeyError) as e:
        console.print(f"[red]✗[/red] Invalid export file: {e}")
        raise typer.Exit(1)

    learner = InstinctLearner(_get_storage_path())
    imported = 0
    skipped = 0
    updated = 0

    for instinct in incoming:
        if instinct.id not in learner._instincts:
            learner._instincts[instinct.id] = instinct
            with learner.storage_path.open("a") as f:
                f.write(json.dumps(instinct.to_dict(), default=str) + "\n")
            imported += 1
        elif force:
            learner._instincts[instinct.id] = instinct
            updated += 1
        else:
            skipped += 1

    if imported or updated:
        learner._save()

    parts = []
    if imported:
        parts.append(f"[green]{imported}[/green] imported")
    if updated:
        parts.append(f"[yellow]{updated}[/yellow] updated (overwritten)")
    if skipped:
        parts.append(f"[dim]{skipped}[/dim] skipped (duplicates)")
    console.print(f"[bold]Result:[/bold] {', '.join(parts)}")


@app.command()
def evolve(
    index: int = typer.Option(
        0,
        "--index",
        "-i",
        help="Index of the instinct to evolve (from 'vibe instinct evolve' without args)",
    ),
    list_only: bool = typer.Option(False, "--list", "-l", help="Only list candidates, don't generate"),
) -> None:
    """Upgrade a high-confidence instinct into a formal VibeSOP skill."""
    from vibesop.core.instinct.learner import InstinctLearner

    learner = InstinctLearner(_get_storage_path())
    reliable = [
        i
        for i in learner.get_reliable_instincts()
        if i.confidence >= 0.8 and i.total_applications >= 10
    ]

    if not reliable:
        console.print("[yellow]No instincts ready for evolution.[/yellow]")
        console.print("[dim]Need confidence >= 0.8 and 10+ uses.[/dim]")
        return

    if list_only:
        console.print("[bold]Evolution Candidates:[/bold]")
        for j, ins in enumerate(reliable):
            console.print(f"  {j}. [cyan]{ins.pattern}[/cyan] ({ins.confidence:.0%}, {ins.total_applications} uses)")
        return

    # Default: list if no index given, or the index is out of range but we'll show list first
    if index < 0 or index >= len(reliable):
        console.print("[bold]Evolution Candidates:[/bold]")
        for j, ins in enumerate(reliable):
            console.print(f"  {j}. [cyan]{ins.pattern}[/cyan] ({ins.confidence:.0%}, {ins.total_applications} uses)")
        if len(reliable) > 1:
            console.print()
            console.print("[dim]Use --index <N> to pick one, or 0 for the first.[/dim]")
        else:
            console.print()
            console.print("[dim]Use --index 0 to evolve the sole candidate.[/dim]")
        return

    ins = reliable[index]
    skill_id = "custom/" + ins.pattern.lower().replace(" ", "-").replace(",", "")[:50]
    skill_dir = Path.cwd() / ".vibe" / "skills" / skill_id
    skill_dir.mkdir(parents=True, exist_ok=True)

    skill_md = f"""---
id: {skill_id}
name: {skill_id}
description: {ins.pattern} (evolved from instinct)
tags: {ins.tags}
intent: workflow
namespace: custom
version: 1.0.0
type: prompt
source: instinct-evolution
instinct_id: {ins.id}
---

# {ins.pattern}

## Overview

Pattern evolved from instinct with {ins.confidence:.0%} confidence ({ins.total_applications} uses).

## When to Apply

{ins.context}

## Steps

When this pattern matches, {ins.action}.

## Metrics

- **Confidence**: {ins.confidence:.0%}
- **Success rate**: {ins.success_rate:.0%} ({ins.success_count}/{ins.total_applications})
- **Evolved from**: instinct #{ins.id[:8]}
"""

    (skill_dir / "SKILL.md").write_text(skill_md)
    console.print(f"[green]Skill created:[/green] {skill_dir}/SKILL.md")
    console.print(f"[green]Skill ID:[/green] [cyan]{skill_id}[/cyan]")
    console.print()
    console.print("[dim]Next: run [cyan]vibe skills suggestions[/cyan] to register it formally.[/dim]")
