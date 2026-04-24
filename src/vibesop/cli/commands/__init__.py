"""VibeSOP CLI commands module.

This package contains all CLI command implementations.

Removed Commands (v4.1.0):
    - execute: Removed as it violated the "router not executor" principle
    - memory: Internalized as routing engine feature
    - instinct: Internalized as automatic learning
    - scan: Merged into analyze security
    - detect: Merged into analyze integrations
    - auto-analyze: Merged into analyze session

Legacy Commands (deprecated, moved to vibesop.cli.legacy):
    - deploy (use platform-specific installation)
    - toolchain (use system package manager)
    - worktree (use git worktree commands)
    - checkpoint (use git tags/branches)
    - hooks (use platform-specific configuration)

To enable legacy commands, set VIBESOP_ENABLE_LEGACY=1 or install with:
    pip install vibesop[legacy]
"""

# Import command modules (not functions) to avoid naming conflicts
from vibesop.cli.commands import analyze as analyze_module
from vibesop.cli.commands import build as build_module
from vibesop.cli.commands import config as config_module
from vibesop.cli.commands import deviation as deviation_module
from vibesop.cli.commands import import_rules as import_rules_module
from vibesop.cli.commands import init as init_module
from vibesop.cli.commands import inspect as inspect_module
from vibesop.cli.commands import install as install_module
from vibesop.cli.commands import onboard as onboard_module
from vibesop.cli.commands import quickstart as quickstart_module
from vibesop.cli.commands import skill_craft as skill_craft_module
from vibesop.cli.commands import skills_cmd as skills_cmd_module
from vibesop.cli.commands import switch as switch_module
from vibesop.cli.commands import targets as targets_module
from vibesop.cli.commands import market_cmd as market_cmd_module
from vibesop.cli.commands import tools_cmd as tools_module

__all__ = [
    "analyze_module",
    "build_module",
    "config_module",
    "deviation_module",
    "import_rules_module",
    "init_module",
    "inspect_module",
    "install_module",
    "market_cmd_module",
    "onboard_module",
    "quickstart_module",
    "skill_craft_module",
    "skills_cmd_module",
    "switch_module",
    "targets_module",
    "tools_module",
]


def _get_legacy_module(name: str):
    """Lazy import for legacy command modules.

    Args:
        name: Module name (without 'vibesop.cli.legacy.' prefix)

    Returns:
        Module object or None if not available
    """
    import os

    if os.getenv("VIBESOP_ENABLE_LEGACY", "0").lower() not in ("1", "true", "yes"):
        return None

    try:
        return __import__(f"vibesop.cli.legacy.{name}", fromlist=[name])
    except ImportError:
        return None


def get_deploy_module():
    """Get deploy command module (legacy)."""
    return _get_legacy_module("deploy")


def get_toolchain_module():
    """Get toolchain command module (legacy)."""
    return _get_legacy_module("toolchain")


def get_worktree_module():
    """Get worktree command module (legacy)."""
    return _get_legacy_module("worktree")


def get_checkpoint_module():
    """Get checkpoint command module (legacy)."""
    return _get_legacy_module("checkpoint")


def get_hooks_module():
    """Get hooks command module (legacy)."""
    return _get_legacy_module("hooks")
