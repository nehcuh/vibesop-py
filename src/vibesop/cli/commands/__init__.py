"""VibeSOP CLI commands module.

This package contains all CLI command implementations.

.. deprecated:: 4.1.0
    The following commands have been moved to vibesop.cli.legacy:
    - deploy (use platform-specific installation)
    - toolchain (use system package manager)
    - worktree (use git worktree commands)
    - checkpoint (use git tags/branches)
    - hooks (use platform-specific configuration)

To enable legacy commands, set VIBESOP_ENABLE_LEGACY=1 or install with:
    pip install vibesop[legacy]
"""

import importlib

# Import command modules (not functions) to avoid naming conflicts
init_module = importlib.import_module("vibesop.cli.commands.init")
build_module = importlib.import_module("vibesop.cli.commands.build")
switch_module = importlib.import_module("vibesop.cli.commands.switch")
inspect_module = importlib.import_module("vibesop.cli.commands.inspect")
targets_module = importlib.import_module("vibesop.cli.commands.targets")
memory_module = importlib.import_module("vibesop.cli.commands.memory_cmd")
instinct_module = importlib.import_module("vibesop.cli.commands.instinct_cmd")
quickstart_module = importlib.import_module("vibesop.cli.commands.quickstart")
onboard_module = importlib.import_module("vibesop.cli.commands.onboard")
scan_module = importlib.import_module("vibesop.cli.commands.scan")
skill_craft_module = importlib.import_module("vibesop.cli.commands.skill_craft")
tools_module = importlib.import_module("vibesop.cli.commands.tools_cmd")
route_commands_module = importlib.import_module("vibesop.cli.commands.route_commands")
import_rules_module = importlib.import_module("vibesop.cli.commands.import_rules")
detect_module = importlib.import_module("vibesop.cli.commands.detect")
install_module = importlib.import_module("vibesop.cli.commands.install")
analyze_module = importlib.import_module("vibesop.cli.commands.analyze")
auto_analyze_module = importlib.import_module("vibesop.cli.commands.auto_analyze")
config_module = importlib.import_module("vibesop.cli.commands.config")
execute_module = importlib.import_module("vibesop.cli.commands.execute")
skills_cmd_module = importlib.import_module("vibesop.cli.commands.skills_cmd")
instinct_new_module = importlib.import_module("vibesop.cli.commands.instinct_new")

__all__ = [
    "analyze_module",
    "auto_analyze_module",
    "build_module",
    "config_module",
    "detect_module",
    "execute_module",
    "import_rules_module",
    "init_module",
    "inspect_module",
    "install_module",
    "instinct_module",
    "instinct_new_module",
    "memory_module",
    "onboard_module",
    "quickstart_module",
    "route_commands_module",
    "scan_module",
    "skill_craft_module",
    "skills_cmd_module",
    "switch_module",
    "targets_module",
    "tools_module",
]


def _get_legacy_module(name: str):
    """Lazy import for legacy command modules.

    Args:
        name: Module name (without 'vibesop.cli.commands.' prefix)

    Returns:
        Module object or None if not available
    """
    import os

    if os.getenv("VIBESOP_ENABLE_LEGACY", "0").lower() not in ("1", "true", "yes"):
        return None

    try:
        return importlib.import_module(f"vibesop.cli.legacy.{name}")
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
