"""VibeSOP toolchain command - Manage development toolchain.

This command manages the development tools used by VibeSOP
such as uv, ruff, pyright, etc.

Usage:
    vibe toolchain list
    vibe toolchain verify TOOL
    vibe toolchain install TOOL
    vibe toolchain --help

Examples:
    # List all tools
    vibe toolchain list

    # Verify a tool
    vibe toolchain verify uv

    # Install a tool
    vibe toolchain install uv
"""

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from vibesop.utils.external_tools import ExternalToolsDetector, ToolStatus

console = Console()


def toolchain(
    action: str = typer.Argument(..., help="Action: list, verify, install, status"),
    tool: Optional[str] = typer.Argument(None, help="Tool name"),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force installation even if already installed",
    ),
) -> None:
    """Manage development toolchain.

    This command manages the development tools required by VibeSOP
    such as uv, ruff, pyright, etc.

    \b
    Examples:
        # List all tools
        vibe toolchain list

        # Check all tools status
        vibe toolchain status

        # Verify a specific tool
        vibe toolchain verify uv

        # Install a tool
        vibe toolchain install uv
    """
    detector = ExternalToolsDetector()

    if action == "list":
        _do_list(detector)
    elif action == "status":
        _do_status(detector)
    elif action == "verify":
        _do_verify(detector, tool)
    elif action == "install":
        _do_install(detector, tool, force)
    else:
        console.print(
            f"[red]✗ Unknown action: {action}[/red]\n"
            f"[dim]Valid actions: list, status, verify, install[/dim]"
        )
        raise typer.Exit(1)


def _do_list(detector: ExternalToolsDetector) -> None:
    """List all known tools.

    Args:
        detector: ExternalToolsDetector instance
    """
    console.print(
        f"\n[bold cyan]🔧 Development Tools[/bold cyan]"
        f"\n{'=' * 40}\n"
    )

    tools_dict = detector.detect_all()

    # Create table
    table = Table()
    table.add_column("Tool", style="cyan")
    table.add_column("Command")
    table.add_column("Status")
    table.add_column("Required")

    for tool_name, tool_info in tools_dict.items():
        status_color = "green" if tool_info.status == ToolStatus.AVAILABLE else "red"
        status = tool_info.status.value
        required = "Yes" if not tool_info.optional else "No"

        table.add_row(
            tool_info.name,
            tool_info.command,
            f"[{status_color}]{status}[/{status_color}]",
            required,
        )

    console.print(table)

    # Summary
    available = sum(1 for t in tools_dict.values() if t.status == ToolStatus.AVAILABLE)
    console.print(f"\n[dim]Available: {available}/{len(tools_dict)}[/dim]")


def _do_status(detector: ExternalToolsDetector) -> None:
    """Show status of all tools.

    Args:
        detector: ExternalToolsDetector instance
    """
    console.print(
        f"\n[bold cyan]🔊 Toolchain Status[/bold cyan]"
        f"\n{'=' * 40}\n"
    )

    tools_dict = detector.detect_all()

    for tool_name, tool_info in tools_dict.items():
        status_icon = {
            ToolStatus.AVAILABLE: "✅",
            ToolStatus.NOT_AVAILABLE: "❌",
            ToolStatus.VERSION_MISMATCH: "⚠️ ",
            ToolStatus.PERMISSION_DENIED: "🔒",
            ToolStatus.UNKNOWN: "❓",
        }.get(tool_info.status, "❓")

        status_text = f"{status_icon} {tool_info.name}"

        if tool_info.status == ToolStatus.AVAILABLE:
            version = tool_info.version or "unknown"
            console.print(f"[green]{status_text}[/green] - {version}")
        elif tool_info.status == ToolStatus.VERSION_MISMATCH:
            console.print(f"[yellow]{status_text}[/yellow] - version mismatch")
        elif tool_info.status == ToolStatus.NOT_AVAILABLE:
            if tool_info.optional:
                console.print(f"[dim]{status_text}[/dim] (optional)")
            else:
                console.print(f"[red]{status_text}[/red] (required)")
        else:
            console.print(f"{status_text} - {tool_info.status.value}")


def _do_verify(detector: ExternalToolsDetector, tool_name: str | None) -> None:
    """Verify a specific tool.

    Args:
        detector: ExternalToolsDetector instance
        tool_name: Tool to verify
    """
    if not tool_name:
        console.print("[red]✗ Tool name required[/red]")
        console.print("[dim]Usage: vibe toolchain verify TOOL[/dim]")
        raise typer.Exit(1)

    tool_info = detector.detect_tool(tool_name)

    if not tool_info:
        console.print(f"[red]✗ Unknown tool: {tool_name}[/red]")
        console.print("[dim]Run 'vibe toolchain list' to see available tools[/dim]")
        raise typer.Exit(1)

    console.print(
        f"\n[bold]Tool: {tool_info.name}[/bold]\n"
        f"  Status: {tool_info.status.value}\n"
    )

    if tool_info.path:
        console.print(f"  Path: {tool_info.path}")

    if tool_info.version:
        console.print(f"  Version: {tool_info.version}")

    if tool_info.min_version:
        console.print(f"  Minimum: {tool_info.min_version}")

    if tool_info.status == ToolStatus.AVAILABLE:
        console.print("\n[green]✓ Tool is ready[/green]")
    else:
        console.print(f"\n[dim]Run 'vibe toolchain install {tool_name}' to install[/dim]")


def _do_install(
    detector: ExternalToolsDetector,
    tool_name: str | None,
    force: bool,
) -> None:
    """Install a tool.

    Args:
        detector: ExternalToolsDetector instance
        tool_name: Tool to install
        force: Force reinstallation
    """
    if not tool_name:
        console.print("[red]✗ Tool name required[/red]")
        console.print("[dim]Usage: vibe toolchain install TOOL[/dim]")
        raise typer.Exit(1)

    console.print(f"[dim]Installing {tool_name}...[/dim]")

    # Provide installation instructions based on tool
    install_commands = {
        "uv": "curl -LsSf https://astral.sh/uv/install.sh | sh",
        "ruff": "pip install ruff",
        "pyright": "npm install -g pyright",
        "node": "Visit https://nodejs.org/",
        "git": "Visit https://git-scm.com/",
    }

    command = install_commands.get(tool_name)

    if command:
        console.print(
            f"\n[dim]To install {tool_name}, run:[/dim]\n"
            f"  [cyan]{command}[/cyan]\n"
        )
    else:
        console.print(f"[dim]No automatic installation available for {tool_name}[/dim]")
