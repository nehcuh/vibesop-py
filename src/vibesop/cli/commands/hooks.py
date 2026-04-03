"""VibeSOP hooks command - Manage platform hooks.

This command provides functionality for managing platform-specific hooks
that trigger at key points during AI sessions.

Usage:
    vibe hooks install PLATFORM
    vibe hooks uninstall PLATFORM
    vibe hooks verify PLATFORM
    vibe hooks --help

Examples:
    # Install hooks for Claude Code
    vibe hooks install claude-code

    # Uninstall hooks
    vibe hooks uninstall claude-code

    # Verify hook status
    vibe hooks verify claude-code
"""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from vibesop.installer.installer import VibeSOPInstaller

console = Console()


def hooks(
    action: str = typer.Argument(
        "install",
        help="Action: install, uninstall, verify, status",
    ),
    platform: Optional[str] = typer.Argument(
        None,
        help="Target platform (claude-code, opencode)",
        metavar="PLATFORM",
    ),
) -> None:
    """Manage platform hooks.

    This command allows you to install, uninstall, and verify
    platform-specific hooks that trigger at key points during
    AI sessions.

    \b
    Examples:
        # Install hooks for Claude Code
        vibe hooks install claude-code

        # Uninstall hooks
        vibe hooks uninstall claude-code

        # Verify hook status
        vibe hooks verify claude-code

        # Show status for all platforms
        vibe hooks status
    """
    installer = VibeSOPInstaller()

    if action == "install":
        _do_install(installer, platform)
    elif action == "uninstall":
        _do_uninstall(installer, platform)
    elif action == "verify":
        _do_verify(installer, platform)
    elif action == "status":
        _do_status(installer)
    else:
        console.print(
            f"[red]✗ Unknown action: {action}[/red]\n"
            f"[dim]Valid actions: install, uninstall, verify, status[/dim]"
        )
        raise typer.Exit(1)


def _do_install(installer: VibeSOPInstaller, platform: Optional[str]) -> None:
    """Install hooks for a platform.

    Args:
        installer: VibeSOPInstaller instance
        platform: Target platform (None = all platforms)
    """
    # Determine platforms to install
    platforms = installer.list_platforms()
    platform_names = [p["name"] for p in platforms]

    if platform:
        if platform not in platform_names:
            console.print(
                f"[red]✗ Unknown platform: {platform}[/red]\n"
                f"[dim]Available platforms: {', '.join(platform_names)}[/dim]"
            )
            raise typer.Exit(1)
        target_platforms = [platform]
    else:
        # Default to claude-code if no platform specified
        target_platforms = ["claude-code"]

    for plat in target_platforms:
        console.print(
            f"\n[bold cyan]🔧 Installing hooks for {plat}[/bold cyan]"
            f"\n{'=' * 40}\n"
        )

        # Get platform config directory
        platform_info = next(p for p in platforms if p["name"] == plat)
        config_dir = Path(platform_info["config_dir"]).expanduser()

        console.print(f"[dim]Target directory: {config_dir}[/dim]\n")

        # Install hooks
        from vibesop.hooks import HookInstaller, HookPoint

        hook_installer = HookInstaller()
        results = hook_installer.install_hooks(plat, config_dir)

        if not results:
            console.print("[yellow]⚠ No hooks defined for this platform[/yellow]")
            return

        # Display results
        installed = [name for name, status in results.items() if status]
        failed = [name for name, status in results.items() if not status]

        if installed:
            console.print(f"[green]✓ Installed {len(installed)} hooks:[/green]")
            for hook_name in installed:
                hook_path = config_dir / "hooks" / f"{hook_name}.sh"
                console.print(f"  • {hook_name} → {hook_path}")

        if failed:
            console.print(f"\n[red]✗ Failed to install {len(failed)} hooks:[/red]")
            for hook_name in failed:
                console.print(f"  • {hook_name}")

        if installed and not failed:
            console.print(f"\n[green]✓ All hooks installed successfully![/green]")
        elif installed:
            console.print(f"\n[yellow]⚠ Partial installation: {len(installed)}/{len(results)}[/yellow]")
        else:
            console.print(f"\n[red]✗ Hook installation failed[/red]")
            raise typer.Exit(1)


def _do_uninstall(installer: VibeSOPInstaller, platform: Optional[str]) -> None:
    """Uninstall hooks for a platform.

    Args:
        installer: VibeSOPInstaller instance
        platform: Target platform (None = all platforms)
    """
    # Determine platforms to uninstall
    platforms = installer.list_platforms()
    platform_names = [p["name"] for p in platforms]

    if platform:
        if platform not in platform_names:
            console.print(
                f"[red]✗ Unknown platform: {platform}[/red]\n"
                f"[dim]Available platforms: {', '.join(platform_names)}[/dim]"
            )
            raise typer.Exit(1)
        target_platforms = [platform]
    else:
        # Default to all platforms if no platform specified
        target_platforms = platform_names

    for plat in target_platforms:
        console.print(
            f"\n[bold cyan]🗑️  Uninstalling hooks for {plat}[/bold cyan]"
            f"\n{'=' * 40}\n"
        )

        # Get platform config directory
        platform_info = next(p for p in platforms if p["name"] == plat)
        config_dir = Path(platform_info["config_dir"]).expanduser()

        console.print(f"[dim]Target directory: {config_dir}[/dim]\n")

        # Uninstall hooks
        from vibesop.hooks import HookInstaller

        hook_installer = HookInstaller()
        results = hook_installer.uninstall_hooks(plat, config_dir)

        if not results:
            console.print("[yellow]⚠ No hooks to uninstall for this platform[/yellow]")
            return

        # Display results
        removed = [name for name, status in results.items() if status]
        failed = [name for name, status in results.items() if not status]

        if removed:
            console.print(f"[green]✓ Removed {len(removed)} hooks:[/green]")
            for hook_name in removed:
                console.print(f"  • {hook_name}")

        if failed:
            console.print(f"\n[red]✗ Failed to remove {len(failed)} hooks:[/red]")
            for hook_name in failed:
                console.print(f"  • {hook_name}")

        if removed and not failed:
            console.print(f"\n[green]✓ All hooks uninstalled successfully![/green]")
        elif removed:
            console.print(f"\n[yellow]⚠ Partial removal: {len(removed)}/{len(results)}[/yellow]")
        else:
            console.print(f"\n[red]✗ Hook uninstallation failed[/red]")


def _do_verify(installer: VibeSOPInstaller, platform: Optional[str]) -> None:
    """Verify hooks for a platform.

    Args:
        installer: VibeSOPInstaller instance
        platform: Target platform (None = all platforms)
    """
    # Determine platforms to verify
    platforms = installer.list_platforms()
    platform_names = [p["name"] for p in platforms]

    if platform:
        if platform not in platform_names:
            console.print(
                f"[red]✗ Unknown platform: {platform}[/red]\n"
                f"[dim]Available platforms: {', '.join(platform_names)}[/dim]"
            )
            raise typer.Exit(1)
        target_platforms = [platform]
    else:
        # Default to all platforms if no platform specified
        target_platforms = platform_names

    for plat in target_platforms:
        console.print(
            f"\n[bold cyan]🔍 Verifying hooks for {plat}[/bold cyan]"
            f"\n{'=' * 40}\n"
        )

        # Get platform config directory
        platform_info = next(p for p in platforms if p["name"] == plat)
        config_dir = Path(platform_info["config_dir"]).expanduser()

        # Verify installation
        verify_result = installer.verify(plat)

        if not verify_result["installed"]:
            console.print("[red]✗ Platform not installed[/red]")
            continue

        # Check hooks
        from vibesop.hooks import HookInstaller

        hook_installer = HookInstaller()
        hook_results = hook_installer.verify_hooks(plat, config_dir)

        if not hook_results:
            console.print("[yellow]⚠ No hooks defined for this platform[/yellow]")
            continue

        # Display results
        table = Table(show_header=True, title=f"{plat} Hook Status")
        table.add_column("Hook", style="cyan")
        table.add_column("Status", style="bold")
        table.add_column("Path")

        for hook_name, status in hook_results.items():
            status_icon = "✅" if status else "❌"
            status_text = "[green]Installed[/green]" if status else "[red]Missing[/red]"

            hook_path = config_dir / "hooks" / f"{hook_name}.sh"
            path_text = str(hook_path) if status else f"dim]Not found[/dim]"

            table.add_row(hook_name, f"{status_icon} {status_text}", path_text)

        console.print(table)

        # Summary
        installed_count = sum(1 for status in hook_results.values() if status)
        total_count = len(hook_results)

        if installed_count == total_count:
            console.print(f"\n[green]✓ All {total_count} hooks installed and functional[/green]")
        elif installed_count > 0:
            console.print(
                f"\n[yellow]⚠ {installed_count}/{total_count} hooks installed[/yellow]"
            )
        else:
            console.print(f"\n[red]✗ No hooks installed[/red]")


def _do_status(installer: VibeSOPInstaller) -> None:
    """Show hook status for all platforms.

    Args:
        installer: VibeSOPInstaller instance
    """
    console.print(
        f"\n[bold cyan]📊 Hook Status Overview[/bold cyan]"
        f"\n{'=' * 40}\n"
    )

    platforms = installer.list_platforms()

    if not platforms:
        console.print("[yellow]⚠ No platforms found[/yellow]")
        return

    table = Table(show_header=True)
    table.add_column("Platform", style="cyan")
    table.add_column("Installed", style="bold")
    table.add_column("Hooks", style="dim")
    table.add_column("Config Dir")

    for platform_info in platforms:
        platform_name = platform_info["name"]
        config_dir = platform_info["config_dir"]

        # Verify installation
        verify_result = installer.verify(platform_name)

        if not verify_result["installed"]:
            table.add_row(
                platform_name,
                "[red]Not installed[/red]",
                "[dim]N/A[/dim]",
                config_dir,
            )
            continue

        # Check hooks
        from vibesop.hooks import HookInstaller

        hook_installer = HookInstaller()
        hook_results = hook_installer.verify_hooks(platform_name, Path(config_dir).expanduser())

        installed_count = sum(1 for status in hook_results.values() if status)
        total_count = len(hook_results)

        if total_count == 0:
            hooks_status = "[dim]No hooks[/dim]"
        elif installed_count == total_count:
            hooks_status = f"[green]{installed_count}/{total_count}[/green]"
        else:
            hooks_status = f"[yellow]{installed_count}/{total_count}[/yellow]"

        table.add_row(
            platform_name,
            "[green]✓ Installed[/green]",
            hooks_status,
            config_dir,
        )

    console.print(table)

    # Overall summary
    total_platforms = len(platforms)
    installed_platforms = sum(
        1 for p in platforms
        if installer.verify(p["name"])["installed"]
    )

    console.print(f"\n[dim]Summary: {installed_platforms}/{total_platforms} platforms installed[/dim]")
