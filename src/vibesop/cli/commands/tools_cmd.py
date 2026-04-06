"""VibeSOP tools command - List and manage external tools.

This command lists available external tools and their status.

Usage:
    vibe tools list
    vibe tools verify TOOL
    vibe tools --help

Examples:
    # List all tools
    vibe tools list

    # Verify a tool
    vibe tools verify git

    # Show tool details
    vibe tools show uv
"""

import typer
from rich.console import Console
from rich.table import Table

from vibesop.utils.external_tools import ExternalToolsDetector, ToolStatus

console = Console()


def tools(
    action: str = typer.Argument(..., help="Action: list, show, verify, check"),
    tool: str | None = typer.Argument(None, help="Tool name"),
) -> None:
    """List and manage external tools.

    This command shows available external tools and their
    installation status.

    \b
    Examples:
        # List all tools
        vibe tools list

        # Show tool details
        vibe tools show uv

        # Verify tool availability
        vibe tools verify git

        # Check all tools
        vibe tools check
    """
    detector = ExternalToolsDetector()

    if action == "list":
        _do_list(detector)
    elif action == "show":
        _do_show(detector, tool)
    elif action == "verify":
        _do_verify(detector, tool)
    elif action == "check":
        _do_check(detector)
    else:
        console.print(
            f"[red]✗ Unknown action: {action}[/red]\n"
            f"[dim]Valid actions: list, show, verify, check[/dim]"
        )
        raise typer.Exit(1)


def _do_list(detector: ExternalToolsDetector) -> None:
    """List all tools.

    Args:
        detector: ExternalToolsDetector instance
    """
    console.print(f"\n[bold cyan]🔧 External Tools[/bold cyan]\n{'=' * 40}\n")

    tools_dict = detector.detect_all()

    # Group by status
    available = [t for t in tools_dict.values() if t.status == ToolStatus.AVAILABLE]
    not_available = [t for t in tools_dict.values() if t.status != ToolStatus.AVAILABLE]

    # Show available tools
    if available:
        console.print("[green]✓ Available Tools:[/green]\n")
        for tool in available:
            version = f" ({tool.version})" if tool.version else ""
            console.print(f"  • [cyan]{tool.name}[/cyan]{version}")
        console.print()

    # Show missing tools
    if not_available:
        console.print("[red]✗ Missing Tools:[/red]\n")
        for tool in not_available:
            required = " (required)" if not tool.optional else " (optional)"
            console.print(f"  • {tool.name}{required}")
        console.print()

    # Summary
    console.print(f"[dim]Total: {len(available)}/{len(tools_dict)} tools available[/dim]")


def _do_show(detector: ExternalToolsDetector, tool_name: str | None) -> None:
    """Show tool details.

    Args:
        detector: ExternalToolsDetector instance
        tool_name: Tool name
    """
    if not tool_name:
        console.print("[red]✗ Tool name required[/red]")
        console.print("[dim]Usage: vibe tools show TOOL[/dim]")
        raise typer.Exit(1)

    tool_info = detector.detect_tool(tool_name)

    if not tool_info:
        console.print(f"[red]✗ Unknown tool: {tool_name}[/red]")
        console.print("[dim]Run 'vibe tools list' to see available tools[/dim]")
        raise typer.Exit(1)

    console.print(f"\n[bold cyan]🔧 {tool_info.name}[/bold cyan]\n{'=' * 40}\n")

    # Show details
    status_icon = {
        ToolStatus.AVAILABLE: "✅",
        ToolStatus.NOT_AVAILABLE: "❌",
        ToolStatus.VERSION_MISMATCH: "⚠️ ",
    }.get(tool_info.status, "❓")

    console.print(f"  [dim]Status:[/dim] {status_icon} {tool_info.status.value}")
    console.print(f"  [dim]Command:[/dim] {tool_info.command}")
    console.print(f"  [dim]Required:[/dim] {'No' if tool_info.optional else 'Yes'}")

    if tool_info.path:
        console.print(f"  [dim]Path:[/dim] {tool_info.path}")

    if tool_info.version:
        console.print(f"  [dim]Version:[/dim] {tool_info.version}")

    if tool_info.min_version:
        console.print(f"  [dim]Minimum:[/dim] {tool_info.min_version}")


def _do_verify(detector: ExternalToolsDetector, tool_name: str | None) -> None:
    """Verify a tool.

    Args:
        detector: ExternalToolsDetector instance
        tool_name: Tool name to verify
    """
    if not tool_name:
        console.print("[red]✗ Tool name required[/red]")
        console.print("[dim]Usage: vibe tools verify TOOL[/dim]")
        raise typer.Exit(1)

    console.print(f"[dim]Verifying {tool_name}...[/dim]")

    tool_info = detector.detect_tool(tool_name)

    if not tool_info:
        console.print(f"[red]✗ Unknown tool: {tool_name}[/red]")
        raise typer.Exit(1)

    if tool_info.status == ToolStatus.AVAILABLE:
        console.print(f"[green]✓ {tool_name} is available[/green]")
        if tool_info.version:
            console.print(f"  [dim]Version: {tool_info.version}[/dim]")
    else:
        console.print(f"[red]✗ {tool_name} is not available[/red]")
        console.print(f"  [dim]Status: {tool_info.status.value}[/dim]")
        raise typer.Exit(1)


def _do_check(detector: ExternalToolsDetector) -> None:
    """Check all tools.

    Args:
        detector: ExternalToolsDetector instance
    """
    console.print(f"\n[bold cyan]🔊 Checking Tools[/bold cyan]\n{'=' * 40}\n")

    tools_dict = detector.detect_all()

    # Create table
    table = Table()
    table.add_column("Tool", style="cyan")
    table.add_column("Status")
    table.add_column("Version", style="dim")

    all_ok = True

    for _tool_name, tool_info in tools_dict.items():
        status_icon = {
            ToolStatus.AVAILABLE: "✅",
            ToolStatus.NOT_AVAILABLE: "❌",
            ToolStatus.VERSION_MISMATCH: "⚠️ ",
            ToolStatus.PERMISSION_DENIED: "🔒",
            ToolStatus.UNKNOWN: "❓",
        }.get(tool_info.status, "❓")

        if tool_info.status != ToolStatus.AVAILABLE and not tool_info.optional:
            all_ok = False

        version = tool_info.version or "N/A"

        table.add_row(
            tool_info.name,
            status_icon,
            version,
        )

    console.print(table)

    if all_ok:
        console.print("\n[green]✓ All required tools are available[/green]")
    else:
        console.print("\n[yellow]⚠️  Some required tools are missing[/yellow]")
        console.print("[dim]Run 'vibe toolchain list' for details[/dim]")
        raise typer.Exit(1)
