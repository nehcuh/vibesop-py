"""CLI subcommand registration.

Groups related commands into Typer sub-apps for better organization.
"""

from __future__ import annotations

import typer

from vibesop.cli.commands import (
    analyze as analyze_mod,
    auto as auto_mod,
    auto_analyze as auto_analyze_mod,
    autonomous_experiment as autonomous_experiment_mod,
    build as build_mod,
    cascade as cascade_mod,
    checkpoint as checkpoint_mod,
    config as config_mod,
    deploy as deploy_mod,
    detect as detect_mod,
    execute as execute_mod,
    experiment as experiment_mod,
    hooks as hooks_mod,
    import_rules as import_rules_mod,
    init as init_mod,
    inspect as inspect_mod,
    install as install_mod,
    instinct_new as instinct_mod,
    memory_cmd as memory_mod,
    onboard as onboard_mod,
    quickstart as quickstart_mod,
    route_commands as route_mod,
    scan as scan_mod,
    skill_craft as skill_craft_mod,
    skills_cmd as skills_mod,
    switch as switch_mod,
    targets as targets_mod,
    toolchain as toolchain_mod,
    tools_cmd as tools_mod,
    worktree as worktree_mod,
    workflow as workflow_mod,
)

# Sub-apps for grouped commands
workflow_app = typer.Typer(help="Workflow management")
config_app = typer.Typer(help="Configuration management")
route_app = typer.Typer(help="Route management")
experiment_app = typer.Typer(help="Experiment management")
cascade_app = typer.Typer(help="Cascade execution")
skills_app = typer.Typer(help="Skill storage management")


def register(app: typer.Typer) -> None:
    """Register all subcommands with the main app.

    Args:
        app: The main Typer application
    """
    # Register sub-apps
    app.add_typer(workflow_app, name="workflow")
    app.add_typer(config_app, name="config")
    app.add_typer(route_app, name="route-cmd")
    app.add_typer(experiment_app, name="experiment")
    app.add_typer(cascade_app, name="cascade-cmd")
    app.add_typer(skills_app, name="skills")

    # Workflow sub-commands
    workflow_app.command("run")(workflow_mod.workflow)
    workflow_app.command("list")(workflow_mod.workflow)
    workflow_app.command("resume")(workflow_mod.workflow)
    workflow_app.command("validate")(workflow_mod.workflow)

    # Config sub-commands
    config_app.command()(config_mod.config)
    config_app.command("semantic")(config_mod.config_semantic)

    # Route sub-commands
    route_app.command("select")(route_mod.route_select)
    route_app.command("validate")(route_mod.route_validate)

    # Experiment sub-commands
    experiment_app.command()(experiment_mod.experiment)

    # Autonomous experiment (autoresearch)
    app.add_typer(autonomous_experiment_mod.app, name="autonomous-experiment")

    # Cascade sub-commands
    cascade_app.command()(cascade_mod.cascade)

    # Top-level commands (grouped by category)

    # Platform / Build / Deploy
    app.command()(init_mod.init)
    app.command()(build_mod.build)
    app.command()(deploy_mod.deploy)
    app.command()(switch_mod.switch)
    app.command("inspect")(inspect_mod.inspect_cmd)
    app.command()(targets_mod.targets)
    app.command()(install_mod.install)

    # Analysis / Scanning
    app.command()(scan_mod.scan)
    app.command()(detect_mod.detect)
    app.command()(analyze_mod.analyze)
    app.command()(auto_analyze_mod.auto_analyze_session)
    app.command("create-suggested-skills")(auto_analyze_mod.create_suggested_skills)

    # Auto / Intent detection
    app.command()(auto_mod.auto)

    # Skills
    skills_app.command()(skills_mod.list)
    skills_app.command("install")(skills_mod.install)
    skills_app.command("link")(skills_mod.link)
    skills_app.command("unlink")(skills_mod.unlink)
    skills_app.command("remove")(skills_mod.remove)
    skills_app.command("sync")(skills_mod.sync)
    skills_app.command("status")(skills_mod.status)

    # Legacy: keep skill-craft as top-level for now
    app.command("skill-craft")(skill_craft_mod.skill_craft)

    # Git / Worktree
    app.command()(worktree_mod.worktree)

    # Tool management
    app.command()(toolchain_mod.toolchain)
    app.command()(tools_mod.tools)

    # Memory / Instinct
    app.command("memory")(memory_mod.memory)
    app.add_typer(instinct_mod.app, name="instinct")

    # Checkpoint
    app.command()(checkpoint_mod.checkpoint)

    # Hooks
    app.command()(hooks_mod.hooks)

    # Rules import
    app.command("import-rules")(import_rules_mod.import_rules)

    # Onboarding
    app.command()(quickstart_mod.quickstart)
    app.command()(onboard_mod.onboard)

    # Skill execution (top-level commands)
    app.command()(execute_mod.execute)
    app.command("execute-list")(execute_mod.list_available)
