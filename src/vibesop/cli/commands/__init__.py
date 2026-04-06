"""VibeSOP CLI commands module.

This package contains all CLI command implementations.
"""

import importlib

# Import command modules (not functions) to avoid naming conflicts
init_module = importlib.import_module("vibesop.cli.commands.init")
build_module = importlib.import_module("vibesop.cli.commands.build")
deploy_module = importlib.import_module("vibesop.cli.commands.deploy")
switch_module = importlib.import_module("vibesop.cli.commands.switch")
inspect_module = importlib.import_module("vibesop.cli.commands.inspect")
targets_module = importlib.import_module("vibesop.cli.commands.targets")
checkpoint_module = importlib.import_module("vibesop.cli.commands.checkpoint")
memory_module = importlib.import_module("vibesop.cli.commands.memory_cmd")
instinct_module = importlib.import_module("vibesop.cli.commands.instinct_cmd")
quickstart_module = importlib.import_module("vibesop.cli.commands.quickstart")
onboard_module = importlib.import_module("vibesop.cli.commands.onboard")
toolchain_module = importlib.import_module("vibesop.cli.commands.toolchain")
scan_module = importlib.import_module("vibesop.cli.commands.scan")
skill_craft_module = importlib.import_module("vibesop.cli.commands.skill_craft")
tools_module = importlib.import_module("vibesop.cli.commands.tools_cmd")
worktree_module = importlib.import_module("vibesop.cli.commands.worktree")
route_commands_module = importlib.import_module("vibesop.cli.commands.route_commands")
import_rules_module = importlib.import_module("vibesop.cli.commands.import_rules")
detect_module = importlib.import_module("vibesop.cli.commands.detect")
install_module = importlib.import_module("vibesop.cli.commands.install")

__all__ = [
    "build_module",
    "checkpoint_module",
    "deploy_module",
    "detect_module",
    "import_rules_module",
    "init_module",
    "inspect_module",
    "install_module",
    "instinct_module",
    "memory_module",
    "onboard_module",
    "quickstart_module",
    "route_commands_module",
    "scan_module",
    "skill_craft_module",
    "switch_module",
    "targets_module",
    "toolchain_module",
    "tools_module",
    "worktree_module",
]
