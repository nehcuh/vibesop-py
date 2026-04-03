"""VibeSOP import-rules command - Import external rules.

This command imports external legacy rules (like team README.md)
into VibeSOP configuration.

Usage:
    vibe import-rules FILE
    vibe import-rules FILE --force

Examples:
    # Import rules from a file
    vibe import-rules team-conventions.md

    # Import and overwrite
    vibe import-rules rules.md --force
"""

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

console = Console()


def import_rules(
    file_path: Path = typer.Argument(
        ...,
        help="Path to rules file to import",
        exists=True,
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite existing rules",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview changes without writing",
    ),
    target: str = typer.Option(
        "rules",
        "--target",
        "-t",
        help="Target file (rules or behavior-policies)",
    ),
) -> None:
    """Import external legacy rules into VibeSOP.

    This command converts external rule files (like team README.md)
    into VibeSOP configuration format.

    \b
    Examples:
        # Import rules from a file
        vibe import-rules team-conventions.md

        # Import to behavior-policies
        vibe import-rules conventions.md --target behavior-policies

        # Preview without writing
        vibe import-rules rules.md --dry-run

        # Overwrite existing
        vibe import-rules rules.md --force
    """
    console.print(
        f"\n[bold cyan]📥 Import Rules[/bold cyan]"
        f"\n{'=' * 40}\n"
    )

    # Read the input file
    content = file_path.read_text()
    console.print(f"[dim]Source: {file_path}[/dim]")
    console.print(f"[dim]Size: {len(content)} bytes[/dim]\n")

    if dry_run:
        console.print(
            Panel(
                f"[bold cyan]🔍 DRY RUN[/bold cyan]\n\n"
                f"[bold]Source:[/bold] {file_path}\n"
                f"[bold]Target:[/bold] {target}\n\n"
                f"[bold]Preview:[/bold]\n"
                f"{content[:200]}...\n\n"
                f"[dim]Remove --dry-run to actually import.[/dim]",
                border_style="cyan",
            )
        )
        return

    # Parse and convert rules
    rules = _parse_rules(content)

    # Determine output path
    if target == "rules":
        output_dir = Path(".vibe/rules")
        output_file = output_dir / "imported-rules.md"
    else:
        output_dir = Path(".vibe/core")
        output_file = output_dir / "policies" / "imported.yaml"

    output_dir.mkdir(parents=True, exist_ok=True)

    # Check if file exists
    if output_file.exists() and not force:
        console.print(
            f"[yellow]⚠️  Target file exists: {output_file}[/yellow]\n"
            f"[dim]Use --force to overwrite[/dim]"
        )
        raise typer.Exit(1)

    # Write converted rules
    output_file.write_text(rules)

    console.print(
        f"\n[green]✓ Rules imported[/green]\n"
        f"  [dim]Target:[/dim] {output_file}\n"
        f"  [dim]Rules:[/dim] {len(content.splitlines())} lines imported\n"
    )


def _parse_rules(content: str) -> str:
    """Parse rules from content.

    Args:
        content: Original content

    Returns:
        Converted VibeSOP format
    """
    # Simple conversion - add header
    header = f"""# Imported Rules

This file contains rules imported from an external source.

## Original Content

"""

    return header + content
