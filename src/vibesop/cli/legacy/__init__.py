"""Legacy (deprecated) CLI commands.

.. deprecated:: 4.1.0
    The commands in this module are deprecated and will be removed in v5.0.0.
    These commands are out of scope for a routing engine.

To enable legacy commands:
1. Install with extras: pip install vibesop[legacy]
2. Set environment variable: VIBESOP_ENABLE_LEGACY=1
3. Or use: vibe --enable-legacy <command>

Migration guide:
- deploy: Use platform-specific installation methods
- toolchain: Use your system package manager (brew, apt, etc.)
- worktree: Use native git worktree commands
- checkpoint: Use git tags/branches for state management
- hooks: Configure hooks in platform-specific settings
"""

import os
import typing
from warnings import warn

import typer

from vibesop.cli.legacy import (
    checkpoint,
    deploy,
    hooks,
    toolchain,
    worktree,
)

# Show deprecation warning when module is imported
warn(
    "Legacy CLI commands are deprecated and will be removed in v5.0.0. "
    "See module docstring for migration guide.",
    DeprecationWarning,
    stacklevel=2,
)


def is_enabled() -> bool:
    """Check if legacy commands are enabled.

    Returns:
        True if legacy commands should be registered
    """
    # Check environment variable
    if os.getenv("VIBESOP_ENABLE_LEGACY", "0").lower() in ("1", "true", "yes"):
        return True

    # Check if installed with legacy extras
    # This is set by the [legacy] extra in pyproject.toml
    try:
        import importlib.metadata

        return (
            importlib.metadata.distribution("vibesop").read_text("extras_require.txt")
            or ""
        ).find("legacy") >= 0
    except Exception:
        pass

    return False


def register(app: typer.Typer) -> None:
    """Register legacy commands with the main app.

    Args:
        app: Main Typer application
    """
    if not is_enabled():
        return

    # Register deprecated commands
    app.command()(deploy.deploy)
    app.command()(toolchain.toolchain)
    app.command()(worktree.worktree)
    app.command()(checkpoint.checkpoint)
    app.command()(hooks.hooks)


__all__ = [
    "checkpoint",
    "deploy",
    "hooks",
    "is_enabled",
    "register",
    "toolchain",
    "worktree",
]
