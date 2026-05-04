# pyright: ignore[reportPossiblyUnboundVariable, reportUnnecessaryComparison]
"""CRUD operations: install, link, unlink, remove, sync."""

from pathlib import Path

import typer
from rich.console import Console

from vibesop.core.skills import SkillStorage

console = Console()


def install(
    skill_id: str = typer.Argument(..., help="Skill identifier"),
    source: Path | None = typer.Option(
        None,
        "--source",
        "-s",
        help="Local path to skill directory",
    ),
    url: str | None = typer.Option(
        None,
        "--url",
        "-u",
        help="Remote URL to download skill from",
    ),
    overwrite: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite if already exists",
    ),
) -> None:
    """Install a skill to central storage.

    \b
    Examples:
        # Install from project
        vibe skills install systematic-debugging

        # Install from local path
        vibe skills install my-skill --source ./skills/my-skill

        # Install from remote URL
        vibe skills install my-skill --url https://example.com/skill.tar.gz

        # Overwrite existing
        vibe skills install systematic-debugging --force
    """
    storage = SkillStorage()

    if url:
        console.print(f"[dim]Downloading {skill_id} from {url}...[/dim]")
        success, msg = storage.install_from_remote(skill_id, url, overwrite)
    elif source:
        success, msg = storage.install_skill(skill_id, source, overwrite)
    else:
        project_skills = Path("core") / "skills" / skill_id
        if project_skills.exists():
            success, msg = storage.install_skill(skill_id, project_skills, overwrite)
        else:
            console.print(f"[red]✗ Skill not found in project: {skill_id}[/red]")
            console.print("[dim]Use --source or --url to specify location[/dim]")
            raise typer.Exit(1)

    if success:
        console.print(f"[green]✓ {msg}[/green]")
    else:
        console.print(f"[red]✗ {msg}[/red]")
        raise typer.Exit(1)


def link(
    skill_id: str = typer.Argument(..., help="Skill identifier"),
    platform: str = typer.Argument(..., help="Target platform"),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite existing link",
    ),
) -> None:
    """Link a skill to a platform.

    Creates a symlink from the platform's skills directory to the
    central storage location.

    \b
    Examples:
        # Link skill to claude-code
        vibe skills link systematic-debugging claude-code

        # Force overwrite existing
        vibe skills link systematic-debugging claude-code --force
    """
    storage = SkillStorage()

    success, msg = storage.link_to_platform(skill_id, platform, force)

    if success:
        console.print(f"[green]✓ {msg}[/green]")
    else:
        console.print(f"[red]✗ {msg}[/red]")
        raise typer.Exit(1)


def unlink(
    skill_id: str = typer.Argument(..., help="Skill identifier"),
    platform: str = typer.Argument(..., help="Target platform"),
) -> None:
    """Unlink a skill from a platform.

    Removes the symlink but keeps the skill in central storage.

    \b
    Examples:
        vibe skills unlink systematic-debugging claude-code
    """
    storage = SkillStorage()

    success, msg = storage.unlink_from_platform(skill_id, platform)

    if success:
        console.print(f"[green]✓ {msg}[/green]")
    else:
        console.print(f"[red]✗ {msg}[/red]")
        raise typer.Exit(1)


def remove(
    skill_id: str = typer.Argument(..., help="Skill identifier"),
    unlink_all: bool = typer.Option(
        False,
        "--unlink-all",
        "-u",
        help="Also remove from all platforms",
    ),
) -> None:
    """Remove a skill from central storage.

    WARNING: This will delete the skill from central storage.

    \b
    Examples:
        # Remove from central storage (if not linked)
        vibe skills remove old-skill

        # Remove and unlink from all platforms
        vibe skills remove old-skill --unlink-all
    """
    storage = SkillStorage()

    linked_platforms = []
    for platform_name in storage.PLATFORM_SKILLS_DIRS:
        platform_path = storage.PLATFORM_SKILLS_DIRS[platform_name] / skill_id
        if platform_path.exists():
            linked_platforms.append(platform_name)

    if linked_platforms and not unlink_all:
        console.print(f"[yellow]⚠ Skill is linked to: {', '.join(linked_platforms)}[/yellow]")
        console.print("[dim]Use --unlink-all to remove from all platforms[/dim]")
        console.print("[dim]Or unlink manually first:[/dim]")
        for platform_name in linked_platforms:
            console.print(f"  [dim]vibe skills unlink {skill_id} {platform_name}[/dim]")
        raise typer.Exit(1)

    success, msg = storage.remove_skill(skill_id, unlink_all=True)

    if success:
        console.print(f"[green]✓ {msg}[/green]")
    else:
        console.print(f"[red]✗ {msg}[/red]")
        raise typer.Exit(1)


def sync(
    platform: str = typer.Argument(..., help="Target platform"),
    project_root: Path = typer.Option(
        Path(),
        "--root",
        "-r",
        help="Project root directory",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite existing links",
    ),
) -> None:
    """Sync all project skills to a platform.

    Installs all skills from core/skills/ to central storage
    and creates symlinks for the specified platform.

    \b
    Examples:
        # Sync to claude-code
        vibe skills sync claude-code

        # Sync from different project root
        vibe skills sync claude-code --root /path/to/vibesop

        # Force overwrite
        vibe skills sync claude-code --force
    """
    from rich.progress import Progress

    storage = SkillStorage()

    with Progress("[progress.bar.default]{}".format(" {task.description}")) as progress:
        task = progress.add_task(
            f"Syncing skills to {platform}",
            total=100,
        )

        installed, linked, _messages = storage.sync_project_skills(
            project_root=project_root,
            platform=platform,
            force=force,
        )

        progress.update(task, completed=100)

    console.print("\n[green]✓ Sync complete![/green]")
    console.print(f"  [dim]Installed:[/dim] {installed} skills")
    console.print(f"  [dim]Linked:[/dim] {linked} skills")
