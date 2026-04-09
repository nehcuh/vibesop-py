"""CLI subcommand registration.

Groups related commands into Typer sub-apps for better organization.

Removed Commands (v4.1.0):
- execute: Removed as it violated the "router not executor" principle.
  Skills should be executed by AI Agents, not VibeSOP.
- memory: Internalized. Session memory management is handled automatically by the routing engine.
- instinct: Internalized. Instinct learning works automatically without manual CLI management.
- scan: Merged into `analyze security` subcommand.
- detect: Merged into `analyze integrations` subcommand.
- auto-analyze: Merged into `analyze session --auto`.

Legacy Commands (deprecated):
The following commands have been moved to the legacy package:
- deploy: Use platform-specific installation methods
- toolchain: Use your system package manager
- worktree: Use native git worktree commands
- checkpoint: Use git tags/branches for state management
- hooks: Configure in platform-specific settings

To enable legacy commands, install with extras: pip install vibesop[legacy]
Or set environment variable: VIBESOP_ENABLE_LEGACY=1
"""

from __future__ import annotations

import typer

from vibesop.cli.commands import (
    analyze as analyze_mod,
)
from vibesop.cli.commands import (
    build as build_mod,
)
from vibesop.cli.commands import (
    config as config_mod,
)
from vibesop.cli.commands import (
    import_rules as import_rules_mod,
)
from vibesop.cli.commands import (
    init as init_mod,
)
from vibesop.cli.commands import (
    inspect as inspect_mod,
)
from vibesop.cli.commands import (
    install as install_mod,
)
from vibesop.cli.commands import (
    onboard as onboard_mod,
)
from vibesop.cli.commands import (
    quickstart as quickstart_mod,
)
from vibesop.cli.commands import (
    skill_craft as skill_craft_mod,
)
from vibesop.cli.commands import (
    skills_cmd as skills_mod,
)
from vibesop.cli.commands import (
    switch as switch_mod,
)
from vibesop.cli.commands import (
    targets as targets_mod,
)
from vibesop.cli.commands import (
    tools_cmd as tools_mod,
)

config_app = typer.Typer(help="Configuration management")
skills_app = typer.Typer(help="Skill storage management")


def register(app: typer.Typer) -> None:
    """Register all subcommands with the main app."""
    app.add_typer(config_app, name="config")
    app.add_typer(skills_app, name="skills")

    config_app.command()(config_mod.config)

    # Core commands
    app.command()(init_mod.init)
    app.command()(build_mod.build)
    app.command()(switch_mod.switch)
    app.command("inspect")(inspect_mod.inspect_cmd)
    app.command()(targets_mod.targets)
    app.command()(install_mod.install)

    # Unified analyze command (replaces scan, detect, auto-analyze)
    # - vibe analyze session - Session analysis
    # - vibe analyze security - Security scanning (was: vibe scan)
    # - vibe analyze integrations - Integration detection (was: vibe detect)
    app.command()(analyze_mod.analyze)

    # Skills management subcommands
    skills_app.command()(skills_mod.list)
    skills_app.command("available")(skills_mod.available)
    skills_app.command("info")(skills_mod.info)
    skills_app.command("install")(skills_mod.install)
    skills_app.command("link")(skills_mod.link)
    skills_app.command("unlink")(skills_mod.unlink)
    skills_app.command("remove")(skills_mod.remove)
    skills_app.command("sync")(skills_mod.sync)
    skills_app.command("status")(skills_mod.status)

    # Experimental commands
    app.command("skill-craft")(skill_craft_mod.skill_craft)
    app.command()(tools_mod.tools)
    app.command("import-rules")(import_rules_mod.import_rules)

    # Project setup
    app.command()(quickstart_mod.quickstart)
    app.command()(onboard_mod.onboard)

    # Register legacy (deprecated) commands if enabled
    _register_legacy_commands(app)


def _register_legacy_commands(app: typer.Typer) -> None:
    """Conditionally register legacy/deprecated commands.

    These commands are deprecated and will be removed in v5.0.0.
    They are only loaded if VIBESOP_ENABLE_LEGACY is set.

    Args:
        app: Main Typer application
    """
    import os

    if os.getenv("VIBESOP_ENABLE_LEGACY", "0").lower() not in ("1", "true", "yes"):
        return

    try:
        from vibesop.cli.legacy import (
            checkpoint,
            deploy,
            hooks,
            toolchain,
            worktree,
        )

        app.command()(deploy.deploy)
        app.command()(toolchain.toolchain)
        app.command()(worktree.worktree)
        app.command()(checkpoint.checkpoint)
        app.command()(hooks.hooks)
    except ImportError:
        pass
