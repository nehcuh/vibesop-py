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
    action: str = typer.Argument("version", help="Action: validate, version, conformance"),
    path: str | None = typer.Option(None, "--path", "-p", help="Path to SKILL.md file or skill directory"),
    all_skills: bool = typer.Option(False, "--all", help="Validate all installed skills / run all conformance tests"),
    platform: str | None = typer.Option(None, "--platform", help="Platform to check conformance for"),
    self_check: bool = typer.Option(False, "--self", help="Run spec self-conformance check"),
) -> None:
    """Manage the SKILL.md specification standard.

    Examples:
        vibe spec version              # Show current spec version
        vibe spec validate -p ./SKILL.md  # Validate a single file
        vibe spec validate --all          # Validate all installed skills
        vibe spec conformance --all       # Run full conformance suite
        vibe spec conformance --platform claude-code
    """
    if action == "version":
        _show_version()
    elif action == "validate":
        _run_validation(path, all_skills)
    elif action == "conformance":
        _run_conformance(platform, all_skills, self_check)
    else:
        console.print(f"[red]Unknown action: {action}[/red]")
        console.print("Available actions: version, validate, conformance")
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


def _run_conformance(platform: str | None, all_platforms: bool, self_only: bool) -> None:
    """Run the conformance test suite."""
    import subprocess
    import sys

    # tests/conformance/ is at repo root
    repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent
    test_dir = repo_root / "tests" / "conformance"

    if not test_dir.exists():
        console.print("[red]Conformance test directory not found.[/red]")
        console.print(f"Expected: {test_dir}")
        raise typer.Exit(code=1)

    if self_only:
        console.print("[bold]Spec Self-Conformance Check[/bold]\n")
        # Run spec compliance tests only (language-level, no platform deps)
        cmd = [sys.executable, "-m", "pytest", str(test_dir / "test_spec_compliance.py"), "-v", "-q"]
        result = subprocess.run(cmd, capture_output=False)
        raise typer.Exit(code=result.returncode)

    if platform:
        console.print(f"[bold]Conformance check for: {platform}[/bold]\n")
        if platform not in ("claude-code", "opencode", "cursor", "kimi-cli", "pi"):
            console.print(f"[red]Unknown platform: {platform}[/red]")
            console.print("Supported: claude-code, opencode, cursor, kimi-cli, pi")
            raise typer.Exit(code=1)
        # Run platform adapter tests for the specific platform
        cmd = [
            sys.executable, "-m", "pytest",
            str(test_dir / "test_platform_adapters.py"),
            "-v", "-q",
            "-k", platform.replace("-", "_"),
        ]
        result = subprocess.run(cmd, capture_output=False)
        raise typer.Exit(code=result.returncode)

    if all_platforms:
        console.print("[bold]Full Conformance Suite[/bold]\n")
        console.print("Running: spec compliance + platform adapters + agent runtime\n")
        cmd = [sys.executable, "-m", "pytest", str(test_dir), "-v", "-q"]
        result = subprocess.run(cmd, capture_output=False)
        if result.returncode == 0:
            console.print("\n[bold green]All conformance tests passed.[/bold green]")
        else:
            console.print("\n[bold red]Some conformance tests failed.[/bold red]")
        raise typer.Exit(code=result.returncode)

    console.print("[yellow]Specify --platform <name>, --all, or --self[/yellow]")
    console.print("Examples:")
    console.print("  vibe spec conformance --platform claude-code")
    console.print("  vibe spec conformance --all")
    console.print("  vibe spec conformance --self")
    raise typer.Exit(code=1)
