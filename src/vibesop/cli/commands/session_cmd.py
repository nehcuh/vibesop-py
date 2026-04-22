"""Session management commands for VibeSOP.

This module provides CLI commands for managing session context
and intelligent re-routing.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from vibesop.core.sessions import SessionContext

app = typer.Typer(help="Session management and intelligent re-routing")
console = Console()


@app.command()
def record_tool(
    tool: str = typer.Option(..., "--tool", "-t", help="Tool name"),
    skill: str = typer.Option(None, "--skill", "-s", help="Current skill"),
    context_file: str = typer.Option(
        "~/.vibesop/session-context.json",
        "--context-file",
        "-c",
        help="Path to context file",
    ),
) -> None:
    """Record a tool use event for context tracking.

    This is typically called by hooks, but can be used manually for testing.
    """
    context_file = Path(context_file).expanduser()

    # For now, create a simple session context
    # In production, this would persist state to context_file
    ctx = SessionContext(project_root=Path.cwd())
    ctx.record_tool_use(tool, skill)

    console.print(f"[green]✓[/green] Recorded tool use: {tool} (skill: {skill})")


@app.command()
def check_reroute(
    message: str = typer.Argument(..., help="User message to analyze"),
    current_skill: str = typer.Option(..., "--skill", "-s", help="Current skill"),
    context_file: str = typer.Option(
        "~/.vibesop/session-context.json",
        "--context-file",
        "-c",
        help="Path to context file (legacy, sessions now auto-persist to .vibe/session/)",
    ),
) -> None:
    """Check if re-routing is suggested for a new message.

    This analyzes the conversation context and the new message
    to determine if a skill switch is recommended.
    """
    _ = Path(context_file).expanduser()  # legacy param, kept for CLI compatibility

    ctx = SessionContext.load(project_root=Path.cwd())
    ctx.set_current_skill(current_skill)

    suggestion = ctx.check_reroute_needed(message)

    if suggestion.should_reroute:
        console.print(
            Panel(
                f"[bold yellow]💡 Consider switching skills[/bold yellow]\n\n"
                f"[dim]From:[/dim] {suggestion.current_skill}\n"
                f"[dim]To:[/dim] {suggestion.recommended_skill}\n"
                f"[dim]Confidence:[/dim] {suggestion.confidence:.0%}\n\n"
                f"[dim]Reason:[/dim] {suggestion.reason}",
                title="[bold]Re-routing Suggestion[/bold]",
                border_style="yellow",
            )
        )
    else:
        console.print(
            Panel(
                f"[bold green]✓ Continue with current skill[/bold green]\n\n"
                f"[dim]Current:[/dim] {suggestion.current_skill}\n"
                f"[dim]Reason:[/dim] {suggestion.reason}",
                title="[bold]No Re-route Needed[/bold]",
                border_style="green",
            )
        )


@app.command()
def summary(
    context_file: str = typer.Option(
        "~/.vibesop/session-context.json",
        "--context-file",
        "-c",
        help="Path to context file (legacy, sessions now auto-persist to .vibe/session/)",
    ),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Display session context summary."""
    _ = Path(context_file).expanduser()  # legacy param, kept for CLI compatibility

    ctx = SessionContext.load(project_root=Path.cwd())
    summary = ctx.get_session_summary()

    if json_output:
        console.print(json.dumps(summary, indent=2))
    else:
        console.print("[bold]Session Summary[/bold]\n")

        # Duration
        duration = summary["duration_seconds"]
        duration_str = f"{duration:.0f}s" if duration < 60 else f"{duration / 60:.1f}m"
        console.print(f"Duration: {duration_str}")

        # Current skill
        console.print(f"Current skill: {summary['current_skill'] or 'None'}")

        # Tool usage
        console.print(f"\nTool uses: {summary['tool_use_count']}")

        if summary["tool_breakdown"]:
            console.print("\n[bold]Tool breakdown:[/bold]")
            for tool, count in summary["tool_breakdown"].items():
                console.print(f"  • {tool}: {count}")

        if summary["recent_tools"]:
            console.print("\n[bold]Recent tools:[/bold]")
            for tool_info in summary["recent_tools"]:
                skill_str = f" ({tool_info['skill']})" if tool_info["skill"] else ""
                console.print(f"  • {tool_info['tool']}{skill_str}")


@app.command()
def set_skill(
    skill_id: str = typer.Argument(..., help="Skill identifier"),
    context_file: str = typer.Option(
        "~/.vibesop/session-context.json",
        "--context-file",
        "-c",
        help="Path to context file (legacy, sessions now auto-persist to .vibe/session/)",
    ),
) -> None:
    """Set the current active skill."""
    _ = Path(context_file).expanduser()  # legacy param, kept for CLI compatibility

    ctx = SessionContext.load(project_root=Path.cwd())
    ctx.set_current_skill(skill_id)
    ctx.save()

    console.print(f"[green]✓[/green] Current skill set to: {skill_id}")


@app.command()
def enable_tracking() -> None:
    """Enable session context tracking.

    This sets up the environment for intelligent re-routing.
    """
    # Add to shell profile
    shell_profile = _get_shell_profile()

    if shell_profile is None:
        console.print("[yellow]Could not detect shell profile[/yellow]")
        console.print("Add this to your shell profile:")
        console.print('  export VIBESOP_CONTEXT_TRACKING="true"')
        return

    export_line = 'export VIBESOP_CONTEXT_TRACKING="true"'

    # Check if already exists
    if shell_profile.exists():
        content = shell_profile.read_text()
        if export_line in content:
            console.print("[green]✓[/green] Tracking already enabled in profile")
            return

    # Append to profile
    with shell_profile.open("a") as f:
        f.write(f"\n# VibeSOP session context tracking\n{export_line}\n")

    console.print(f"[green]✓[/green] Added to {shell_profile}")
    console.print("\n[yellow]Restart your shell or run:[/yellow]")
    console.print(f'  source {shell_profile}')


@app.command()
def disable_tracking() -> None:
    """Disable session context tracking."""
    shell_profile = _get_shell_profile()

    if shell_profile is None or not shell_profile.exists():
        console.print("[yellow]Run this to disable for current session:[/yellow]")
        console.print('  unset VIBESOP_CONTEXT_TRACKING')
        return

    # Remove from profile
    content = shell_profile.read_text()
    lines = content.split("\n")

    # Filter out VibeSOP tracking lines
    filtered_lines = [
        line
        for line in lines
        if not (
            "VIBESOP_CONTEXT_TRACKING" in line
            or (line.strip().startswith("#") and "VibeSOP session context" in line)
        )
    ]

    shell_profile.write_text("\n".join(filtered_lines))

    console.print(f"[green]✓[/green] Removed from {shell_profile}")
    console.print("\n[yellow]Restart your shell or run:[/yellow]")
    console.print("  unset VIBESOP_CONTEXT_TRACKING")


def _get_shell_profile() -> Path | None:
    """Detect shell profile path."""
    import os

    shell = os.environ.get("SHELL", "")

    if "zsh" in shell:
        return Path.home() / ".zshrc"
    elif "bash" in shell:
        # Check for .bash_profile or .bashrc
        bash_profile = Path.home() / ".bash_profile"
        bashrc = Path.home() / ".bashrc"
        if bash_profile.exists():
            return bash_profile
        return bashrc

    return None
