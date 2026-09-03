"""Config/doc generation utilities — render documentation, hooks, and agent indices.

These functions generate platform configuration output:
  - render_route_hook: Jinja2 shell hook script
  - generate_slim_agents_index: AGENTS.md index
  - generate_docs_routing/session_lifecycle/skills_catalog/quick_commands
  - render_docs_files: batch doc file writer
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from jinja2 import FileSystemLoader, select_autoescape

from vibesop._version import __version__
from vibesop.adapters._content import detect_tool_environment
from vibesop.utils.jinja_safety import make_shell_safe_env

logger = logging.getLogger(__name__)

# After vibe route / hook inject, the real file is skill_file / NEXT STEP —
# often `.vibe/skills/**/{id}.skill/SKILL.md`, not skills/<id>/SKILL.md.
READ_ROUTED_SKILL_MD = (
    "then read the SKILL.md path from the routing result "
    "(`skill_file` in JSON, or the `SKILL.md:` / `NEXT STEP` line). "
    "Do not guess `skills/<id>/SKILL.md`."
)
READ_STEP_SKILL_MD = (
    "Read each step's `skill_file` path (or the SKILL.md line on that step). "
    "Do not guess `skills/<id>/SKILL.md`."
)


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
    hook_routing: bool = False,
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
        hook_routing: Whether the platform registers a routing hook
            (event registration is the sole criterion). ``True`` renders
            the conditional routing copy (hook injection first, CLI as
            fallback); ``False`` (default) keeps the imperative CLI-first
            copy so the CLI channel survives on hook-less platforms.

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

    if hook_routing:
        routing_protocol = f"""\
Routing is automatic when a VibeSOP hook is installed. If the current
user prompt arrives with a hook injection — look for `VibeSOP routed:`,
`[ACTIVE SKILL:`, `NEXT STEP (MANDATORY): read`, or
`VibeSOP: No matching skill found` — routing has already run for this
prompt: follow that result and do NOT re-run `vibe route`.

If no such injection is present on the current prompt (hook not
installed or failed), run:

    vibe route "<user_request>"

{READ_ROUTED_SKILL_MD}

User-typed `/vibe-*` commands still go through `vibe route --slash`
(see Quick Commands). Human-invoked CLI discovery is unchanged."""
    else:
        then_read = READ_ROUTED_SKILL_MD[0].upper() + READ_ROUTED_SKILL_MD[1:]
        routing_protocol = f"""\
**MANDATORY: Call `vibe route` before any non-trivial task.**

```bash
vibe route "<user_request>"
```

{then_read}"""

    tool_env = detect_tool_environment()
    if tool_env:
        tool_env = tool_env + "\n---\n"

    return f"""# VibeSOP Configuration

> **Version**: {version}
> **Generated**: {now}

{tool_env}
## Routing Protocol

{routing_protocol}

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


def generate_docs_routing(*, hook_routing: bool = False) -> str:
    """Generate docs/routing.md with detailed routing protocol.

    This content was previously inlined in the main AGENTS.md.
    Moved here to keep the index slim and reduce staleness risk.

    Args:
        hook_routing: Whether the platform registers a routing hook.
            ``True`` renders an injection-first Workflow (recognize the
            hook fingerprints, CLI only as fallback); ``False`` (default)
            keeps the CLI-first Workflow.
    """
    if hook_routing:
        workflow = """\
## Workflow (execute in order)

1. **Check injection**: If the current user prompt arrives with a hook
   injection — `VibeSOP routed:`, `[ACTIVE SKILL:`, or
   `NEXT STEP (MANDATORY): read` (or
   `VibeSOP: No matching skill found`) — routing has already run for
   this prompt: follow that result and skip to step 3. Do NOT re-run
   `vibe route`.
2. **Route** (fallback, only when no injection is present):
   `vibe route "<user_request>"` — use the user's EXACT words
3. **Read**: the `skill_file` / `NEXT STEP` / `SKILL.md:` path — do not guess `skills/<id>/SKILL.md`
4. **Execute**: Follow the skill's steps exactly
5. **Verify**: Run checks the skill requires"""
    else:
        workflow = """\
## Workflow (execute in order)

1. **Route**: `vibe route "<user_request>"` — use the user's EXACT words
2. **Read**: the `skill_file` / `SKILL.md:` path — do not guess `skills/<id>/SKILL.md`
3. **Execute**: Follow the skill's steps exactly
4. **Verify**: Run checks the skill requires"""

    return f"""# Routing Protocol

{workflow}

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
2. {READ_STEP_SKILL_MD}
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
- Run `vibe route --slash "/session-end"` and read the printed `skill_file` / `NEXT STEP` path. Do not guess `skills/session-end/SKILL.md`.
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


def render_docs_files(
    output_dir: Path,
    skills: list[Any],
    *,
    hook_routing: bool = False,
) -> list[Path]:
    """Render all docs/ files for a platform adapter.

    Shared between OpenCode and Kimi CLI adapters. Creates:
    - docs/routing.md
    - docs/session-lifecycle.md
    - docs/skills-catalog.md
    - docs/quick-commands.md

    Args:
        output_dir: Platform output directory (docs/ will be created inside).
        skills: List of skill definitions from the manifest.
        hook_routing: Forwarded to ``generate_docs_routing`` — ``True``
            on platforms with a registered routing hook.

    Returns:
        List of created file paths.
    """
    docs_dir = output_dir / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    created: list[Path] = []

    docs = {
        "routing.md": generate_docs_routing(hook_routing=hook_routing),
        "session-lifecycle.md": generate_docs_session_lifecycle(),
        "skills-catalog.md": generate_docs_skills_catalog(skills),
        "quick-commands.md": generate_docs_quick_commands(),
    }

    for filename, content in docs.items():
        path = docs_dir / filename
        path.write_text(content, encoding="utf-8")
        created.append(path)

    return created


__all__ = [
    "generate_docs_quick_commands",
    "generate_docs_routing",
    "generate_docs_session_lifecycle",
    "generate_docs_skills_catalog",
    "generate_slim_agents_index",
    "render_docs_files",
    "render_route_hook",
]
