"""``vibe sequence`` — tool-sequence capture & assembly (P3: distillation data source).

- ``vibe sequence record-tool``: called by the Claude Code PostToolUse hook;
  reads the hook event JSON from stdin and appends a minimal entry (tool name
  + timestamp + session id, never tool_input) to ``.vibe/tool_sequences.jsonl``.
- ``vibe sequence assemble``: fold new capture entries into instinct sequence
  patterns (application-only telemetry, success=False).
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import typer
from rich.console import Console

logger = logging.getLogger(__name__)

app = typer.Typer(
    help="Tool-sequence capture for skill distillation (P3).",
    no_args_is_help=True,
)
console = Console()


def _sequences_enabled(project_root: Path) -> bool:
    """Read the ``sequences.enabled`` switch (default true).

    Same reading pattern as ``suggestions.enabled`` (env vars arrive as raw
    strings). Fail-open: a broken config must not silently disable capture.
    """
    try:
        from vibesop.core.config.manager import ConfigManager

        enabled = ConfigManager(project_root).get("sequences.enabled", True)
        if isinstance(enabled, str):  # env vars are returned as raw strings
            enabled = enabled.strip().lower() in ("true", "1", "yes", "on")
        return bool(enabled)
    except Exception:
        logger.debug("sequences.enabled lookup failed, defaulting to enabled", exc_info=True)
        return True


@app.command("record-tool")
def record_tool(
    project_root: Path = typer.Option(
        Path(), "--project-root", help="Project root (where .vibe/ lives). Defaults to cwd."
    ),
) -> None:
    """Record one Claude Code PostToolUse hook event, read as JSON from stdin.

    Only the tool name, a local timestamp, and the session id are persisted —
    ``tool_input`` (paths, secrets) is NEVER written. Malformed input is
    dropped silently and the command always exits 0: a hook must never block
    the host agent.
    """
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else None
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        try:
            if _sequences_enabled(project_root):
                from vibesop.core.instinct.tool_sequences import record_tool_event

                record_tool_event(payload, project_root)
        except Exception:  # capture must never block the host agent
            logger.debug("tool-sequence record failed", exc_info=True)
    raise typer.Exit(0)


@app.command("assemble")
def assemble(
    project_root: Path = typer.Option(
        Path(), "--project-root", help="Project root (where .vibe/ lives). Defaults to cwd."
    ),
) -> None:
    """Fold captured tool sequences into instinct sequence patterns.

    Groups new entries (since the last assembly watermark) by session id —
    session-less entries fall back to 30-minute time windows — and records
    every group of ≥3 tool calls as application-only telemetry
    (``record_sequence(..., success=False)``).
    """
    from vibesop.core.instinct.tool_sequences import assemble_tool_sequences

    try:
        fed = assemble_tool_sequences(project_root)
    except Exception as e:
        console.print(f"[red]✗[/red] Assembly failed: {e}")
        raise typer.Exit(1) from None
    console.print(f"[green]✓[/green] Fed {fed} tool sequence(s) into instinct learning.")


if __name__ == "__main__":
    app()
