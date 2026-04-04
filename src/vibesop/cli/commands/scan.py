# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false
"""VibeSOP scan command - Security scanning.

This command scans files for security issues and threats.

Usage:
    vibe scan PATH
    vibe scan --all
    vibe scan --help

Examples:
    # Scan current directory
    vibe scan .

    # Scan with report
    vibe scan . --report security-report.json

    # Scan all skill files
    vibe scan --all
"""

from pathlib import Path
from typing import Optional, List

import typer
from rich.console import Console
from rich.table import Table

from vibesop.security.scanner import SecurityScanner

console = Console()


def scan(
    paths: List[Path] = typer.Argument(
        ...,
        help="Paths to scan",
        exists=True,
    ),
    all_files: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Scan all files (not just code files)",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output report to file",
    ),
    min_severity: str = typer.Option(
        "medium",
        "--min-severity",
        "-s",
        help="Minimum severity: low, medium, high, critical",
    ),
) -> None:
    """Scan files for security issues.

    This command scans files for potential security issues
    such as hardcoded secrets, path traversal, etc.

    \b
    Examples:
        # Scan current directory
        vibe scan .

        # Scan specific files
        vibe scan src/ config/

        # Scan all file types
        vibe scan . --all

        # Output report to file
        vibe scan . --output report.json
    """
    console.print(f"\n[bold cyan]🔍 Security Scan[/bold cyan]\n{'=' * 40}\n")

    scanner = SecurityScanner()

    # Collect files to scan
    files_to_scan = []
    for path in paths:
        if path.is_file():
            files_to_scan.append(path)
        elif path.is_dir():
            # Get code files
            extensions = [".py", ".js", ".ts", ".rb", ".yaml", ".yml", ".json"]
            if all_files:
                extensions = []  # All files

            for ext in extensions or ["*"]:
                files_to_scan.extend(path.rglob(f"*{ext}" if ext else "*"))

    console.print(f"[dim]Scanning {len(files_to_scan)} files...[/dim]\n")

    # Run scan
    results = []
    for file_path in files_to_scan[:100]:  # Limit to 100 files
        try:
            issues = scanner.scan_file(file_path)
            if issues:
                results.extend(issues)
        except Exception as e:
            console.print(f"[dim]Error scanning {file_path}: {e}[/dim]")

    # Show results
    if not results:
        console.print("[green]✓ No security issues found[/green]")
    else:
        console.print(f"[yellow]⚠️  Found {len(results)} potential issues[/yellow]\n")

        # Create table
        table = Table()
        table.add_column("File", style="cyan")
        table.add_column("Severity")
        table.add_column("Issue")
        table.add_column("Line", style="dim")

        # Sort by severity
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        sorted_results = sorted(
            results, key=lambda r: severity_order.get(r.get("severity", "low"), 99)
        )

        for issue in sorted_results[:20]:
            severity = issue.get("severity", "low")
            severity_color = {
                "critical": "red",
                "high": "red",
                "medium": "yellow",
                "low": "blue",
                "info": "dim",
            }.get(severity, "dim")

            table.add_row(
                str(issue.get("file", ""))[:30],
                f"[{severity_color}]{severity}[/{severity_color}]",
                issue.get("message", "")[:50],
                str(issue.get("line", "")),
            )

        console.print(table)

        if len(results) > 20:
            console.print(f"\n[dim]... and {len(results) - 20} more issues[/dim]")

    # Output report
    if output and results:
        import json

        output.write_text(json.dumps(results, indent=2))
        console.print(f"\n[dim]Report saved to: {output}[/dim]")
