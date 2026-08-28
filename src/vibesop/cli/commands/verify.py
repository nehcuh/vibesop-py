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

import json
import shlex
import shutil
import string
import sys
from itertools import pairwise
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from vibesop.utils.hook_commands import (
    VIBESOP_HOOK_SCRIPT_BASENAMES,
    classify_vibesop_hook_command,
    command_basenames,
    parse_hook_script_command,
    unwrap_token,
)

PLATFORM_CONFIGS: dict[str, dict[str, Any]] = {
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
            "route_hook_command": "vibesop hook commands in settings.json are Git-Bash-safe",
            "track_hook": "hooks/vibesop-track.sh exists",
        },
    },
    "kimi-cli": {
        "name": "Kimi Code CLI",
        "config_dir": Path.home() / ".kimi-code",
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
    "cursor": {
        "name": "Cursor IDE",
        "config_dir": Path.home() / ".config" / "cursor",
        "checks": {
            "config_dir": "Configuration directory exists",
            "agents_md_config": "AGENTS.md in config dir exists",
            "agents_md_project": "AGENTS.md in project root exists",
            "env_script": "vibesop-env.sh exists",
            "hook_script": "hooks/vibesop-route.sh exists",
            "hook_executable": "vibesop-route.sh is executable",
        },
    },
    "pi": {
        "name": "Pi Coding Agent",
        "config_dir": Path(".pi"),
        "checks": {
            "config_dir": "Project .pi/ directory exists",
            "agents_md": "AGENTS.md in project root exists",
            "extensions_dir": ".pi/extensions/ directory exists",
            "skills_dir": ".pi/skills/ directory exists",
            "route_extension": "vibesop-route.ts extension exists",
            "track_extension": "vibesop-track.ts extension exists",
            "prompts_dir": ".pi/prompts/ directory exists",
        },
    },
    "grok-build": {
        "name": "Grok Build",
        "config_dir": Path.home() / ".grok",
        "checks": {
            "config_dir": "Configuration directory exists",
            "rules_routing": "rules/routing.md exists",
            "route_hook_json": "hooks/vibesop-route.json exists",
            "tool_seq_hook_json": "hooks/vibesop-tool-seq.json exists",
            "vibe_on_path": "vibe executable is on PATH",
        },
    },
}


def collect_settings_hook_commands(settings: dict[str, Any]) -> list[str]:
    """Return every ``hooks.*.hooks[].command`` string from settings.json."""
    commands: list[str] = []
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return commands
    for entries in hooks.values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            items = entry.get("hooks")
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict):
                    cmd = item.get("command")
                    if isinstance(cmd, str):
                        commands.append(cmd)
    return commands


def unsafe_windows_hook_command_reason(command: str) -> str | None:
    """Why a Claude Code hook command will fail on Windows.

    Returns None when the command is safe (``bash <posix-abs-path>``, no
    wrapper, no quotes). Probed live on Claude Code 2.1.220 (2026-08-28):
    the host spawns hooks via ``bash -c`` with the session CWD as working
    directory, so a config-relative ``hooks/<name>.sh`` resolves against
    that CWD and fails with 127 from anywhere else. Quoted paths also
    failed on hosts with the older path-join behavior (pre-2.1.x), so
    they stay rejected.
    """
    stripped = command.lstrip()
    if stripped.startswith(('"', "'")):
        return "quoted path is not absolute to Claude Code (configDir+quote join)"
    if "\\" in command:
        return "backslash in command (Git Bash eats \\ )"
    lowered = command.lower()
    if "program files" in lowered or "bash.exe" in lowered:
        return "Git bash.exe wrapper (Program Files splits under bash -c)"
    return None


def _windows_drive_token(command: str) -> str | None:
    """First token starting with a drive-letter prefix (``C:/`` or ``C:\\``).

    Anchored at the token start (same shape as the parser's win_abs check):
    ``re.search`` would false-positive on ``https://`` (``s:/``).
    """
    for tok in command.split():
        t = unwrap_token(tok).strip("\"'")
        if len(t) >= 3 and t[0] in string.ascii_letters and t[1] == ":" and t[2] in "/\\":
            return t
    return None


def _unquoted_spaced_script_reason(command: str) -> str | None:
    """The M1 word-split signature: a vibesop script token starting mid-path.

    ``bash C:/Users/First Last/…/vibesop-route.sh`` tokenizes so the
    basename lands on a *relative-looking* fragment (``Last/…``) preceded
    by a path fragment — under the host's ``bash -c`` spawn that command
    exits 127. Complete script tokens (absolute, drive, ``hooks/``, or
    quoted) and benign extras (flags, URLs) are left alone.
    """
    try:
        raw = shlex.split(command, posix=False)
    except ValueError:
        return None
    for prev, tok in pairwise(raw):
        if tok.startswith(("-", '"', "'")):
            continue
        inner = unwrap_token(tok).replace("\\", "/")
        if inner.rsplit("/", 1)[-1].lower() not in VIBESOP_HOOK_SCRIPT_BASENAMES:
            continue
        if inner.startswith(("/", "hooks/")):
            continue
        if (
            len(inner) >= 3
            and inner[0] in string.ascii_letters
            and inner[1] == ":"
            and inner[2] == "/"
        ):
            continue
        prev_n = unwrap_token(prev).replace("\\", "/").lower()
        if prev_n in ("bash", "bash.exe") or prev_n.endswith("/bash.exe"):
            continue
        return 'unquoted space in script path (bash -c word-splits into 127) - use bash "<posix-abs-path>"'
    return None


def _vibesop_command_unsafe_reason(command: str) -> str | None:
    """Why a vibesop hook command is unsafe on this host (None = safe).

    Both platforms converge on ``bash <posix-abs-path>`` — quoted as one
    bash word when the path contains whitespace: the 2.1.220 host spawns
    hooks with ``bash -c`` and the session CWD, so a config-relative
    ``hooks/<script>.sh`` resolves against that CWD and 127s (rejected
    unconditionally on every platform), and an unquoted spaced path
    word-splits under ``bash -c`` into 127.
    """
    reason = unsafe_windows_hook_command_reason(command)
    if reason:
        return reason
    norm = parse_hook_script_command(command)
    if norm is not None and norm.startswith("hooks/") and "/" not in norm[6:]:
        return "config-relative hooks/<script>.sh resolves against the session CWD (127)"
    if sys.platform == "win32":
        if not command.lstrip().lower().startswith(("bash ", "bash\t")):
            return "Windows Claude Code needs bash <posix-abs-path>"
    else:
        drive = _windows_drive_token(command)
        if drive:
            return f"drive-letter token ({drive}) - Windows form on a non-win32 host"
    return _unquoted_spaced_script_reason(command)


console = Console()


def verify(
    platform: str | None = typer.Argument(
        None,
        help="Platform to verify (claude-code, grok-build, kimi-cli, opencode, cursor, pi, all)",
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
    overall_results: list[tuple[str, str, list[dict[str, Any]]]] = []

    for plat in platforms_to_check:
        results = _check_platform(plat)
        plat_pass = all(r["pass"] for r in results)
        if not plat_pass:
            all_pass = False
        overall_results.append((plat, PLATFORM_CONFIGS[plat]["name"], results))

    _render_results(overall_results, verbose)

    if not all_pass:
        raise typer.Exit(1)


def _check_platform(platform: str) -> list[dict[str, Any]]:
    config = PLATFORM_CONFIGS[platform]
    config_dir = config["config_dir"]
    project_root = Path.cwd()
    results: list[dict[str, Any]] = []

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
                if sys.platform == "win32":
                    # No exec bit on Windows; hooks run via Git Bash, so
                    # degrade to: bash on PATH + non-empty script.
                    is_exec = shutil.which("bash") is not None and path.stat().st_size > 0
                    result["pass"] = is_exec
                    result["detail"] = (
                        "Executable via bash" if is_exec else "bash not found or script empty"
                    )
                else:
                    is_exec = bool(path.stat().st_mode & 0o111)
                    result["pass"] = is_exec
                    result["detail"] = "Executable" if is_exec else "Not executable (chmod 755)"
            else:
                result["detail"] = "Script not found"

        elif check_id == "route_hook_command":
            path = config_dir / "settings.json"
            if not path.exists():
                result["detail"] = f"Missing: {path}"
            else:
                try:
                    settings = json.loads(path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError) as exc:
                    result["detail"] = f"Unreadable settings.json: {exc}"
                else:
                    if not isinstance(settings, dict):
                        result["detail"] = "settings.json is not an object"
                    else:
                        cmds = collect_settings_hook_commands(settings)
                        vibesop_cmds = [c for c in cmds if classify_vibesop_hook_command(c)]
                        route_cmds = [
                            c for c in vibesop_cmds if "vibesop-route.sh" in command_basenames(c)
                        ]
                        unsafe: str | None = None
                        for c in vibesop_cmds:
                            reason = _vibesop_command_unsafe_reason(c)
                            if reason:
                                unsafe = f"{reason}: {c[:80]}"
                                break
                        if not route_cmds:
                            result["detail"] = "no vibesop-route.sh command in settings.json"
                            if unsafe:
                                result["detail"] += f" (also unsafe: {unsafe})"
                        elif unsafe:
                            result["detail"] = unsafe
                        else:
                            result["pass"] = True
                            result["detail"] = (
                                f"{len(vibesop_cmds)} hook command(s), "
                                "vibesop commands Git-Bash-safe"
                            )

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
                content = path.read_text(encoding="utf-8")
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
                if sys.platform == "win32":
                    # No exec bit on Windows; hooks run via Git Bash, so
                    # degrade to: bash on PATH + non-empty script.
                    is_exec = shutil.which("bash") is not None and path.stat().st_size > 0
                    result["pass"] = is_exec
                    result["detail"] = (
                        "Executable via bash" if is_exec else "bash not found or script empty"
                    )
                else:
                    is_exec = bool(path.stat().st_mode & 0o111)
                    result["pass"] = is_exec
                    result["detail"] = "Executable" if is_exec else "Not executable (chmod 755)"
            else:
                result["detail"] = "Script not found"

        elif check_id == "rules_routing":
            path = config_dir / "rules" / "routing.md"
            result["pass"] = path.exists()
            result["detail"] = (
                f"Found ({path.stat().st_size}b)" if result["pass"] else f"Missing: {path}"
            )

        elif check_id == "route_hook_json":
            path = config_dir / "hooks" / "vibesop-route.json"
            result["pass"] = path.exists()
            result["detail"] = (
                f"Found ({path.stat().st_size}b)" if result["pass"] else f"Missing: {path}"
            )

        elif check_id == "tool_seq_hook_json":
            path = config_dir / "hooks" / "vibesop-tool-seq.json"
            result["pass"] = path.exists()
            result["detail"] = (
                f"Found ({path.stat().st_size}b)" if result["pass"] else f"Missing: {path}"
            )

        elif check_id == "vibe_on_path":
            vibe = shutil.which("vibe")
            result["pass"] = vibe is not None
            result["detail"] = vibe if vibe else "vibe not on PATH (uv tool bin missing from PATH)"

        elif check_id == "agents_md":
            path = project_root / "AGENTS.md"
            result["pass"] = path.exists()
            result["detail"] = (
                f"Found ({path.stat().st_size}b)" if result["pass"] else f"Missing: {path}"
            )

        elif check_id == "extensions_dir":
            path = config_dir / "extensions"
            result["pass"] = path.is_dir()
            result["detail"] = f"Found {path}" if result["pass"] else f"Missing: {path}"

        elif check_id == "skills_dir":
            path = config_dir / "skills"
            result["pass"] = path.is_dir()
            result["detail"] = f"Found {path}" if result["pass"] else f"Missing: {path}"

        elif check_id == "route_extension":
            path = config_dir / "extensions" / "vibesop-route.ts"
            result["pass"] = path.exists()
            result["detail"] = (
                f"Found ({path.stat().st_size}b)" if result["pass"] else f"Missing: {path}"
            )

        elif check_id == "track_extension":
            path = config_dir / "extensions" / "vibesop-track.ts"
            result["pass"] = path.exists()
            result["detail"] = (
                f"Found ({path.stat().st_size}b)" if result["pass"] else f"Missing: {path}"
            )

        elif check_id == "prompts_dir":
            path = config_dir / "prompts"
            result["pass"] = path.is_dir()
            result["detail"] = f"Found {path}" if result["pass"] else f"Missing: {path}"

        results.append(result)

    return results


def _render_results(
    overall_results: list[tuple[str, str, list[dict[str, Any]]]], verbose: bool
) -> None:
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
