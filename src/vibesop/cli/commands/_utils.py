"""Shared utilities for CLI commands."""

from __future__ import annotations

import logging
from pathlib import Path

from ruamel.yaml import YAML

logger = logging.getLogger(__name__)


def get_configured_platform() -> str | None:
    """Get platform from .vibe/config.toml (preferred) or .vibe/config.yaml.

    Returns:
        Platform string if configured, None otherwise.
    """
    for ext in [".toml", ".yaml"]:
        config_path = Path(f".vibe/config{ext}")
        if not config_path.exists():
            continue
        try:
            if ext == ".toml":
                from vibesop.utils.encoding import load_toml_with_fallback

                config = load_toml_with_fallback(config_path)
            else:
                from vibesop.utils.encoding import read_text_with_fallback

                yaml_parser = YAML()
                config = yaml_parser.load(read_text_with_fallback(config_path))
            return config.get("platform") if config else None
        except Exception as e:
            logger.debug("Failed to read %s: %s", config_path.name, e)
    return None


def validate_platform(platform: str | None) -> list[str] | None:
    """Validate and normalize the --platform value.

    Accepts comma-separated values (``--platform claude-code,kimi-cli``) and
    the special sentinel ``all`` (returns ``None`` to signal "all platforms").

    Returns a list of validated platform names, or ``None`` when ``platform``
    is ``None`` (caller should then fall back to config-based resolution).
    """
    if platform is None:
        return None
    from vibesop.core.skills.storage import SkillStorage

    valid = SkillStorage.PLATFORM_SKILLS_DIRS.keys()
    raw_items = [p.strip() for p in platform.split(",") if p.strip()]
    if not raw_items:
        return None
    if len(raw_items) == 1 and raw_items[0] == "all":
        return None

    unknown = [p for p in raw_items if p not in valid]
    if unknown:
        from rich.console import Console
        import typer
        console = Console()
        console.print(
            f"[red]✗ Unknown platform: {', '.join(unknown)}[/red]\n"
            f"[dim]Valid platforms: {', '.join(sorted(valid))} (or 'all')[/dim]"
        )
        raise typer.Exit(1)
    return raw_items


def resolve_platforms(
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
    from pathlib import Path as StdPath

    from vibesop.core.config.manager import ConfigManager, ConfigSourcePriority
    from vibesop.core.skills.storage import SkillStorage

    if cli_platform is not None:
        return validate_platform(cli_platform), "cli-flag"

    manager = ConfigManager(project_root or StdPath.cwd())
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
        from rich.console import Console

        console = Console()
        console.print(
            f"[yellow]⚠ Ignoring unknown platform(s) in config: "
            f"{', '.join(unknown)}[/yellow]\n"
            f"[dim]Valid: {', '.join(sorted(valid))}[/dim]"
        )
    resolved = [p for p in targets if p in valid]
    if not resolved:
        return list(valid), "default"
    return resolved, source
