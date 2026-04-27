"""VibeSOP verify command - Verify platform configuration integrity.

Checks platform-specific configuration files for correctness,
including hooks, AGENTS.md, script permissions, and more.

Usage:
    vibe verify [PLATFORM]
    vibe verify --help

Examples:
    # Verify all installed platforms
    vibe verify

    # Verify specific platform
    vibe verify kimi-cli
    vibe verify opencode

    # Verify and show details
    vibe verify --verbose
"""

import shutil
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

PLATFORM_CONFIGS: dict[str, dict] = {
    "claude-code": {
        "name": "Claude Code",
        "config_dir": Path.home() / ".claude",
        "checks": {
            "config_dir": "Configuration directory exists",
            "claude_md": "CLAUDE.md in config dir exists",
            "project_claude_md": "CLAUDE.md in project root exists",
            "rules_dir": "rules/ directory exists",
            "route_hook": "hooks/vibesop-route.sh exists",
            "route_hook_executable": "vibesop-route.sh is executable",
            "track_hook": "hooks/vibesop-track.sh exists",
        },
    },
    "kimi-cli": {
        "name": "Kimi Code CLI",
        "config_dir": Path.home() / ".kimi",
        "checks": {
            "config_dir": "Configuration directory exists",
            "config_toml": "config.toml exists",
            "hooks_section": "config.toml has hooks segment",
            "hook_script": "hooks/vibesop-route.sh exists",
            "hook_executable": "vibesop-route.sh is executable",
        },
    },
    "opencode": {
        "name": "OpenCode",
        "config_dir": Path.home() / ".config" / "opencode",
        "checks": {
            "config_dir": "Configuration directory exists",
            "agents_md_config": "AGENTS.md in config dir exists",
            "agents_md_project": "AGENTS.md in project root exists",
            "env_script": "vibesop-env.sh exists",
            "hook_script": "hooks/vibesop-route.sh exists",
            "hook_executable": "vibesop-route.sh is executable",
        },
    },
}

console = Console()


def verify(
    platform: str | None = typer.Argument(
        None,
        help="Platform to verify (claude-code, kimi-cli, opencode, all)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed check results",
    ),
) -> None:
    """Verify platform configuration integrity.

    This command checks that VibeSOP configuration files are correctly
    installed and have the expected content for each platform.
    """
    platforms_to_check: list[str] = list(PLATFORM_CONFIGS.keys())
    if platform and platform != "all":
        if platform not in PLATFORM_CONFIGS:
            console.print(f"[red]✗ Unknown platform: {platform}[/red]")
            console.print(f"[dim]Valid platforms: {', '.join(PLATFORM_CONFIGS.keys())}, all[/dim]")
            raise typer.Exit(1)
        platforms_to_check = [platform]

    all_pass = True
    overall_results: list[tuple[str, str, list[dict]]] = []

    for plat in platforms_to_check:
        results = _check_platform(plat)
        plat_pass = all(r["pass"] for r in results)
        if not plat_pass:
            all_pass = False
        overall_results.append((plat, PLATFORM_CONFIGS[plat]["name"], results))

    _render_results(overall_results, verbose)

    if not all_pass:
        raise typer.Exit(1)


def _check_platform(platform: str) -> list[dict]:
    config = PLATFORM_CONFIGS[platform]
    config_dir = config["config_dir"]
    project_root = Path.cwd()
    results: list[dict] = []

    for check_id, check_desc in config["checks"].items():
        result = {"id": check_id, "description": check_desc, "pass": False, "detail": ""}

        if check_id == "config_dir":
            result["pass"] = config_dir.exists()
            result["detail"] = str(config_dir) if result["pass"] else f"Missing: {config_dir}"

        elif check_id == "claude_md":
            path = config_dir / "CLAUDE.md"
            result["pass"] = path.exists()
            result["detail"] = (
                f"Found ({path.stat().st_size}b)" if result["pass"] else f"Missing: {path}"
            )

        elif check_id == "project_claude_md":
            path = project_root / "CLAUDE.md"
            result["pass"] = path.exists()
            result["detail"] = (
                f"Found ({path.stat().st_size}b)" if result["pass"] else f"Missing: {path}"
            )

        elif check_id == "rules_dir":
            path = config_dir / "rules"
            result["pass"] = path.is_dir()
            result["detail"] = (
                f"Found ({len(list(path.iterdir()))} files)"
                if result["pass"]
                else f"Missing: {path}"
            )

        elif check_id == "route_hook":
            path = config_dir / "hooks" / "vibesop-route.sh"
            result["pass"] = path.exists()
            result["detail"] = (
                f"Found ({path.stat().st_size}b)" if result["pass"] else f"Missing: {path}"
            )

        elif check_id == "route_hook_executable":
            path = config_dir / "hooks" / "vibesop-route.sh"
            if path.exists():
                is_exec = bool(path.stat().st_mode & 0o111)
                result["pass"] = is_exec
                result["detail"] = "Executable" if is_exec else "Not executable (chmod 755)"
            else:
                result["detail"] = "Script not found"

        elif check_id == "track_hook":
            path = config_dir / "hooks" / "vibesop-track.sh"
            result["pass"] = path.exists()
            result["detail"] = (
                f"Found ({path.stat().st_size}b)" if result["pass"] else f"Missing: {path}"
            )

        elif check_id == "config_toml":
            path = config_dir / "config.toml"
            result["pass"] = path.exists()
            result["detail"] = (
                f"Found ({path.stat().st_size}b)" if result["pass"] else f"Missing: {path}"
            )

        elif check_id == "hooks_section":
            path = config_dir / "config.toml"
            if path.exists():
                content = path.read_text()
                has_hooks = "[[hooks]]" in content
                has_vibe_hook = "vibesop-route" in content
                result["pass"] = has_hooks and has_vibe_hook
                if result["pass"]:
                    result["detail"] = "[[hooks]] with vibesop-route found"
                elif has_hooks:
                    result["detail"] = "[[hooks]] exists but vibesop-route not found"
                else:
                    result["detail"] = (
                        "No [[hooks]] section found (may have been overwritten by Kimi CLI)"
                    )
            else:
                result["detail"] = "config.toml not found"

        elif check_id == "agents_md_config":
            path = config_dir / "AGENTS.md"
            result["pass"] = path.exists()
            result["detail"] = (
                f"Found ({path.stat().st_size}b)" if result["pass"] else f"Missing: {path}"
            )

        elif check_id == "agents_md_project":
            path = project_root / "AGENTS.md"
            result["pass"] = path.exists()
            result["detail"] = (
                f"Found ({path.stat().st_size}b)" if result["pass"] else f"Missing: {path}"
            )

        elif check_id == "env_script":
            path = config_dir / "vibesop-env.sh"
            result["pass"] = path.exists()
            result["detail"] = (
                f"Found ({path.stat().st_size}b)" if result["pass"] else f"Missing: {path}"
            )

        elif check_id == "hook_script":
            path = config_dir / "hooks" / "vibesop-route.sh"
            result["pass"] = path.exists()
            result["detail"] = (
                f"Found ({path.stat().st_size}b)" if result["pass"] else f"Missing: {path}"
            )

        elif check_id == "hook_executable":
            path = config_dir / "hooks" / "vibesop-route.sh"
            if path.exists():
                is_exec = bool(path.stat().st_mode & 0o111)
                result["pass"] = is_exec
                result["detail"] = "Executable" if is_exec else "Not executable (chmod 755)"
            else:
                result["detail"] = "Script not found"

        results.append(result)

    return results


def _render_results(overall_results: list[tuple[str, str, list[dict]]], verbose: bool) -> None:
    console.print(f"\n[bold cyan]🔍 Configuration Verification[/bold cyan]\n{'=' * 40}\n")

    vibe_available = shutil.which("vibe") is not None
    vibe_icon = "✅" if vibe_available else "❌"
    console.print(f"{vibe_icon} vibe CLI: {'available' if vibe_available else 'not found'}")

    all_pass = True

    for plat_id, plat_name, checks in overall_results:
        has_fail = any(not c["pass"] for c in checks)
        if has_fail:
            all_pass = False

        table = Table(title=f"{'✅' if not has_fail else '❌'} {plat_name} ({plat_id})")
        table.add_column("Check", style="cyan")
        table.add_column("Status")
        if verbose:
            table.add_column("Detail")

        for check in checks:
            icon = "✅" if check["pass"] else "❌"
            status = "[green]PASS[/green]" if check["pass"] else "[red]FAIL[/red]"
            row = [check["description"], f"{icon} {status}"]
            if verbose:
                row.append(check.get("detail", ""))
            table.add_row(*row)

        console.print("")
        console.print(table)

    console.print(f"\n{'=' * 40}")

    if all_pass:
        console.print("[bold green]✅ All checks passed![/bold green]")
    else:
        console.print("[bold red]❌ Some checks failed. Review details above.[/bold red]")
