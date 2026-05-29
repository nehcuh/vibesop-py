"""`vibe spec` -- Skill specification validation and management."""

from __future__ import annotations

import logging
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from vibesop.spec import SpecValidator, SpecVersion

logger = logging.getLogger(__name__)
console = Console()


def spec(
    action: str = typer.Argument("version", help="Action: validate, version"),
    path: str | None = typer.Option(None, "--path", "-p", help="Path to SKILL.md file or skill directory"),
    all_skills: bool = typer.Option(False, "--all", help="Validate all installed skills"),
) -> None:
    """Manage the SKILL.md specification standard.

    Examples:
        vibe spec version              # Show current spec version
        vibe spec validate -p ./SKILL.md  # Validate a single file
        vibe spec validate --all          # Validate all installed skills
    """
    if action == "version":
        _show_version()
    elif action == "validate":
        _run_validation(path, all_skills)
    else:
        console.print(f"[red]Unknown action: {action}[/red]")
        console.print("Available actions: version, validate")
        raise typer.Exit(code=1)


def _show_version() -> None:
    """Display current and supported spec versions."""
    console.print(f"[bold]Current spec version:[/bold] {SpecVersion.V3_0.value}")
    console.print(f"[bold]Supported versions:[/bold] {', '.join(v.value for v in SpecVersion)}")
    console.print()
    console.print("[dim]Use 'vibe spec validate --all' to check installed skills for compliance.[/dim]")


def _run_validation(path: str | None, all_skills: bool) -> None:
    """Run spec validation against SKILL.md files."""
    validator = SpecValidator()

    if path:
        _validate_single(validator, Path(path).resolve())
    elif all_skills:
        _validate_all(validator)
    else:
        console.print("[yellow]Specify a path with --path, or use --all to validate all installed skills.[/yellow]")
        raise typer.Exit(code=1)


def _validate_single(validator: SpecValidator, skill_path: Path) -> None:
    """Validate a single SKILL.md file and display results."""
    result = validator.validate_file(skill_path)

    if result.valid:
        console.print(f"[green]Valid[/green] — {result.skill_id} (spec v{result.spec_version.value})")
    else:
        console.print(f"[red]Invalid[/red] — {result.skill_id} (spec v{result.spec_version.value})")

    if result.errors:
        console.print("\n[bold red]Errors:[/bold red]")
        for err in result.errors:
            console.print(f"  [red]✗[/red] [{err.field}] {err.message}")

    if result.warnings:
        console.print("\n[bold yellow]Warnings:[/bold yellow]")
        for warn in result.warnings:
            console.print(f"  [yellow]![/yellow] [{warn.field}] {warn.message}")

    if not result.errors and not result.warnings:
        console.print("  [dim]No issues found.[/dim]")


def _validate_all(validator: SpecValidator) -> None:
    """Validate all installed skills and produce a summary report."""
    import os

    # Search common skill locations
    search_paths = [
        Path.home() / ".config" / "skills",
        Path.home() / ".claude" / "skills",
        Path(os.getcwd()) / ".vibe" / "skills",
        Path(os.getcwd()) / "skills",
    ]

    all_results = []
    for search_path in search_paths:
        if not search_path.exists():
            continue
        for skill_md in search_path.rglob("SKILL.md"):
            result = validator.validate_file(skill_md)
            all_results.append(result)

    if not all_results:
        console.print("[yellow]No SKILL.md files found in standard locations.[/yellow]")
        return

    valid_count = sum(1 for r in all_results if r.valid)
    error_count = sum(len(r.errors) for r in all_results)
    warning_count = sum(len(r.warnings) for r in all_results)

    table = Table(title="Spec Validation Report")
    table.add_column("Valid?", style="bold")
    table.add_column("Skill ID")
    table.add_column("Version")
    table.add_column("Issues")

    for result in sorted(all_results, key=lambda r: (not r.valid, r.skill_id)):
        status = "[green]✓[/green]" if result.valid else "[red]✗[/red]"
        issues = f"{len(result.errors)}E {len(result.warnings)}W" if result.issue_count > 0 else "[dim]none[/dim]"
        table.add_row(status, result.skill_id, result.spec_version.value, issues)

    console.print(table)
    console.print()
    console.print(f"[bold]Summary:[/bold] {valid_count}/{len(all_results)} valid, "
                  f"{error_count} errors, {warning_count} warnings")
