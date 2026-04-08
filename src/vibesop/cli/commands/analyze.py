"""VibeSOP analyze command - Analyze and inspect various aspects.

This unified command provides analysis capabilities for:
- Sessions: Analyze conversation history and suggest skills
- Security: Scan files for security issues
- Integrations: Detect available skill pack integrations

Usage:
    vibe analyze session [file]
    vibe analyze security [path]
    vibe analyze integrations
    vibe analyze --help

Examples:
    # Analyze current session
    vibe analyze session

    # Scan for security issues
    vibe analyze security .

    # Detect skill pack integrations
    vibe analyze integrations
"""

from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def analyze(
    target: str = typer.Argument(
        ...,
        help="Analysis target: session, security, integrations",
    ),
    source: Path | None = typer.Argument(
        None,
        help="Source file or directory to analyze",
        exists=True,
    ),
    min_frequency: int = typer.Option(
        3,
        "--min-frequency",
        "-f",
        help="Minimum pattern frequency (for session analysis)",
    ),
    min_confidence: float = typer.Option(
        0.7,
        "--min-confidence",
        "-c",
        help="Minimum confidence threshold",
    ),
    auto_craft: bool = typer.Option(
        False,
        "--auto-craft",
        "-a",
        help="Auto-create skills (session analysis only)",
    ),
    all_files: bool = typer.Option(
        False,
        "--all",
        help="Scan all files (security analysis only)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed information",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Output as JSON",
    ),
) -> None:
    """Analyze sessions, security, or integrations.

    Unified analysis command that provides different analysis capabilities
    based on the target type.

    \b
    Session Analysis:
        # Analyze current session
        vibe analyze session

        # Analyze specific session file
        vibe analyze session conversation.jsonl

        # Auto-create suggested skills
        vibe analyze session --auto-craft

    Security Analysis:
        # Scan current directory
        vibe analyze security .

        # Scan specific files
        vibe analyze security src/ config/

        # Include all file types
        vibe analyze security . --all

    Integration Detection:
        # Detect installed integrations
        vibe analyze integrations

        # Show all available integrations
        vibe analyze integrations --verbose
    """
    if target == "session":
        _analyze_session(source, min_frequency, min_confidence, auto_craft)
    elif target == "security":
        _analyze_security(source or Path("."), all_files, json_output)
    elif target == "integrations":
        _analyze_integrations(verbose, json_output)
    else:
        console.print(
            f"[red]✗ Unknown analysis target: {target}[/red]\n"
            f"[dim]Valid targets: session, security, integrations[/dim]"
        )
        raise typer.Exit(1)


def _analyze_session(
    source: Path | None,
    min_frequency: int,
    min_confidence: float,
    auto_craft: bool,
) -> None:
    """Analyze session file for patterns and skill suggestions.

    Args:
        source: Session file path
        min_frequency: Minimum pattern frequency
        min_confidence: Minimum confidence threshold
        auto_craft: Whether to auto-create skills
    """
    from vibesop.core.session_analyzer import SessionAnalyzer

    console.print(f"\n[bold cyan]🔍 Session Analysis[/bold cyan]\n{'=' * 40}\n")

    analyzer = SessionAnalyzer(
        min_frequency=min_frequency,
        min_confidence=min_confidence,
    )

    # Find session file
    session_file = source or _find_current_session()

    if not session_file or not session_file.exists():
        console.print("[yellow]No session file found[/yellow]")
        console.print("[dim]Run: vibe analyze session <path-to-session>[/dim]")
        return

    console.print(f"[dim]Analyzing: {session_file}[/dim]\n")

    # Analyze
    suggestions = analyzer.analyze_session_file(session_file)

    if not suggestions:
        console.print("[green]✓ No strong patterns detected[/green]")
        console.print("[dim]Your session doesn't show repeated patterns yet.[/dim]")
        return

    # Show summary
    console.print(f"[green]Found {len(suggestions)} potential skills[/green]\n")

    # Display suggestions
    for i, suggestion in enumerate(suggestions, 1):
        value_color = {
            "high": "green",
            "medium": "yellow",
            "low": "dim",
        }.get(suggestion.estimated_value, "dim")

        console.print(
            f"{i}. [cyan]{suggestion.skill_name}[/cyan]\n"
            f"   [dim]Frequency:[/dim] {suggestion.frequency} queries  "
            f"[dim]Confidence:[/dim] {suggestion.confidence:.0%}  "
            f"[dim]Value:[/dim] [{value_color}]{suggestion.estimated_value}[/{value_color}]\n"
            f"   [dim]Example:[/dim] {suggestion.trigger_queries[0][:50]}...\n"
        )

    if auto_craft:
        console.print("\n[cyan]Auto-creating skills...[/cyan]\n")
        _auto_create_skills(suggestions)
        console.print(
            f"\n[green]✓ Created skills[/green]\n"
            "[dim]Run [cyan]vibe build[/cyan] to include them in your configuration.[/dim]"
        )
    else:
        console.print(
            f"\n[dim]To create these skills, run:[/dim]\n"
            f"  [cyan]vibe analyze session {session_file} --auto-craft[/cyan]\n"
        )


def _analyze_security(
    paths: Path,
    all_files: bool,
    json_output: bool,
) -> None:
    """Scan files for security issues.

    Args:
        paths: Path or directory to scan
        all_files: Whether to scan all file types
        json_output: Whether to output JSON
    """
    from vibesop.security.scanner import SecurityScanner

    console.print(f"\n[bold cyan]🔍 Security Scan[/bold cyan]\n{'=' * 40}\n")

    scanner = SecurityScanner()

    # Collect files to scan
    files_to_scan = []
    if paths.is_file():
        files_to_scan.append(paths)
    elif paths.is_dir():
        extensions = [".py", ".js", ".ts", ".rb", ".yaml", ".yml", ".json"]
        if all_files:
            extensions = []

        for ext in extensions or ["*"]:
            files_to_scan.extend(paths.rglob(f"*{ext}" if ext else "*"))

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

    # JSON output
    if json_output:
        import json

        console.print(json.dumps(results, indent=2))
        return

    # Display results
    if not results:
        console.print("[green]✓ No security issues found[/green]")
    else:
        console.print(f"[yellow]⚠️  Found {len(results)} potential issues[/yellow]\n")

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


def _analyze_integrations(
    verbose: bool,
    json_output: bool,
) -> None:
    """Detect available skill pack integrations.

    Args:
        verbose: Whether to show detailed information
        json_output: Whether to output JSON
    """
    from vibesop.integrations import IntegrationDetector, IntegrationManager, IntegrationStatus

    console.print(f"\n[bold cyan]🔍 Detecting Integrations[/bold cyan]\n{'=' * 40}\n")

    detector = IntegrationDetector()
    manager = IntegrationManager()

    # Check skills base path
    skills_path = detector.skills_base_path
    if skills_path:
        console.print(f"[dim]Skills path: {skills_path}[/dim]\n")
    else:
        console.print("[yellow]⚠ No skills path found[/yellow]\n[dim]Expected locations:[/dim]")
        for path in IntegrationDetector.SKILLS_BASE_PATHS:
            console.print(f"  [dim]  {path}[/dim]")
        console.print()

    # Detect all integrations
    all_integrations = manager.list_integrations(refresh=True)

    # JSON output
    if json_output:
        import json

        data = [info.to_dict() for info in all_integrations]
        console.print_json(json.dumps(data, indent=2))
        return

    # Table output
    table = Table(title="Skill Pack Integrations")
    table.add_column("Integration", style="cyan")
    table.add_column("Status")
    table.add_column("Description")
    table.add_column("Version", style="dim")

    for info in all_integrations:
        # Status icon
        if info.status == IntegrationStatus.INSTALLED:
            status = "[green]✓ Installed[/green]"
        elif info.status == IntegrationStatus.NOT_INSTALLED:
            status = "[dim]⊘ Not installed[/dim]"
        elif info.status == IntegrationStatus.INCOMPATIBLE:
            status = "[yellow]⚠ Incompatible[/yellow]"
        else:
            status = "[dim]? Unknown[/dim]"

        # Version
        version = info.version or "[dim]-[/dim]"

        table.add_row(
            info.name,
            status,
            info.description,
            version,
        )

        # Show skills if verbose
        if verbose and info.skills:
            for skill in info.skills:
                table.add_row(
                    "",
                    "",
                    f"  [dim]→ {skill}[/dim]",
                    "",
                )

    console.print(table)

    # Show summary
    installed_count = sum(1 for i in all_integrations if i.status == IntegrationStatus.INSTALLED)
    total_count = len(all_integrations)

    console.print(f"\n[dim]Installed: {installed_count}/{total_count} integrations[/dim]")

    if installed_count < total_count:
        not_installed = [
            i.name for i in all_integrations if i.status != IntegrationStatus.INSTALLED
        ]
        if not_installed:
            console.print(
                f"\n[dim]Available to install: {', '.join(not_installed)}[/dim]\n"
                "[dim]Run: [cyan]vibe install <name>[/cyan] to install[/dim]"
            )


def _find_current_session() -> Path | None:
    """Find the current session file.

    Returns:
        Path to session file or None if not found
    """
    # Common session file patterns
    patterns = [
        ".vibe/session.jsonl",
        ".vibe/conversation.jsonl",
        "session.jsonl",
        "conversation.jsonl",
    ]

    for pattern in patterns:
        path = Path(pattern)
        if path.exists():
            return path

    return None


def _auto_create_skills(suggestions: list[Any]) -> None:
    """Auto-create skills from suggestions.

    Args:
        suggestions: List of skill suggestions
    """
    from pathlib import Path

    created = 0
    output_dir = Path(".vibe/skills")
    output_dir.mkdir(parents=True, exist_ok=True)

    for suggestion in suggestions:
        if suggestion.estimated_value not in ("high", "medium"):
            continue

        # Generate skill content
        skill_content = f"""# {suggestion.skill_name}

{suggestion.description}

## Intent

{suggestion.description}

## Trigger When

{suggestion.trigger_pattern}

## Steps

1. Identify the user's need based on the trigger pattern
2. Provide assistance based on the context

## Examples

### Example 1

**User**: {suggestion.trigger_queries[0] if suggestion.trigger_queries else "help me"}

**Action**: Provide assistance based on the query context

---

*Created by VibeSOP Session Analysis*
*Based on {suggestion.frequency} similar queries*
"""

        # Write skill file
        safe_name = suggestion.skill_name.lower().replace(" ", "-").replace("/", "-")
        skill_file = output_dir / f"{safe_name}.md"
        skill_file.write_text(skill_content)

        console.print(f"[green]✓ Created:[/green] {skill_file}")
        created += 1

    if created > 0:
        console.print(f"\n[green]✓ Created {created} skills[/green]")
