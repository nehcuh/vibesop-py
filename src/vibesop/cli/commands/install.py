"""VibeSOP install command - Install skill packs from trusted names or URLs.

This command discovers, analyzes, and installs skill packs using the
unified intelligent installer.

Usage:
    vibe install <NAME|URL>
    vibe install --auto
    vibe install --list
    vibe install superpowers --platform claude-code

Examples:
    # Install a trusted skill pack
    vibe install superpowers

    # Install from any Git URL
    vibe install https://github.com/obra/superpowers

    # Install for a specific platform only
    vibe install superpowers --platform claude-code

    # Auto-install all recommended packs
    vibe install --auto

    # List available/trusted packs
    vibe install --list
"""

import typer
from pathlib import Path
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Table

from vibesop.constants import DEFAULT_AUTO_INSTALL_PACKS, TRUSTED_PACKS
from vibesop.core.skills.external_loader import ExternalSkillLoader
from vibesop.core.skills.storage import SkillStorage
from vibesop.core.skills.trust import TrustStore
from vibesop.installer.pack_installer import PackInstaller

console = Console()

_INSTALL_DOCSTRING_PLATFORM_HELP = (
    "Target platform for skill symlinks (claude-code, kimi-cli, opencode, cursor, pi). "
    "If omitted, installs to all supported platforms."
)


def install(
    name_or_url: str | None = typer.Argument(
        None,
        help="Trusted pack name (superpowers, omx) or Git URL",
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
    platform: str | None = typer.Option(
        None,
        "--platform",
        "-p",
        help=_INSTALL_DOCSTRING_PLATFORM_HELP,
    ),
) -> None:
    """Install skill packs from trusted names or arbitrary Git URLs."""
    # Resolve target platforms (flag > project config > user config > default)
    platforms_list, platforms_source = _resolve_platforms(platform)

    if platforms_source == "default":
        console.print(
            "[dim]No platform preference found — defaulting to claude-code only.[/dim]\n"
            "[dim]To target other agents (kimi-cli, opencode, cursor, pi), run:[/dim]\n"
            "  [cyan]vibe config platforms claude-code,kimi-cli[/cyan]\n"
            "[dim]Or pass --platform <list> per install. Use --platform all for legacy behavior.[/dim]\n"
        )
    elif platforms_source != "cli-flag":
        label = "project" if platforms_source == "project-config" else "user"
        target_str = "all platforms" if platforms_list is None else ", ".join(platforms_list)
        console.print(
            f"[dim]Using {label} config platforms: {target_str}[/dim]\n"
        )

    # List mode
    if list_available:
        _list_available()
        return

    # Auto mode
    if auto:
        _auto_install(force, skip_verify, platforms_list)
        return

    # Manual mode - require name_or_url
    if not name_or_url:
        console.print(
            "[red]✗ No pack name or URL specified[/red]\n"
            "[dim]Examples:[/dim]\n"
            "  [cyan]vibe install superpowers[/cyan]\n"
            "  [cyan]vibe install omx[/cyan]\n"
            "  [cyan]vibe install https://github.com/user/skills[/cyan]\n"
            "\n"
            "[dim]Or use:[/dim]\n"
            "  [cyan]vibe install --auto[/cyan] [dim]to install recommended packs[/dim]\n"
            "  [cyan]vibe install --list[/cyan] [dim]to see available packs[/dim]\n"
        )
        raise typer.Exit(1)

    _install_pack(name_or_url, force, skip_verify, platforms=platforms_list)


def _list_available() -> None:
    """List available skill packs."""
    loader = ExternalSkillLoader()
    supported = loader.get_supported_packs()

    console.print(f"\n[bold cyan]📦 Available Skill Packs[/bold cyan]\n{'=' * 40}\n")

    t = Table()
    t.add_column("Pack", style="cyan")
    t.add_column("Source URL")
    t.add_column("Status", style="bold")

    for name, url in TRUSTED_PACKS.items():
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


def _validate_platform(platform: str | None) -> list[str] | None:
    """Validate and normalize the --platform value.

    Accepts comma-separated values (``--platform claude-code,kimi-cli``) and
    the special sentinel ``all`` (returns ``None`` to signal PackInstaller's
    "install to every platform" path).

    Returns a list of validated platform names, or ``None`` when ``platform``
    is ``None`` (caller should then fall back to config-based resolution).
    """
    if platform is None:
        return None
    valid = SkillStorage.PLATFORM_SKILLS_DIRS.keys()
    raw_items = [p.strip() for p in platform.split(",") if p.strip()]
    if not raw_items:
        return None
    if len(raw_items) == 1 and raw_items[0] == "all":
        return None
    unknown = [p for p in raw_items if p not in valid]
    if unknown:
        console.print(
            f"[red]✗ Unknown platform: {', '.join(unknown)}[/red]\n"
            f"[dim]Valid platforms: {', '.join(sorted(valid))} (or 'all')[/dim]"
        )
        raise typer.Exit(1)
    return raw_items


def _resolve_platforms(
    cli_platform: str | None,
    project_root: Path | None = None,
) -> tuple[list[str] | None, str]:
    """Resolve the install target platforms.

    Order: ``--platform`` flag > project config > user config > built-in default.

    Returns ``(platforms, source)`` where ``platforms`` is a list of validated
    platform names (or ``None`` to signal "all platforms") and ``source`` is
    one of ``"cli-flag"``, ``"project-config"``, ``"user-config"``,
    ``"default"``.
    """
    if cli_platform is not None:
        return _validate_platform(cli_platform), "cli-flag"

    from vibesop.core.config.manager import ConfigManager, ConfigSourcePriority

    manager = ConfigManager(project_root or Path.cwd())
    targets = manager.get_platforms_config().install_targets

    project_src = manager._sources.get(ConfigSourcePriority.PROJECT)
    user_src = manager._sources.get(ConfigSourcePriority.GLOBAL)
    if project_src and "platforms" in project_src.data:
        source = "project-config"
    elif user_src and "platforms" in user_src.data:
        source = "user-config"
    else:
        source = "default"

    if not targets:
        return None, source

    valid = SkillStorage.PLATFORM_SKILLS_DIRS.keys()
    unknown = [p for p in targets if p not in valid]
    if unknown:
        console.print(
            f"[yellow]⚠ Ignoring unknown platform(s) in config: "
            f"{', '.join(unknown)}[/yellow]\n"
            f"[dim]Valid: {', '.join(sorted(valid))}[/dim]"
        )
    resolved = [p for p in targets if p in valid]
    if not resolved:
        return list(valid), "default"
    return resolved, source


def _auto_install(force: bool, skip_verify: bool, platforms: list[str] | None = None) -> None:
    """Auto-install recommended skill packs."""
    console.print(f"\n[bold cyan]🚀 Auto-Installing Recommended Packs[/bold cyan]\n{'=' * 40}\n")

    loader = ExternalSkillLoader()
    supported = loader.get_supported_packs()
    results: dict[str, str] = {}

    for name in DEFAULT_AUTO_INSTALL_PACKS:
        info = supported.get(name, {})
        if info.get("installed") and not force:
            console.print(f"[dim]⊘ {name}: already installed, skipping[/dim]")
            results[name] = "skipped"
            continue

        console.print(f"[dim]Installing {name}...[/dim]")
        result = _install_pack(name, force, skip_verify, quiet=True, platforms=platforms)
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


def _prompt_trust_if_untrusted(
    pack_name: str,
    pack_url: str | None,
    is_url: bool,
    audit_msg: str,
) -> None:
    """Prompt user to trust a pack/source if not already trusted.

    Called after successful installation of a non-standard (URL) pack
    that may have security audit warnings.
    """
    store = TrustStore()

    if is_url and pack_url:
        if store.is_trusted_source(pack_url):
            return
        if "WARN" in audit_msg:
            console.print(
                f"[yellow]Security audit found warnings for [bold]{pack_name}[/bold][/yellow]\n"
                f"[yellow]Source: [bold]{pack_url}[/bold][/yellow]\n"
                f"[dim]Trust this source with:[/dim] [cyan]vibe trust {pack_url}[/cyan]\n"
            )
        elif pack_url not in TRUSTED_PACKS.values():
            console.print(
                f"[dim]New source detected. Trust it with:[/dim] [cyan]vibe trust {pack_url}[/cyan]\n"
            )
    elif pack_url and pack_url not in TRUSTED_PACKS.values():
        if not store.is_trusted_pack(pack_name) and not store.is_trusted_source(pack_url):
            console.print(
                f"[dim]New source detected. Trust it with:[/dim] [cyan]vibe trust {pack_url}[/cyan]\n"
            )


def _install_pack(
    name_or_url: str,
    force: bool,
    skip_verify: bool,
    quiet: bool = False,
    platforms: list[str] | None = None,
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
        pack_name = analyzer.infer_pack_name(name_or_url)
        pack_url = name_or_url
    else:
        pack_name = name_or_url
        pack_url = None  # ExternalSkillLoader will look up TRUSTED_PACKS

    if not quiet:
        source = pack_url or pack_name
        console.print(f"\n[bold cyan]📦 Installing {pack_name}[/bold cyan]\n{'=' * 40}\n")
        console.print(f"[dim]Source:[/dim] {source}\n")
        if platforms:
            console.print(f"[dim]Platform:[/dim] {', '.join(platforms)}\n")

    installer = PackInstaller()
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
        success, msg = installer.install_pack(pack_name, pack_url, platforms=platforms)
    else:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(f"Installing {pack_name}...", total=100)

            # The installer does the heavy lifting; we just show completion
            # since install_pack doesn't expose incremental progress.
            progress.update(task, completed=30, description="Analyzing repository...")
            success, msg = installer.install_pack(pack_name, pack_url, platforms=platforms)
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
                    pack_name, loader.external_paths[0] / pack_name
                )
                if discovered:
                    console.print(
                        f"[green]✓ {len(discovered)} skill(s) discovered and ready[/green]\n"
                    )
                else:
                    console.print("[yellow]⚠ No skills discovered after install[/yellow]\n")

            _prompt_trust_if_untrusted(pack_name, pack_url, is_url, msg)
        return "success"

    if not quiet:
        console.print(f"\n[red]✗ Failed to install {pack_name}[/red]\n")
        for line in msg.split("\n"):
            console.print(f"  [dim]{line}[/dim]")
        console.print()
        raise typer.Exit(1)
    return "failed"
