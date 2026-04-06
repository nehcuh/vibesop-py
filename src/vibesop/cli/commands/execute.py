"""Execute command — run a skill by ID with a query.

Usage:
    vibe execute systematic-debugging "debug database error"
    vibe execute omx/deep-interview "build a todo app"
    vibe execute omx/ralph --working-dir /path/to/project "implement feature X"
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import typer

from vibesop.cli.executor import execute_skill
from vibesop.core.skills.manager import SkillManager

app = typer.Typer(help="Execute a skill by ID with a query.")


@app.command()
def execute(
    skill_id: str = typer.Argument(
        ..., help="Skill ID to execute (e.g., systematic-debugging, omx/ralph)"
    ),
    query: str = typer.Argument(..., help="Query/context for the skill"),
    working_dir: str = typer.Option(
        ".", "--working-dir", "-C", help="Working directory for skill execution"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be executed without running"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output results as JSON"),
) -> None:
    """Execute a skill by ID with a query.

    This command bridges the gap between routing and execution.
    After running `vibe route` to find the right skill, use this
    command to actually run it.

    Examples:
        vibe execute systematic-debugging "debug database error"
        vibe execute omx/deep-interview "build a todo app"
        vibe execute omx/ralph -C /path/to/project "implement feature X"
        vibe execute gstack/qa --json "test my website"
    """
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    from vibesop.core.skills.manager import SkillManager

    console = Console()
    work_path = Path(working_dir).resolve()

    if not work_path.exists():
        console.print(f"[red]Error: Working directory does not exist: {work_path}[/red]")
        raise typer.Exit(1)

    manager = SkillManager(project_root=work_path)

    # Check if skill exists
    skill_def = manager.get_skill_info(skill_id)
    if skill_def is None:
        console.print(f"[red]Error: Skill not found: {skill_id}[/red]")
        console.print("")
        console.print("Available skills:")
        all_skills = manager.list_skills()
        for sid in sorted(all_skills.keys())[:20]:
            console.print(f"  - {sid}")
        if len(all_skills) > 20:
            console.print(f"  ... and {len(all_skills) - 20} more (use `vibe skills list`)")
        raise typer.Exit(1)

    if dry_run:
        table = Table(title="Dry Run — Would Execute")
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("Skill ID", skill_id)
        table.add_row(
            "Skill Name",
            skill_def.metadata.name
            if hasattr(skill_def, "metadata") and skill_def.metadata
            else skill_id,
        )
        table.add_row(
            "Intent",
            skill_def.metadata.intent
            if hasattr(skill_def, "metadata") and skill_def.metadata
            else "N/A",
        )
        table.add_row("Query", query)
        table.add_row("Working Dir", str(work_path))
        table.add_row(
            "Type", skill_def.skill_type.value if hasattr(skill_def, "skill_type") else "unknown"
        )
        console.print(table)
        return

    start_time = time.perf_counter()

    try:
        result = asyncio.run(
            execute_skill(
                skill_id=skill_id,
                query=query,
                working_dir=work_path,
            )
        )
    except Exception as e:
        console.print(f"[red]Execution error: {e}[/red]")
        raise typer.Exit(1) from e

    duration_ms = (time.perf_counter() - start_time) * 1000

    if json_output:
        output = {
            "skill_id": skill_id,
            "query": query,
            "success": result.success,
            "output": result.output,
            "error": result.error,
            "duration_ms": round(duration_ms, 2),
            "metadata": result.metadata or {},
        }
        console.print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        if result.success:
            status_icon = "✅"
            status_color = "green"
        else:
            status_icon = "❌"
            status_color = "red"

        console.print(
            Panel(
                f"[bold {status_color}]{status_icon} {skill_id}[/bold {status_color}]\n"
                f"\n[bold]Query:[/bold] {query}\n"
                f"[bold]Duration:[/bold] {duration_ms:.0f}ms\n"
                f"\n[bold]Output:[/bold]\n{result.output}"
                + (f"\n\n[bold red]Error:[/bold red] {result.error}" if result.error else ""),
                title="Skill Execution Result",
                border_style=status_color,
            )
        )

    if not result.success:
        raise typer.Exit(1)


@app.command("list")
def list_available(
    working_dir: str = typer.Option(".", "--working-dir", "-C", help="Working directory"),
    namespace: str = typer.Option(None, "--namespace", "-n", help="Filter by namespace"),
) -> None:
    """List all available skills that can be executed."""
    from rich.console import Console
    from rich.table import Table

    from vibesop.core.skills.manager import SkillManager

    console = Console()
    work_path = Path(working_dir).resolve()
    manager = SkillManager(project_root=work_path)

    skills = manager.list_skills()

    table = Table(title="Available Skills")
    table.add_column("Skill ID", style="cyan")
    table.add_column("Intent", style="green")
    table.add_column("Type", style="yellow")
    table.add_column("Namespace", style="magenta")

    for skill in sorted(skills, key=lambda s: s["id"]):
        if namespace and skill.get("namespace") != namespace:
            continue
        table.add_row(
            skill["id"],
            (skill.get("intent", "N/A") or "N/A")[:50],
            skill.get("type", "unknown"),
            skill.get("namespace", "N/A"),
        )

    console.print(table)
    console.print(f"\nTotal: {len(skills)} skills")
    if namespace:
        console.print(f"Filtered by namespace: {namespace}")
    console.print("\nExecute a skill: [bold cyan]vibe execute <skill_id> <query>[/bold cyan]")
