"""Shared adapter utilities — single source of truth for common adapter logic.

Previously duplicated across claude_code.py, opencode.py, and kimi_cli.py:
  - find_skill_content: skill file lookup (identical in all 3 adapters)
  - normalize_skill_type:  type field normalization (identical in opencode + kimi)
  - generate_fallback_skill_content: minimal stub SKILL.md (identical in opencode + kimi)
"""

from __future__ import annotations

import logging
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

    skill_paths = [
        project_root / "core" / "skills" / name_only / "SKILL.md",
        project_root / "core" / "skills" / skill_id / "SKILL.md",
        project_root / "skills" / name_only / "SKILL.md",
        project_root / "skills" / skill_id / "SKILL.md",
        Path(__file__).parent.parent / "core" / "skills" / name_only / "SKILL.md",
        Path(__file__).parent.parent / "core" / "skills" / skill_id / "SKILL.md",
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


def render_route_hook(
    *,
    platform: str = "opencode",
    platform_name: str = "OpenCode",
    version: str = __version__,
    purpose: str = "Route user queries to VibeSOP skills",
    hook_event_name: str = "",
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
        hook_event_name: Name of the hook event (e.g.,
            ``"UserPromptSubmit"``).  When non-empty, included in every
            ``hookSpecificOutput`` object as the required
            ``hookEventName`` field (Claude Code and Kimi CLI both
            require this).
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
    env = make_shell_safe_env(
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
        hook_event_name=hook_event_name,
        enable_explicit_overrides=enable_explicit_overrides,
        enable_orchestration=enable_orchestration,
        include_additional_context=include_additional_context,
        no_match_message=no_match_message,
    )


def generate_slim_agents_index(
    *,
    version: str = __version__,
    platform_name: str = "OpenCode",  # noqa: ARG001  # public API kwarg
    config_dir_label: str = "~/.config/opencode",  # noqa: ARG001  # public API kwarg
    include_skills_reference: bool = True,
) -> str:
    """Generate a slim AGENTS.md index that references docs/ for details.

    Instead of inlining 200+ lines of routing protocol, skill catalog,
    and session lifecycle, this produces a ~60 line index that tells
    the agent where to find each piece of information.

    Args:
        version: VibeSOP version string.
        platform_name: Human-readable platform name.
        config_dir_label: Path label for the global config directory.
        include_skills_reference: Whether to include the skills catalog reference.

    Returns:
        Slim AGENTS.md content.
    """
    from datetime import datetime

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    skills_ref = ""
    if include_skills_reference:
        skills_ref = """
## Skills

Run `vibe skills list` to see available skills, or read `docs/skills-catalog.md`.
"""

    tool_env = detect_tool_environment()
    if tool_env:
        tool_env = tool_env + "\n---\n"

    return f"""# VibeSOP Configuration

> **Version**: {version}
> **Generated**: {now}

{tool_env}
## Routing Protocol

**MANDATORY: Call `vibe route` before any non-trivial task.**

```bash
vibe route "<user_request>"
```

Then read `skills/<matched-skill>/SKILL.md` and follow its steps.

For routing details, override protocol, and multi-intent handling: read `docs/routing.md`.
{skills_ref}
## Session Lifecycle

When the user signals session end, run `session-end`.

Signals: "that's all for now", "heading out", "收工", "再见", `/session-end`.

Details: read `docs/session-lifecycle.md`.

## Quick Commands

When the user types `/vibe-*`, run:

```bash
vibe route --slash "/vibe-help"
vibe route --slash "/vibe-list"
vibe route --slash "/vibe-install <pack>"
```

Full list: `vibe route --slash "/vibe-help"`.

---

*Generated by VibeSOP v{version}*
"""


def generate_docs_routing() -> str:
    """Generate docs/routing.md with detailed routing protocol.

    This content was previously inlined in the main AGENTS.md.
    Moved here to keep the index slim and reduce staleness risk.
    """
    return """# Routing Protocol

## Workflow (execute in order)

1. **Route**: `vibe route "<user_request>"` — use the user's EXACT words
2. **Read**: `read skills/<matched-skill>/SKILL.md`
3. **Execute**: Follow the skill's steps exactly
4. **Verify**: Run checks the skill requires

## Agent Override Protocol

`vibe route` output is advisory, but deviation MUST be transparent.

If you decide **not** to adopt the routed skill, you MUST:

1. **Explicitly declare**: "I choose not to use the recommended skill `<skill_id>`"
2. **Show your reasoning**: explain why the skill is unsuitable
3. **Propose an alternative**: describe what you plan to do instead
4. **Get user confirmation**: WAIT for explicit approval before proceeding

Override without these 4 steps is a violation.

## Multi-Intent Orchestration

When `vibe route` returns an orchestration plan (2+ intents):

1. Execute each step in order
2. Read each step's `SKILL.md` before executing
3. Report progress: "Step N complete"
4. Parallel steps may run simultaneously

Do NOT ignore the plan and pick a single skill.

## Routing Decision Visibility

The CLI shows:
- Detected intent(s) and matched skill(s)
- Confidence scores and matching layer
- Alternative candidates and why they were rejected
- Orchestration plan for multi-intent requests

Compact summary: `vibe route --quiet "<query>"`

## Tasks That MUST Be Routed

- Debugging, fixing bugs, errors, unexpected behavior
- Code review, analysis, quality assessment
- Writing, modifying, refactoring features
- Architecture design, planning, documentation
- Security auditing, threat modeling
- Performance optimization, profiling
- Multi-step or cross-domain tasks

## Tasks That Do NOT Need Routing

- Trivial one-shot questions ("what does X do?")
- Reading a file at a user-specified path
- Listing directory contents
- Simple follow-ups within existing routed context

## Conversation Context

For multi-turn awareness:

```bash
export CONVERSATION_ID="opencode-$(python3 -c "import os, hashlib; print(hashlib.sha256(os.getcwd().encode()).hexdigest()[:16])")"
vibe route --conversation "$CONVERSATION_ID" "<user_request>"
```
"""


def generate_docs_session_lifecycle() -> str:
    """Generate docs/session-lifecycle.md with session event handling.

    This content was previously inlined in the main AGENTS.md.
    """
    return """# Session Lifecycle Events

Routing applies to **user tasks**. But some events are **Agent lifecycle
signals** and MUST be handled even when `vibe route` does not return a
confident match.

## Session End

When the user signals the end of a session, you MUST run `session-end`.

### English signals

- "that's all for now"
- "heading out"
- "I'm leaving"
- "I'm done"
- "gotta go"
- "wrap it up"
- "call it a day"

### Chinese signals

- "我要离开了"
- "先走了"
- "拜拜"
- "再见"
- "今天就到这里"
- "就到这里吧"
- "收工"

### Explicit command

`/session-end`

### If routing fails

- Do NOT skip session-end because `vibe route` returned fallback-llm
- Run the skill directly: `read skills/session-end/SKILL.md` and execute
- This is a P0 mandatory skill — skipping it is a protocol violation
"""


def generate_docs_skills_catalog(skills: list[Any]) -> str:
    """Generate docs/skills-catalog.md listing available skills.

    This is generated dynamically from the manifest, so it can be
    regenerated independently of the main AGENTS.md index.

    Args:
        skills: List of skill definitions from the manifest.

    Returns:
        Skills catalog markdown content.
    """
    lines = [
        "# Skills Catalog",
        "",
        "This file is auto-generated. Regenerate with `vibe build`.",
        "",
    ]

    if not skills:
        lines.extend(
            [
                "No skills configured.",
                "",
                "Install skills with:",
                "```bash",
                "vibe install <pack>",
                "```",
                "",
            ]
        )
    else:
        for skill in skills:
            skill_id = skill.id if hasattr(skill, "id") else skill.get("id", "")
            name = skill.name if hasattr(skill, "name") else skill.get("name", skill_id)
            description = (
                skill.description if hasattr(skill, "description") else skill.get("description", "")
            )
            trigger = (
                skill.trigger_when
                if hasattr(skill, "trigger_when")
                else skill.get("trigger_when", "")
            )
            lines.extend(
                [
                    f"### {skill_id}",
                    f"- **Name**: {name}",
                    f"- **Description**: {description}",
                    f"- **Trigger**: {trigger}",
                    "",
                ]
            )

    lines.extend(
        [
            "---",
            "*Regenerate: `vibe build`*",
        ]
    )

    return "\n".join(lines)


def generate_docs_quick_commands() -> str:
    """Generate docs/quick-commands.md with available slash commands."""
    return """# Quick Commands

When the user types a `/vibe-*` command, execute it via `vibe route --slash`.

## Available Commands

| Command | Description |
|---------|-------------|
| `/vibe-help` | Show all available commands |
| `/vibe-list` | List installed skills and available packs |
| `/vibe-route <query>` | Force trigger routing with transparency |
| `/vibe-install <pack>` | Install a skill pack |
| `/vibe-analyze [--deep]` | Analyze project architecture |
| `/vibe-evaluate [--skill <id>]` | Evaluate skill quality |
| `/vibe-orchestrate <query>` | Multi-skill orchestration |

## Usage

```bash
vibe route --slash "/vibe-help"
vibe route --slash "/vibe-list --installed"
vibe route --slash "/vibe-analyze --deep"
vibe route --slash "/vibe-install superpowers"
```
"""


def render_docs_files(output_dir: Path, skills: list[Any]) -> list[Path]:
    """Render all docs/ files for a platform adapter.

    Shared between OpenCode and Kimi CLI adapters. Creates:
    - docs/routing.md
    - docs/session-lifecycle.md
    - docs/skills-catalog.md
    - docs/quick-commands.md

    Args:
        output_dir: Platform output directory (docs/ will be created inside).
        skills: List of skill definitions from the manifest.

    Returns:
        List of created file paths.
    """
    docs_dir = output_dir / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    created: list[Path] = []

    docs = {
        "routing.md": generate_docs_routing(),
        "session-lifecycle.md": generate_docs_session_lifecycle(),
        "skills-catalog.md": generate_docs_skills_catalog(skills),
        "quick-commands.md": generate_docs_quick_commands(),
    }

    for filename, content in docs.items():
        path = docs_dir / filename
        path.write_text(content, encoding="utf-8")
        created.append(path)

    return created


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

    return template.render(
        skill=skill_dict,
        metadata={
            "created_at": datetime.now(),
            "version": version,
        },
        version=version,
    )


__all__ = [
    "find_skill_content",
    "generate_docs_quick_commands",
    "generate_docs_routing",
    "generate_docs_session_lifecycle",
    "generate_docs_skills_catalog",
    "generate_fallback_skill_content",
    "generate_slim_agents_index",
    "is_pack_installed",
    "normalize_skill_type",
    "render_docs_files",
    "render_route_hook",
    "render_skill_md",
]
