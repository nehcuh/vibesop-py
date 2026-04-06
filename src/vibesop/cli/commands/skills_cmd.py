"""VibeSOP skills command - Manage skill storage.

Usage:
    vibe skills list
    vibe skills install <skill_id>
    vibe skills link <skill_id> <platform>
    vibe skills unlink <skill_id> <platform>
    vibe skills remove <skill_id>
    vibe skills sync
"""

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from vibesop.core.skills import SkillStorage

console = Console()


def list(
    all_: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="List all skills including details",
    ),
    platform: str | None = typer.Option(
        None,
        "--platform",
        "-p",
        help="Filter by platform",
    ),
) -> None:
    """List installed skills.

    \b
    Examples:
        # List all skills in central storage
        vibe skills list

        # Show detailed information
        vibe skills list --all

        # Show skills for a specific platform
        vibe skills list --platform claude-code
    """
    storage = SkillStorage()

    if platform:
        # Show skills linked to a specific platform
        if platform not in storage.PLATFORM_SKILLS_DIRS:
            console.print(f"[red]✗ Unknown platform: {platform}[/red]")
            raise typer.Exit(1)

        linked = storage.get_linked_skills(platform)
        console.print(f"\n[bold]Skills linked to {platform}:[/bold]")
        console.print(f"  {len(linked)} skills\n")

        if linked:
            for skill_id in linked:
                is_link = (storage.PLATFORM_SKILLS_DIRS[platform] / skill_id).is_symlink()
                link_type = "[cyan]→[/cyan]" if is_link else "[dim]cp[/dim]"
                console.print(f"  {link_type} {skill_id}")

    elif all_:
        # Show detailed information
        skills = storage.list_skills()

        table = Table(title="Installed Skills")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Version", style="yellow")
        table.add_column("Source", style="dim")
        table.add_column("Installed", style="dim")

        for skill_id, manifest in skills.items():
            source_str = f"{manifest.source.type}"
            if manifest.source.version:
                source_str += f"@{manifest.source.version}"

            table.add_row(
                skill_id,
                manifest.name,
                manifest.version,
                source_str,
                manifest.installed_at[:10],
            )

        console.print(table)
        console.print(f"\n[dim]Total: {len(skills)} skills[/dim]")

    else:
        # Simple list
        skills = storage.list_skills()
        console.print("\n[bold]Installed Skills:[/bold]")
        console.print(f"  {len(skills)} skills\n")

        for skill_id in skills:
            console.print(f"  [cyan]{skill_id}[/cyan]")


def install(
    skill_id: str = typer.Argument(..., help="Skill identifier"),
    source: Path | None = typer.Option(  # noqa: B008
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

    # Determine source
    if url:
        console.print(f"[dim]Downloading {skill_id} from {url}...[/dim]")
        success, msg = storage.install_from_remote(skill_id, url, overwrite)
    elif source:
        success, msg = storage.install_skill(skill_id, source, overwrite)
    else:
        # Try to find in project
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

    # Check if skill is linked to any platforms
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
    project_root: Path = typer.Option(  # noqa: B008
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


def status() -> None:
    """Show skill storage status."""
    storage = SkillStorage()

    # Check central storage
    central_exists = storage.CENTRAL_SKILLS_DIR.exists()
    central_count = len(storage.list_skills())

    # Collect platform info
    platform_info = {}
    for platform_name, platform_dir in storage.PLATFORM_SKILLS_DIRS.items():
        if platform_dir.exists():
            linked = storage.get_linked_skills(platform_name)
            platform_info[platform_name] = {
                "exists": True,
                "linked": len(linked),
                "symlinks": sum(1 for s in platform_dir.iterdir() if s.is_symlink())
                if platform_dir.exists()
                else 0,
            }
        else:
            platform_info[platform_name] = {
                "exists": False,
                "linked": 0,
                "symlinks": 0,
            }

    # Display status
    console.print("\n[bold]Skill Storage Status[/bold]\n")

    # Central storage
    central_status = "[green]✓[/green]" if central_exists else "[red]✗[/red]"
    console.print(f"{central_status} Central Storage: {storage.CENTRAL_SKILLS_DIR}")
    console.print(f"    [dim]Skills installed: {central_count}[/dim]\n")

    # Platform directories
    console.print("[bold]Platform Directories:[/bold]\n")
    for platform_name, info in platform_info.items():
        if info["exists"]:
            status = f"[green]{info['linked']} linked[/green]"
            symlink_count = info["symlinks"]
            console.print(f"  {platform_name}: {status} ({symlink_count} symlinks)")
        else:
            console.print(f"  {platform_name}: [dim]not created[/dim]")

    console.print("")
