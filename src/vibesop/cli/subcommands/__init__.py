"""CLI subcommand registration.

Groups related commands into Typer sub-apps for better organization.
"""

from __future__ import annotations

import typer

from vibesop.cli.commands import (
    algorithms as algorithms_mod,
)
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

    config_app.callback(invoke_without_command=True)(config_mod.config)

    # Core commands
    app.command()(init_mod.init)
    app.command()(build_mod.build)
    app.command()(switch_mod.switch)
    app.command("inspect")(inspect_mod.inspect_cmd)
    app.command()(targets_mod.targets)
    app.command()(install_mod.install)

    # Algorithm library
    app.command("algorithms")(algorithms_mod.algorithms_list)

    # Unified analyze command
    app.command()(analyze_mod.analyze)

    # Skills management subcommands
    skills_app.command("list")(skills_mod.list_skills)
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
