# pyright: ignore[reportPossiblyUnboundVariable, reportUnnecessaryComparison]
"""VibeSOP skills command group - All `vibe skills *` subcommands.

Consolidated from: skills_cmd.py, skills_suggest_cmd.py,
skills_recommended_cmd.py, skills_rate_cmd.py.

Usage:
    vibe skills list [--all] [--platform P] [--show-scope] [--show-status]
    vibe skills available [--namespace N] [--verbose]
    vibe skills info <skill_id>
    vibe skills install <skill_id> [--source PATH] [--url URL] [--force]
    vibe skills link <skill_id> <platform> [--force]
    vibe skills unlink <skill_id> <platform>
    vibe skills remove <skill_id> [--unlink-all]
    vibe skills sync <platform> [--root PATH] [--force]
    vibe skills status
    vibe skills health [--pack P] [--verbose] [--ecosystem]
    vibe skills outdated [--refresh] [--json]
    vibe skills enable <skill_id>
    vibe skills disable <skill_id>
    vibe skills report [--grade G] [--suggest-removal]
    vibe skills scope <skill_id> [--set SCOPE]
    vibe skills feedback --skill ID --query Q [--helpful yes/no] ...
    vibe skills create [--name N] [--from TEMPLATE] [--from-suggestion ID]
    vibe skills distill [<suggestion-id>] [--yes] [--template]
    vibe skills lifecycle <skill_id> [--set STATE] [--reason R] [--auto-review]
    vibe skills suggestions [--dismiss] [--json]
    vibe skills rate <skill_id> <1-5> [--review R]
    vibe skills ratings [skill_id] [--limit N]
    vibe skills recommended [--collaborative] [--install]
"""

from vibesop.cli.commands.skills_commands._config import (
    disable,
    enable,
    lifecycle,
    scope,
)
from vibesop.cli.commands.skills_commands._crud import (
    install,
    link,
    remove,
    sync,
    unlink,
)
from vibesop.cli.commands.skills_commands._discovery import (
    create,
    distill,
    featured,
    recommended,
    suggestions,
)
from vibesop.cli.commands.skills_commands._health import (
    health,
    outdated,
    status,
)
from vibesop.cli.commands.skills_commands._index import (
    index,
)
from vibesop.cli.commands.skills_commands._listing import (
    available,
    info,
    list_skills,
)
from vibesop.cli.commands.skills_commands._quality import (
    feedback,
    rate,
    ratings,
    report,
    skill_optimize,
)

__all__ = [
    "available",
    "create",
    "disable",
    "distill",
    "enable",
    "featured",
    "feedback",
    "health",
    "index",
    "info",
    "install",
    "lifecycle",
    "link",
    "list_skills",
    "outdated",
    "rate",
    "ratings",
    "recommended",
    "remove",
    "report",
    "scope",
    "skill_optimize",
    "status",
    "suggestions",
    "sync",
    "unlink",
]
