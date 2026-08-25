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

    Windows paths (``C:\\Users\\x``) additionally drop the drive colon — a
    mid-path ``C:`` component is re-rooted to the drive by Win32 path
    resolution, which would point discovery at the wrong tree entirely.
    """
    return str(cwd).replace("/", "-").replace("\\", "-").replace(":", "")


def _discover_jsonl_files(project_dir: Path) -> list[Path]:
    """Return all ``.jsonl`` files under a Claude project dir, newest-first."""
    if not project_dir.exists():
        return []
    return sorted(project_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)


def _resolve_capture_depth(cli_value: str) -> str:
    """Resolve capture_depth: CLI flag wins; else read config; else 'standard'.

    Reads ``conversation_mirror.capture_depth`` from .vibe/config.toml. Any
    unrecognized value (CLI or config) falls back to ``standard`` — the
    parser's own coercion handles the actual validation, this just sources
    the value.
    """
    if cli_value:
        return cli_value
    try:
        from vibesop.core.config.manager import ConfigManager

        config_val = ConfigManager(Path.cwd()).get("conversation_mirror.capture_depth", "")
        if isinstance(config_val, str) and config_val.strip():
            return config_val.strip()
    except Exception:
        logger.debug("capture_depth config lookup failed, defaulting to 'standard'")
    return "standard"


def _resolve_max_history() -> int | None:
    """Read ``conversation_mirror.max_history`` from config, if set.

    Returns None when the key is absent — the caller's own default
    (200 for import_session, 200 for live mirror) is then used. Both
    paths MUST agree on the default; otherwise live-captured turns
    get truncated at 10 while batch-imported turns survive to 200.
    """
    try:
        from vibesop.core.config.manager import ConfigManager

        val = ConfigManager(Path.cwd()).get("conversation_mirror.max_history", None)
        if isinstance(val, int) and val > 0:
            return val
    except Exception:
        logger.debug("max_history config lookup failed")
    return None


# Both batch-import and live-mirror paths use this default. ConversationContext
# itself defaults to 10 (tuned for routing hints), which is wrong for mirror —
# silently truncates real conversations. Caller must override.
_MIRROR_DEFAULT_MAX_HISTORY = 200


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
    capture_depth: str = typer.Option(
        "",
        "--capture-depth",
        help=(
            "How much to capture: 'minimal' (text only), 'standard' (default; "
            "+thinking +tool keys +tool_result is_error +model/usage), "
            "'full' (+tool_result content_preview, 200 chars). "
            "Empty = read from conversation_mirror.capture_depth config."
        ),
    ),
    purge: bool = typer.Option(
        False,
        "--purge",
        help=(
            "Delete the target conversation file before importing. Use this "
            "after upgrading capture_depth to avoid duplicate 'thin' + 'rich' "
            "turns from pre-Path-1 mirror files."
        ),
    ),
    include_subagents: bool = typer.Option(
        True,
        "--include-subagents/--no-include-subagents",
        help=(
            "Also import each sub-agent transcript (Claude Code stores them "
            "under <session-id>/subagents/agent-*.jsonl). Each spawns its "
            "own mirror conversation so the dashboard surfaces the sub-agent's "
            "internal thinking/tool calls. Disable for top-level-only mirror."
        ),
    ),
) -> None:
    """Batch-import Claude Code transcript(s) into .vibe/conversations/."""
    from vibesop.core.conversation_import import (
        append_parsed_turns,
        derive_subagent_conversation_id,
        discover_subagents,
        import_subagent,
        parse_claude_jsonl,
    )

    depth = _resolve_capture_depth(capture_depth)
    max_history = _resolve_max_history() or _MIRROR_DEFAULT_MAX_HISTORY

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

    console.print(f"[dim]capture_depth={depth}[/dim]")

    total_new = 0
    total_skip = 0
    total_subagents = 0
    total_sub_new = 0
    for path, cid in targets:
        # Detect pre-Path-1 "thin" turns BEFORE import — warn user about
        # the duplicate-append failure mode (found by grok+pi review).
        target_file = storage_dir / f"{cid}.json"
        if target_file.exists() and not purge and _file_has_thin_turns(target_file):
            console.print(
                f"[yellow]Warning:[/yellow] {cid}.json contains pre-Path-1 turns "
                f"(no thinking/tool_calls fields). Re-importing will append duplicates. "
                f"Pass --purge to wipe + re-import cleanly."
            )

        if purge and target_file.exists():
            target_file.unlink()
            console.print(f"[dim]Purged {target_file.name}[/dim]")

        # Single parse — append_parsed_turns consumes the list directly,
        # avoiding the previous double-parse (found by pi review).
        parsed = parse_claude_jsonl(path, capture_depth=depth)
        new_count, skipped = append_parsed_turns(parsed, cid, storage_dir, max_history=max_history)
        total_new += new_count
        total_skip += skipped
        console.print(
            f"Imported {new_count} new turns into {cid} ({skipped} skipped as duplicates) "
            f"from {path.name}"
        )

        # Phase 2: sub-agent transcripts live under <session>/subagents/.
        # Each becomes its own mirror conversation so the dashboard shows
        # the sub-agent's internal thinking/tool calls — without this the
        # user only sees the parent's Task tool_use block.
        if include_subagents:
            subagents = discover_subagents(path)
            if subagents:
                console.print(
                    f"[dim]Discovered {len(subagents)} sub-agent transcript(s) "
                    f"for {path.stem}[/dim]"
                )
            for idx, record in enumerate(subagents, start=1):
                sub_cid = derive_subagent_conversation_id(cid, record)
                # When --purge is set the parent file was wiped above; apply
                # the same to sub-agent conversations so re-imports stay clean.
                sub_target = storage_dir / f"{sub_cid}.json"
                if purge and sub_target.exists():
                    sub_target.unlink()
                    console.print(f"[dim]Purged {sub_target.name}[/dim]")
                sub_new = import_subagent(
                    record,
                    sub_cid,
                    storage_dir,
                    parent_session_id=path.stem,
                    max_history=max_history,
                    capture_depth=depth,
                    parent_conversation_id=cid,
                )
                total_subagents += 1
                total_sub_new += sub_new
                agent_type = record.meta.get("agentType") or "agent"
                desc = record.meta.get("description") or ""
                label = f"{agent_type}"
                if desc:
                    label += f" — {desc[:60]}"
                console.print(
                    f"  ↳ sub-agent {idx}/{len(subagents)}: {sub_new} new turns "
                    f"into {sub_cid} [{label}]"
                )

    footer = (
        f"[green]Done:[/green] {total_new} new turn(s) across {len(targets)} session(s), "
        f"{total_skip} duplicate(s) skipped."
    )
    # Only mention sub-agents when there were any — avoids noisy "0 sub-agent
    # turn(s)" tail on sessions that never spawned a Task.
    if include_subagents and total_subagents > 0:
        footer += (
            f" [cyan]+ {total_sub_new} sub-agent turn(s) across "
            f"{total_subagents} sub-agent transcript(s).[/cyan]"
        )
    console.print(footer)


def _file_has_thin_turns(path: Path) -> bool:
    """Detect pre-Path-1 mirror files lacking thinking/tool_calls fields.

    Returns True if the file has at least one turn that lacks ALL Path-1
    extension keys (thinking, tool_calls, tool_results). Used to warn the
    user before re-import creates duplicate "thin + rich" turns.
    """
    import json

    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return False
    turns = data.get("turns", []) if isinstance(data, dict) else []
    if not turns:
        return False
    # Thin = none of the Path-1 fields present in this turn's dict
    path1_keys = ("thinking", "tool_calls", "tool_results", "model", "usage", "stop_reason")
    for t in turns:
        if not isinstance(t, dict):
            continue
        if not any(k in t for k in path1_keys):
            return True
    return False


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
    max_history = _resolve_max_history() or _MIRROR_DEFAULT_MAX_HISTORY
    context = ConversationContext(
        conversation_id=conversation_id,
        storage_dir=storage_dir,
        max_history=max_history,
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
