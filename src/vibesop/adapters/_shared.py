"""Shared adapter utilities — single source of truth for common adapter logic.

Previously duplicated across claude_code.py, opencode.py, and kimi_cli.py:
  - find_skill_content: skill file lookup (identical in all 3 adapters)
  - normalize_skill_type:  type field normalization (identical in opencode + kimi)
  - generate_fallback_skill_content: minimal stub SKILL.md (identical in opencode + kimi)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from vibesop._version import __version__

logger = logging.getLogger(__name__)


def find_skill_content(skill_id: str, project_root: Path) -> str | None:
    """Find and read actual skill content from core/skills/.

    Searches multiple candidate paths to locate the SKILL.md file for
    the given skill identifier. This is shared across all adapters.

    Args:
        skill_id: Skill identifier (e.g., "systematic-debugging" or "omx/deep-interview")
        project_root: Path to VibeSOP project root (contains core/skills/)

    Returns:
        Skill file content or None if not found
    """
    skill_paths = [
        project_root / "core" / "skills" / skill_id / "SKILL.md",
        project_root / "skills" / skill_id / "SKILL.md",
        Path(__file__).parent.parent / "core" / "skills" / skill_id / "SKILL.md",
    ]

    for skill_path in skill_paths:
        if skill_path.exists():
            try:
                return skill_path.read_text(encoding="utf-8")
            except Exception as e:
                logger.debug(f"Failed to read skill file {skill_path}: {e}")

    return None


def normalize_skill_type(content: str) -> str:
    """Normalize skill type for platform compatibility.

    Some platforms only recognize "standard" and "flow" skill types.
    VibeSOP uses "prompt" internally, which may cause parsers to skip
    the skill entirely. This converts unsupported types to "standard"
    while preserving all other frontmatter.

    Args:
        content: Original SKILL.md content

    Returns:
        Content with normalized type field (unchanged if already compatible)
    """
    if not content.startswith("---"):
        return content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return content

    frontmatter_text = parts[1].strip()
    if not frontmatter_text:
        return content

    try:
        import yaml

        frontmatter = yaml.safe_load(frontmatter_text)
        if not isinstance(frontmatter, dict):
            return content

        skill_type = frontmatter.get("type")
        if skill_type and skill_type not in ("standard", "flow"):
            lines = frontmatter_text.splitlines()
            new_lines = []
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("type:"):
                    new_lines.append("type: standard")
                else:
                    new_lines.append(line)
            new_frontmatter = "\n".join(new_lines)
            return f"---\n{new_frontmatter}\n---{parts[2]}"
    except (ValueError, IndexError):
        pass

    return content


def generate_fallback_skill_content(
    skill: Any,
    dir_name: str | None = None,
) -> str:
    """Generate minimal fallback SKILL.md for external skills without source content.

    Args:
        skill: Skill definition (may be manifest SkillInfo or dict)
        dir_name: Flattened directory name used for the skill (displayed as name)

    Returns:
        Minimal SKILL.md markdown content
    """
    skill_id = skill.id if hasattr(skill, "id") else skill.get("id", "")
    name = (
        dir_name
        or (skill.name if hasattr(skill, "name") else skill.get("name", skill_id))
    )
    description = (
        skill.description
        if hasattr(skill, "description")
        else skill.get("description", "")
    )
    trigger = (
        skill.trigger_when
        if hasattr(skill, "trigger_when")
        else skill.get("trigger_when", "")
    )

    lines = [
        "---",
        f"name: {name}",
        f"description: {description}",
        "---",
        "",
        f"# {name}",
        "",
        f"{description}",
        "",
    ]
    if trigger:
        lines.extend(["## Trigger", "", f"{trigger}", ""])
    lines.extend(
        ["", "*External skill — install the source pack for full content.*", ""]
    )
    return "\n".join(lines)


def render_route_hook(
    *,
    platform: str = "opencode",
    platform_name: str = "OpenCode",
    version: str = __version__,
    purpose: str = "Route user queries to VibeSOP skills",
    enable_explicit_overrides: bool = False,
    enable_orchestration: bool = False,
    include_additional_context: bool = False,
    no_match_message: bool = False,
) -> str:
    """Render the shared vibesop-route.sh hook script.

    All three adapters call this function instead of maintaining their
    own copies of the hook shell script.  The shared Jinja2 template
    lives in ``templates/shared/vibesop-route.sh.j2`` and is configured
    via keyword arguments.

    Args:
        platform: Platform identifier (``"claude-code"``, ``"opencode"``,
            ``"kimi-cli"``).  Controls the usage-comment block in the
            rendered script.
        platform_name: Human-readable platform name for the header.
        version: VibeSOP version string (defaults to ``__version__``).
        purpose: One-line description for the script header.
        enable_explicit_overrides:  When ``True`` the rendered script
            includes the ``/skill-id`` / ``@skill-id`` / ``使用 skill-id``
            override detection block.
        enable_orchestration:  When ``True`` the rendered script parses
            ``mode`` from the routing result and injects an execution
            plan for multi-intent queries.
        include_additional_context:  When ``True`` the rendered script
            attaches the full skill content as ``additionalContext`` in
            the hook output (used by Claude Code and Kimi CLI).
        no_match_message:  When ``True`` the rendered script produces a
            user-facing fallback message when no skill matches (``"🤖
            VibeSOP: No matching skill found.  Proceeding in normal
            mode."``).

    Returns:
        Rendered shell script text.
    """
    template_dir = Path(__file__).parent / "templates" / "shared"
    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("vibesop-route.sh.j2")
    return template.render(
        platform=platform,
        platform_name=platform_name,
        version=version,
        purpose=purpose,
        enable_explicit_overrides=enable_explicit_overrides,
        enable_orchestration=enable_orchestration,
        include_additional_context=include_additional_context,
        no_match_message=no_match_message,
    )


__all__ = [
    "find_skill_content",
    "normalize_skill_type",
    "generate_fallback_skill_content",
    "render_route_hook",
]
