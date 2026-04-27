"""VibeSOP deploy command - Deploy built configuration to platform.

This module handles deploying built configuration files to the
target platform's configuration directory.
"""

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

VALID_TARGETS = ["claude-code", "kimi-cli", "opencode", "superpowers", "cursor"]

PLATFORM_DIRS: dict[str, Path] = {
    "claude-code": Path.home() / ".claude",
    "kimi-cli": Path.home() / ".kimi",
    "opencode": Path.home() / ".config" / "opencode",
    "superpowers": Path.home() / ".superpowers",
    "cursor": Path.home() / ".cursor",
}


def _execute_deploy(  # pyright: ignore[reportUnusedFunction]
    target: str,
    destination: Path | None = None,
    source: Path | None = None,
    force: bool = False,
    backup: bool = True,
    dry_run: bool = False,
) -> None:
    """Execute deploy logic (reusable by other commands).

    Args:
        target: Target platform
        destination: Destination directory (uses platform default if None)
        source: Source directory with built files
        force: Force overwrite existing files
        backup: Backup existing configuration before overwriting
        dry_run: Print what would be done without actually doing it

    Raises:
        ValueError: If target is invalid or source does not exist
    """
    if target not in VALID_TARGETS:
        msg = f"Invalid target: {target}. Valid targets: {', '.join(VALID_TARGETS)}"
        raise ValueError(msg)

    if source is None:
        source = Path(f".vibe/dist/{target}")
    if not source.exists():
        msg = f"Build output not found: {source}. Run 'vibe build {target}' first."
        raise FileNotFoundError(msg)

    if destination is None:
        destination = PLATFORM_DIRS.get(target)
        if destination is None:
            msg = f"No default config directory for {target}"
            raise ValueError(msg)

    destination = destination.expanduser().resolve()
    source = source.expanduser().resolve()

    if dry_run:
        logger.info("[DRY RUN] Would deploy %s -> %s", source, destination)
        return

    # Backup existing config
    if backup and destination.exists():
        backup_dir = destination.with_name(destination.name + ".backup")
        if backup_dir.exists():
            shutil.rmtree(backup_dir)
        shutil.copytree(destination, backup_dir, symlinks=True)
        logger.info("Backed up existing config to %s", backup_dir)

    # Deploy - copy each item from source to destination
    destination.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        dest_item = destination / item.name
        if dest_item.exists():
            if force:
                if dest_item.is_dir():
                    shutil.rmtree(dest_item)
                else:
                    dest_item.unlink()
            else:
                continue
        if item.is_dir():
            shutil.copytree(item, dest_item, symlinks=True, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest_item)

    logger.info("Deployed %s configuration to %s", target, destination)
