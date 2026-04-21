"""VibeSOP skills management commands.

Enhanced skills CLI with smart installation.
"""

import typer
from vibesop.cli.commands.skill_add import add as skill_add
from vibesop.cli.commands.skills_cmd import (
    available,
    health,
    info,
    install,
    link,
    list_skills,
    remove,
    status,
    sync,
    unlink,
)

# Create skills app
skills_app = typer.Typer(
    name="skill",
    help="Manage skills - install, configure, and list skills",
)

# Register commands
skills_app.command("add")(skill_add)
skills_app.command("list")(list_skills)
skills_app.command("info")(info)
skills_app.command("install")(install)
skills_app.command("link")(link)
skills_app.command("unlink")(unlink)
skills_app.command("remove")(remove)
skills_app.command("sync")(sync)
skills_app.command("status")(status)
skills_app.command("health")(health)
skills_app.command("available")(available)

# Add alias for "skills" (plural form)
def skills(
    action: str = typer.Argument(..., help="Action: add, list, info, etc."),
) -> None:
    """Manage skills (alias for 'skill' command).

    \b
    Examples:
        # Add a new skill
        vibe skills add tushare

        # List all skills
        vibe skills list

        # Show skill info
        vibe skills info tushare-quant
    """
    # This is a pass-through to the skills_app
    # Typer will handle the routing
    pass


# Export for main.py
__all__ = ["skills_app", "skills"]
