"""VibeSOP import-rules command - Import external rules.

.. warning::
    This is an experimental feature. The interface and behavior may change
    in future versions. Use with caution in production environments.

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


def _show_experimental_warning() -> None:
    """Show experimental feature warning."""
    console.print(
        "[yellow]⚠️  Experimental Feature[/yellow]\n"
        "[dim]This command is experimental and may change in future versions.[/dim]\n"
    )


def import_rules(
    file_path: Path = typer.Argument(  # noqa: B008
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
    """Import external legacy rules into VibeSOP (experimental).

    .. warning::
        This is an experimental feature. The interface may change.

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
    # Show experimental warning
    _show_experimental_warning()

    console.print(f"\n[bold cyan]📥 Import Rules[/bold cyan]\n{'=' * 40}\n")

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
        output_dir = Path(".vibe/core/policies")
        output_file = output_dir / "imported.yaml"

    output_dir.mkdir(parents=True, exist_ok=True)

    # Check if file exists
    if output_file.exists() and not force:
        console.print(
            f"[yellow]⚠️  File already exists:[/yellow] {output_file}\n"
            "[dim]Use --force to overwrite.[/dim]"
        )
        raise typer.Exit(1)

    # Write rules
    output_file.write_text(rules)

    console.print(
        Panel(
            f"[bold green]✅ Import Successful[/bold green]\n\n"
            f"[bold]Source:[/bold] {file_path}\n"
            f"[bold]Target:[/bold] {output_file}\n"
            f"[bold]Rules:[/bold] {len(rules)} bytes",
            border_style="green",
        )
    )


def _parse_rules(content: str) -> str:
    """Parse and convert rules content.

    Args:
        content: Raw content from input file

    Returns:
        Converted rules in markdown format
    """
    # Simple conversion - just wrap in markdown
    lines = content.split("\n")

    # Add VibeSOP header
    result = ["# Imported Rules", "", "> Source: External rule file", "", "---", ""]

    # Add original content
    result.extend(lines)

    return "\n".join(result)
