"""VibeSOP config command - Configuration management."""

from pathlib import Path
from typing import Any

import typer
import yaml
from rich.console import Console
from rich.panel import Panel

from vibesop.core.skills.storage import SkillStorage

console = Console()


def config(
    semantic: bool = typer.Option(
        False,
        "--semantic",
        "-s",
        help="Show semantic matching configuration (deprecated)",
    ),
) -> None:
    """Manage VibeSOP configuration.

    \\b
    Examples:
        # Show general configuration
        vibe config
    """
    if semantic:
        console.print(
            Panel(
                "[bold yellow]⚠️ Semantic module has been removed in v4.0.[/bold yellow]\n\n"
                "Semantic matching is now handled by core/matching/ module.\n"
                "The dedicated semantic CLI has been deprecated.",
                title="[bold]Deprecated[/bold]",
                border_style="yellow",
            )
        )
        return

    _show_general_config()


def _show_general_config() -> None:
    """Show general VibeSOP configuration."""
    from vibesop import __version__

    console.print(
        Panel(
            f"[bold]VibeSOP[/bold] Configuration\n\n"
            f"Version: {__version__}\n"
            f"Python: 3.12+\n\n"
            f"[bold]Matching:[/bold]\n"
            f"  Keyword, TF-IDF, Fuzzy (built-in)\n\n"
            f"[bold]For skill management, use:[/bold]\n"
            f"  vibe skills list\n"
            f"  vibe skills status",
            title="[bold]Configuration[/bold]",
            border_style="blue",
        )
    )


def platforms(
    values: list[str] = typer.Argument(
        None,
        help="Platform names to set (e.g., claude-code kimi-cli). Omit to show current.",
    ),
    project: bool = typer.Option(
        False,
        "--project",
        help="Write to project-level config (<project>/.vibe/config.yaml) instead of user-level.",
    ),
    clear: bool = typer.Option(
        False,
        "--clear",
        help="Remove the platforms key from the config (revert to default).",
    ),
) -> None:
    """Show or set which AI agent platforms receive skill installs.

    \b
    Examples:
        # Show currently resolved platforms and where they came from
        vibe config platforms

        # Set user-level preference (applies across all projects)
        vibe config platforms claude-code kimi-cli

        # Set project-level preference (overrides user-level)
        vibe config platforms claude-code --project

        # Clear user-level preference (fall back to default)
        vibe config platforms --clear

        # Clear project-level preference
        vibe config platforms --clear --project
    """
    from vibesop.cli.commands._utils import resolve_platforms

    valid_platforms = set(SkillStorage.PLATFORM_SKILLS_DIRS.keys())

    if clear:
        target_path = _config_path(project)
        if not target_path.exists():
            console.print(f"[dim]No config at {target_path} — nothing to clear.[/dim]")
            return
        existing = _load_yaml(target_path)
        platforms_section = existing.get("platforms")
        if isinstance(platforms_section, dict) and "install_targets" in platforms_section:
            del platforms_section["install_targets"]
            if not platforms_section:
                del existing["platforms"]
            _dump_yaml(target_path, existing)
            console.print(f"[green]✓ Cleared platforms from {target_path}[/green]")
        else:
            console.print(f"[dim]No platforms key in {target_path} — nothing to clear.[/dim]")
        return

    if not values:
        resolved, source = resolve_platforms(None, Path.cwd())
        label = "all platforms" if resolved is None else ", ".join(resolved)
        console.print(
            Panel(
                f"[bold]Resolved platforms:[/bold] {label}\n"
                f"[bold]Source:[/bold] {source}\n\n"
                f"[dim]User config:[/dim]    {_config_path(False)}\n"
                f"[dim]Project config:[/dim] {_config_path(True)}\n\n"
                f"[dim]Precedence: --platform flag > project config > user config > default[/dim]",
                title="[bold]Platforms[/bold]",
                border_style="blue",
            )
        )
        return

    cleaned: list[str] = []
    for v in values:
        if "," in v:
            cleaned.extend(p.strip() for p in v.split(",") if p.strip())
        else:
            cleaned.append(v.strip())
    unknown = [p for p in cleaned if p not in valid_platforms]
    if unknown:
        console.print(
            f"[red]✗ Unknown platform(s): {', '.join(unknown)}[/red]\n"
            f"[dim]Valid: {', '.join(sorted(valid_platforms))}[/dim]"
        )
        raise typer.Exit(1)

    target_path = _config_path(project)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    existing = _load_yaml(target_path)
    platforms_section = existing.get("platforms")
    if not isinstance(platforms_section, dict):
        platforms_section = {}
        existing["platforms"] = platforms_section
    platforms_section["install_targets"] = cleaned
    _dump_yaml(target_path, existing)

    label = "project" if project else "user"
    console.print(
        f"[green]✓ {label.capitalize()} platforms set to: {', '.join(cleaned)}[/green]\n"
        f"[dim]Written to: {target_path}[/dim]"
    )


def _config_path(project: bool) -> Path:
    if project:
        return Path.cwd() / ".vibe" / "config.yaml"
    return Path.home() / ".vibe" / "config.yaml"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        from vibesop.utils.encoding import read_text_with_fallback

        data = yaml.safe_load(read_text_with_fallback(path)) or {}
        return data if isinstance(data, dict) else {}
    except yaml.YAMLError as e:
        console.print(f"[red]✗ Failed to parse {path}: {e}[/red]")
        raise typer.Exit(1) from e


def _dump_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, default_flow_style=False)
