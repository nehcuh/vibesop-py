"""VibeSOP install command - Install skill packs from trusted names or URLs.

This command discovers, analyzes, and installs skill packs using the
unified intelligent installer.

Usage:
    vibe install <NAME|URL>
    vibe install --auto
    vibe install --list

Examples:
    # Install a trusted skill pack
    vibe install gstack

    # Install from any Git URL
    vibe install https://github.com/obra/superpowers

    # Auto-install all recommended packs
    vibe install --auto

    # List available/trusted packs
    vibe install --list
"""

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Table

from vibesop.core.skills.external_loader import ExternalSkillLoader

console = Console()


def install(
    name_or_url: str | None = typer.Argument(
        None,
        help="Trusted pack name (gstack, superpowers) or Git URL",
    ),
    auto: bool = typer.Option(
        False,
        "--auto",
        "-a",
        help="Auto-install recommended skill packs",
    ),
    list_available: bool = typer.Option(
        False,
        "--list",
        "-l",
        help="List available skill packs",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force reinstall even if already installed",
    ),
    skip_verify: bool = typer.Option(
        False,
        "--skip-verify",
        help="Skip post-install verification",
    ),
) -> None:
    """Install skill packs from trusted names or arbitrary Git URLs."""
    # List mode
    if list_available:
        _list_available()
        return

    # Auto mode
    if auto:
        _auto_install(force, skip_verify)
        return

    # Manual mode - require name_or_url
    if not name_or_url:
        console.print(
            "[red]✗ No pack name or URL specified[/red]\n"
            "[dim]Examples:[/dim]\n"
            "  [cyan]vibe install gstack[/cyan]\n"
            "  [cyan]vibe install superpowers[/cyan]\n"
            "  [cyan]vibe install https://github.com/user/skills[/cyan]\n"
            "\n"
            "[dim]Or use:[/dim]\n"
            "  [cyan]vibe install --auto[/cyan] [dim]to install recommended packs[/dim]\n"
            "  [cyan]vibe install --list[/cyan] [dim]to see available packs[/dim]\n"
        )
        raise typer.Exit(1)

    _install_pack(name_or_url, force, skip_verify)


def _list_available() -> None:
    """List available skill packs."""
    loader = ExternalSkillLoader()
    trusted = loader.TRUSTED_PACKS
    supported = loader.get_supported_packs()

    console.print(f"\n[bold cyan]📦 Available Skill Packs[/bold cyan]\n{'=' * 40}\n")

    t = Table()
    t.add_column("Pack", style="cyan")
    t.add_column("Source URL")
    t.add_column("Status", style="bold")

    for name, url in trusted.items():
        info = supported.get(name, {})
        if info.get("installed"):
            status = "[green]✓ Installed[/green]"
        else:
            status = "[dim]⊘ Not installed[/dim]"
        t.add_row(name, url, status)

    console.print(t)
    console.print(
        "\n[dim]Install a pack:[/dim]\n"
        "  [cyan]vibe install <pack-name>[/cyan]\n"
        "  [cyan]vibe install <git-url>[/cyan]\n"
    )


def _auto_install(force: bool, skip_verify: bool) -> None:
    """Auto-install recommended skill packs."""
    console.print(
        f"\n[bold cyan]🚀 Auto-Installing Recommended Packs[/bold cyan]\n{'=' * 40}\n"
    )

    loader = ExternalSkillLoader()
    trusted = loader.TRUSTED_PACKS
    supported = loader.get_supported_packs()
    results: dict[str, str] = {}

    for name in trusted:
        info = supported.get(name, {})
        if info.get("installed") and not force:
            console.print(f"[dim]⊘ {name}: already installed, skipping[/dim]")
            results[name] = "skipped"
            continue

        console.print(f"[dim]Installing {name}...[/dim]")
        result = _install_pack(name, force, skip_verify, quiet=True)
        results[name] = result

    # Summary
    console.print("\n[bold]Summary[/bold]\n")
    for name, result in results.items():
        if result == "success":
            console.print(f"  [green]✓ {name}[/green]")
        elif result == "skipped":
            console.print(f"  [dim]⊘ {name} (already installed)[/dim]")
        else:
            console.print(f"  [red]✗ {name}[/red]")
    console.print()


def _install_pack(
    name_or_url: str,
    force: bool,
    skip_verify: bool,
    quiet: bool = False,
) -> str:
    """Install a skill pack by name or URL.

    Returns:
        "success", "failed", or "skipped"
    """
    # Determine if this is a URL or a pack name
    is_url = name_or_url.startswith(("http://", "https://", "git@"))

    if is_url:
        # Infer pack name from URL
        from vibesop.installer.analyzer import RepoAnalyzer

        analyzer = RepoAnalyzer()
        pack_name = analyzer._infer_pack_name(name_or_url)
        pack_url = name_or_url
    else:
        pack_name = name_or_url
        pack_url = None  # ExternalSkillLoader will look up TRUSTED_PACKS

    if not quiet:
        source = pack_url or pack_name
        console.print(f"\n[bold cyan]📦 Installing {pack_name}[/bold cyan]\n{'=' * 40}\n")
        console.print(f"[dim]Source:[/dim] {source}\n")

    loader = ExternalSkillLoader()

    # Check if already installed (unless force)
    if not force and pack_url is None:
        supported = loader.get_supported_packs()
        if supported.get(pack_name, {}).get("installed"):
            if not quiet:
                console.print(
                    f"[yellow]⚠ {pack_name} is already installed[/yellow]\n"
                    "[dim]Use --force to reinstall[/dim]\n"
                )
            return "skipped"

    # Execute installation with progress bar
    if quiet:
        success, msg = loader.install_pack(pack_name, pack_url)
    else:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(f"Installing {pack_name}...", total=100)

            # The loader does the heavy lifting; we just show completion
            # since install_pack doesn't expose incremental progress.
            progress.update(task, completed=30, description="Analyzing repository...")
            success, msg = loader.install_pack(pack_name, pack_url)
            progress.update(task, completed=100, description="Installation complete")

    if success:
        if not quiet:
            console.print(f"\n[green]✓ {pack_name} installed successfully![/green]\n")
            for line in msg.split("\n"):
                console.print(f"[dim]{line}[/dim]")
            console.print()

            if not skip_verify:
                console.print("[dim]Verifying installation...[/dim]")
                discovered = loader.discover_from_pack(
                    pack_name, loader._external_paths[0] / pack_name
                )
                if discovered:
                    console.print(
                        f"[green]✓ {len(discovered)} skill(s) discovered and ready[/green]\n"
                    )
                else:
                    console.print("[yellow]⚠ No skills discovered after install[/yellow]\n")
        return "success"

    if not quiet:
        console.print(f"\n[red]✗ Failed to install {pack_name}[/red]\n")
        for line in msg.split("\n"):
            console.print(f"  [dim]{line}[/dim]")
        console.print()
    return "failed"
