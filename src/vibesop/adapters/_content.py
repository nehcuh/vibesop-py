"""Skill content utilities — find, validate, normalize, and render skill files.

These functions form the skill lifecycle layer:
  - detect_tool_environment: environment guidance for config files
  - find_skill_content: locate SKILL.md on disk
  - is_pack_installed: check external pack presence
  - normalize_skill_type: convert unsupported types to "standard"
  - generate_fallback_skill_content: minimal SKILL.md stub
  - render_skill_md: Jinja2 template rendering
  - _yaml_dquote: YAML-safe string quoting
"""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path
from typing import Any

from jinja2 import FileSystemLoader, select_autoescape

from vibesop._version import __version__
from vibesop.utils.jinja_safety import make_shell_safe_env

logger = logging.getLogger(__name__)


def detect_tool_environment() -> str:
    """Detect nvm and uv availability and return guidance text.

    Checks if nvm (Node Version Manager) and uv (Python package manager)
    are available on the system. Returns Markdown guidance to be inserted
    at the top of CLAUDE.md / AGENTS.md global configuration files.

    Returns:
        Markdown string with tool environment guidance, or empty string
        if neither nvm nor uv is detected.
    """
    tools_found: list[str] = []
    guidance_lines: list[str] = []

    # Detect nvm
    nvm_found = False
    nvm_candidates = [
        Path.home() / ".nvm" / "nvm.sh",
        Path("/usr/local/opt/nvm/nvm.sh"),
    ]
    for candidate in nvm_candidates:
        if candidate.exists():
            nvm_found = True
            break
    if not nvm_found:
        nvm_in_path = shutil.which("nvm") is not None
        if nvm_in_path:
            nvm_found = True

    if nvm_found:
        tools_found.append("nvm")
        guidance_lines.append(
            "- **nvm** (Node Version Manager): When working with Node.js "
            "projects, use `nvm use` to switch to the correct Node.js version "
            "before running any Node.js commands. Run `nvm ls` to see "
            "available versions."
        )

    # Detect uv
    uv_found = shutil.which("uv") is not None
    if uv_found:
        tools_found.append("uv")
        guidance_lines.append(
            "- **uv** (Python package manager): When working with Python "
            "projects, **always use `uv` instead of `pip`** for package "
            "management.\n"
            "  - Use `uv run python` or `uv run pytest` to run Python scripts "
            "and tests\n"
            "  - Use `uv add <package>` to install project dependencies\n"
            "  - Use `uv pip install <package>` for ad-hoc installations\n"
            "  - Use `uv sync` to sync the project environment"
        )

    if not tools_found:
        return ""

    header = (
        "## Tool Environment\n\n"
        "The following development tools are available on this system. "
        "Use them when working with the corresponding ecosystems:\n\n"
    )
    return header + "\n".join(guidance_lines) + "\n"


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
    # Strip namespace prefix for directory lookup (e.g. "builtin/instinct" → "instinct")
    name_only = skill_id.split("/", 1)[1] if "/" in skill_id else skill_id

    from vibesop.utils.bundled import resolve_builtin_skills_dir

    builtin = resolve_builtin_skills_dir(project_root)
    skill_paths = [
        builtin / name_only / "SKILL.md",
        builtin / skill_id / "SKILL.md",
        project_root / "skills" / name_only / "SKILL.md",
        project_root / "skills" / skill_id / "SKILL.md",
    ]

    for skill_path in skill_paths:
        if skill_path.exists():
            try:
                return skill_path.read_text(encoding="utf-8")
            except Exception as e:
                logger.debug(f"Failed to read skill file {skill_path}: {e}")

    return None


def is_pack_installed(skill_id: str) -> Path | None:
    """Check if the external pack for a skill is installed in central storage.

    For skill IDs like 'gstack/review' or 'superpowers/brainstorm',
    checks if ~/.config/skills/<namespace>/<name>/SKILL.md exists.

    Returns:
        Path to the installed skill directory or None
    """
    if "/" not in skill_id:
        return None

    parts = skill_id.split("/", 1)
    namespace = parts[0]
    skill_name = parts[1]

    central_base = Path.home() / ".config" / "skills"

    candidates = [
        central_base / namespace / skill_name,
        central_base / namespace / "skills" / skill_name,
        # depth-2: skill installed directly under ~/.config/skills/ (no pack dir)
        central_base / skill_name,
    ]
    for candidate in candidates:
        if candidate.exists() and (candidate / "SKILL.md").exists():
            return candidate

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
    except Exception:
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
    name = dir_name or (skill.name if hasattr(skill, "name") else skill.get("name", skill_id))
    description = (
        skill.description if hasattr(skill, "description") else skill.get("description", "")
    )
    # Collapse multi-line descriptions to a single line for valid YAML
    description = " ".join(description.split()) if description else ""
    # YAML double-quote: escape backslashes and embedded double quotes
    description = description.replace("\\", "\\\\").replace('"', '\\"')
    trigger = (
        skill.trigger_when if hasattr(skill, "trigger_when") else skill.get("trigger_when", "")
    )

    lines = [
        "---",
        f"name: {name}",
        f'description: "{description}"',
        "---",
        "",
        f"# {name}",
        "",
        f"{description}",
        "",
    ]
    if trigger:
        lines.extend(["## Trigger", "", f"{trigger}", ""])
    lines.extend(["", "*External skill — install the source pack for full content.*", ""])
    return "\n".join(lines)


def _yaml_dquote(value: str) -> str:
    """Wrap a string in YAML double quotes, escaping \\ and ".

    YAML bare strings break when the value starts with ``[``, ``{``,
    ``>``, ``|``, ``!``, or contains ``: `` (colon-space), ``#``
    (comment), or ``$var`` patterns.  Wrapping in double quotes is the
    simplest way to produce safe frontmatter for any free-form
    description.
    """
    if not value:
        return '""'
    # Escape backslashes first, then double quotes
    safe = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{safe}"'


def render_skill_md(
    skill: Any,
    *,
    version: str = __version__,
) -> str:
    """Render a SKILL.md from the shared Jinja2 template.

    Uses ``templates/shared/SKILL.md.j2`` — the canonical template shared
    by all adapters that render fallback skill content (Claude Code, Pi).
    """
    from datetime import datetime

    template_dir = Path(__file__).parent / "templates" / "shared"
    env = make_shell_safe_env(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("SKILL.md.j2")

    skill_dict: dict[str, Any] = {}
    if hasattr(skill, "model_dump"):
        skill_dict = skill.model_dump()
    elif hasattr(skill, "__dataclass_fields__"):
        import dataclasses

        skill_dict = dataclasses.asdict(skill)  # type: ignore[arg-type]
    elif isinstance(skill, dict):
        skill_dict = skill
    else:
        for attr in (
            "id",
            "name",
            "description",
            "trigger_when",
            "skill_type",
            "namespace",
            "version",
            "author",
            "tags",
            "metadata",
        ):
            if hasattr(skill, attr):
                skill_dict[attr] = getattr(skill, attr)

    # YAML-safe the description before handing to template
    if skill_dict.get("description"):
        skill_dict["description"] = _yaml_dquote(skill_dict["description"])

    rendered = template.render(
        skill=skill_dict,
        metadata={
            "created_at": datetime.now(),
            "version": version,
        },
        version=version,
    )
    # Cap blank-line runs at two so empty template sections can never ship
    # blank-run-heavy stubs (2026-08-27: a stub with an empty "When to Use"
    # section rendered enough consecutive newlines to trip the runtime
    # injection heuristic, flagging VibeSOP's own generated stub as tampered).
    return re.sub(r"\n{4,}", "\n\n\n", rendered)


__all__ = [
    "_yaml_dquote",
    "detect_tool_environment",
    "find_skill_content",
    "generate_fallback_skill_content",
    "is_pack_installed",
    "normalize_skill_type",
    "render_skill_md",
]
