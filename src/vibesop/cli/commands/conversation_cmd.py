"""``vibe conversation`` — Claude Code conversation mirror utilities.

- ``vibe conversation import-claude``: batch-import a Claude Code transcript
  jsonl into ``.vibe/conversations/<id>.json`` for dashboard visibility.
- ``vibe conversation append-turn``: real-time hook entry point called by
  the UserPromptSubmit / PostToolUse mirror hooks (Phase 2, Path A).
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import typer
from rich.console import Console

logger = logging.getLogger(__name__)

app = typer.Typer(
    help="Conversation mirror — sync Claude Code transcripts for dashboard view.",
    no_args_is_help=True,
)
console = Console()


def _escape_cwd_as_project_dir(cwd: Path) -> str:
    """Mirror Claude Code's project-dir escaping: ``/`` → ``-``.

    e.g. ``/Users/huchen/Projects/vibesop-py`` → ``-Users-huchen-Projects-vibesop-py``.
    """
    return str(cwd).replace("/", "-")


def _discover_jsonl_files(project_dir: Path) -> list[Path]:
    """Return all ``.jsonl`` files under a Claude project dir, newest-first."""
    if not project_dir.exists():
        return []
    return sorted(project_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)


@app.command("import-claude")
def import_claude(
    source: Path = typer.Option(
        Path(),
        "--source",
        help=(
            "Path to a Claude Code .jsonl transcript, or a directory containing them. "
            "Empty = auto-discover from ~/.claude/projects/<escaped-cwd>/."
        ),
    ),
    conversation_id: str = typer.Option(
        "",
        "--conversation-id",
        help="Mirror conversation ID. Empty = derive from jsonl filename (mirror-claude-<stem>).",
    ),
    storage_dir: Path = typer.Option(
        Path(".vibe/conversations"),
        "--storage-dir",
        help="Where to write the mirrored conversation file.",
    ),
    all_sessions: bool = typer.Option(
        False,
        "--all-sessions",
        help="When --source is a directory, import every .jsonl as a separate conversation.",
    ),
) -> None:
    """Batch-import Claude Code transcript(s) into .vibe/conversations/."""
    from vibesop.core.conversation_import import import_session

    # Resolve the list of (source_path, conversation_id) pairs to process.
    targets: list[tuple[Path, str]] = []

    if str(source) in ("", "."):
        # Auto-discover: ~/.claude/projects/<escaped-cwd>/
        project_dir = Path.home() / ".claude" / "projects" / _escape_cwd_as_project_dir(Path.cwd())
        jsonl_files = _discover_jsonl_files(project_dir)
        if not jsonl_files:
            console.print(
                f"[red]Error:[/red] no Claude jsonl found at {project_dir}. "
                "Pass --source explicitly."
            )
            raise typer.Exit(1)
        selected = jsonl_files if all_sessions else jsonl_files[:1]
        for path in selected:
            cid = conversation_id or f"mirror-claude-{path.stem}"
            targets.append((path, cid))
    elif source.is_file():
        cid = conversation_id or f"mirror-claude-{source.stem}"
        targets.append((source, cid))
    elif source.is_dir():
        jsonl_files = sorted(source.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not jsonl_files:
            console.print(f"[red]Error:[/red] no .jsonl files in directory {source}.")
            raise typer.Exit(1)
        selected = jsonl_files if all_sessions else jsonl_files[:1]
        for path in selected:
            cid = conversation_id or f"mirror-claude-{path.stem}"
            targets.append((path, cid))
    else:
        console.print(f"[red]Error:[/red] source path does not exist: {source}")
        raise typer.Exit(1)

    if not targets:
        console.print("[red]Error:[/red] no sessions to import.")
        raise typer.Exit(1)

    total_new = 0
    total_skip = 0
    for path, cid in targets:
        from vibesop.core.conversation_import import parse_claude_jsonl

        parsed_count = len(parse_claude_jsonl(path))
        new_count = import_session(path, cid, storage_dir)
        skipped = parsed_count - new_count
        total_new += new_count
        total_skip += skipped
        console.print(
            f"Imported {new_count} new turns into {cid} ({skipped} skipped as duplicates) "
            f"from {path.name}"
        )

    console.print(
        f"[green]Done:[/green] {total_new} new turn(s) across {len(targets)} session(s), "
        f"{total_skip} duplicate(s) skipped."
    )


# ----------------------------------------------------------------------
# Phase 2 (Path A): real-time mirror hook entry point
# ----------------------------------------------------------------------

# Conversation id prefix for mirror-captured turns — same convention used by
# ``import-claude`` so the dashboard groups them under a single origin.
_MIRROR_CONV_PREFIX = "mirror-claude-"
# Truncate session-derived ids so dashboard listings stay readable and
# filesystem paths stay short.
_MIRROR_CONV_ID_MAX = 20


def _resolve_mirror_conversation_id(payload: dict[str, Any]) -> str:
    """Derive a stable conversation id for a mirror hook payload.

    Resolution order: ``payload['session_id']`` → ``$CLAUDE_SESSION_ID`` →
    a timestamped fallback. Session-derived ids are prefixed with
    ``mirror-claude-`` (so they're visually distinct from CLI conversations)
    and truncated for readability.
    """
    session_id = payload.get("session_id")
    if not session_id:
        session_id = os.environ.get("CLAUDE_SESSION_ID")
    if session_id:
        return _MIRROR_CONV_PREFIX + str(session_id)[:_MIRROR_CONV_ID_MAX]
    return f"mirror-{int(time.time())}"


def _extract_user_prompt(payload: dict[str, Any]) -> str:
    """Pull the user's prompt text from a UserPromptSubmit payload.

    Claude Code uses ``prompt``; we accept a few aliases so the hook is
    robust to small upstream schema drift.
    """
    for key in ("prompt", "user_prompt", "query", "message", "text"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _format_tool_content(payload: dict[str, Any]) -> str:
    """Build a privacy-safe summary string for a PostToolUse payload.

    Format: ``ToolName(arg1, arg2)`` — only argument KEYS are persisted,
    never values. ``tool_input`` may contain paths or secrets, so we
    explicitly do NOT include any of its values.
    """
    tool_name = payload.get("tool_name") or payload.get("tool") or "Unknown"
    raw_input = payload.get("tool_input")
    if raw_input is None:
        raw_input = payload.get("args")
    keys = ", ".join(sorted(raw_input.keys())) if isinstance(raw_input, dict) else ""
    return f"{tool_name}({keys})"


def _dispatch_mirror_event(payload: dict[str, Any], project_root: Path) -> None:
    """Dispatch one mirror hook payload to the right turn shape.

    Routes by ``hook_event_name``:

    - ``UserPromptSubmit`` → user turn (role=user, query=prompt, content=None)
    - ``PostToolUse`` → tool turn (role=tool, query="", content=summary)
      where the summary is ``ToolName(arg1, arg2)`` — only KEYS, never values.
    - any other event → silently skipped (debug log).

    All turns land in ``<project_root>/.vibe/conversations/<id>.json``.
    """
    from vibesop.core.conversation import ConversationContext

    event = payload.get("hook_event_name")
    if event == "UserPromptSubmit":
        query = _extract_user_prompt(payload)
        content: str | None = None
        role = "user"
    elif event == "PostToolUse":
        query = ""
        content = _format_tool_content(payload)
        role = "tool"
    else:
        logger.debug("conversation mirror: skipping event %r", event)
        return

    conversation_id = _resolve_mirror_conversation_id(payload)
    storage_dir = project_root.resolve() / ".vibe" / "conversations"
    context = ConversationContext(
        conversation_id=conversation_id, storage_dir=storage_dir
    )
    context.add_turn(query=query, skill_id=None, intent=None, role=role, content=content)


@app.command("append-turn")
def append_turn(
    project_root: Path = typer.Option(
        Path(),
        "--project-root",
        help="Project root for storage resolution (where .vibe/ lives). Defaults to cwd.",
    ),
) -> None:
    """stdin JSON → ConversationContext.add_turn. Hook entry point.

    Called by ``vibesop-mirror-prompt.sh.j2`` (UserPromptSubmit) and the
    PostToolUse mirror variant. Reads a JSON envelope from stdin, extracts
    role+content by ``hook_event_name``, and appends a turn. Always exits
    0 — hook contract: never block the host agent.
    """
    import sys

    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else None
    except json.JSONDecodeError:
        payload = None

    try:
        if isinstance(payload, dict):
            _dispatch_mirror_event(payload, project_root)
    except Exception:
        logger.debug("conversation mirror append-turn failed", exc_info=True)

    raise typer.Exit(0)
