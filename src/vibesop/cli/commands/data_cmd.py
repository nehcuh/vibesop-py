"""``vibe data`` — manage VibeSOP-derived data.

Provides a deletion path (``vibe data purge``) for the prompt-derived data
VibeSOP persists — analytics, traces, preferences, instincts, memory, and
feedback (F-08). Without it, every routed prompt is effectively permanent.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(help="Manage VibeSOP-derived data.", no_args_is_help=True)
console = Console()


@app.callback()
def _main() -> None:  # pyright: ignore[reportUnusedFunction]
    """Manage VibeSOP-derived data (purge)."""


@app.command()
def purge(
    all: bool = typer.Option(
        False, "--all", help="Purge ALL VibeSOP-derived data (every target below)."
    ),
    analytics: bool = typer.Option(False, "--analytics", help="Purge .vibe/analytics.jsonl."),
    traces: bool = typer.Option(False, "--traces", help="Purge .vibe/traces/*.json."),
    preferences: bool = typer.Option(False, "--preferences", help="Purge learned preferences."),
    instincts: bool = typer.Option(False, "--instincts", help="Purge learned instincts."),
    memory: bool = typer.Option(False, "--memory", help="Purge conversation memory."),
    sessions: bool = typer.Option(False, "--sessions", help="Purge .vibe/session/*.json."),
    feedback: bool = typer.Option(
        False, "--feedback", help="Purge feedback records (global ~/.vibe/feedback.jsonl)."
    ),
    yes: bool = typer.Option(False, "-y", "--yes", help="Skip the confirmation prompt."),
    project_root: Path = typer.Option(
        Path(), "--project-root", help="Project root (where .vibe/ lives)."
    ),
) -> None:
    """Permanently delete VibeSOP-derived data (F-08: user deletion path)."""
    if all:
        analytics = traces = preferences = instincts = memory = sessions = feedback = True
    if not (analytics or traces or preferences or instincts or memory or sessions or feedback):
        console.print(
            "[red]No purge target selected.[/red] Pass --all, or one of "
            "--analytics/--traces/--preferences/--instincts/--memory/--sessions/--feedback."
        )
        raise typer.Exit(code=2)

    if not yes and not typer.confirm(
        "This permanently deletes the selected data. Continue?", default=False
    ):
        console.print("[yellow]Aborted — nothing was changed.[/yellow]")
        raise typer.Exit(code=0)

    vibe_dir = project_root / ".vibe"
    cleared: list[str] = []

    if analytics:
        from vibesop.core.analytics import AnalyticsStore

        n = AnalyticsStore(storage_dir=vibe_dir).clear()
        cleared.append(f"analytics: {n} record(s)")
    if traces:
        from vibesop.core.routing.tracer import RoutingTracer

        n = RoutingTracer(traces_dir=vibe_dir / "traces").clear()
        cleared.append(f"traces: {n} file(s)")
    if preferences:
        from vibesop.core.preference import PreferenceLearner

        PreferenceLearner(storage_path=vibe_dir / "preferences.json").clear()
        cleared.append("preferences: cleared")
    if instincts:
        from vibesop.core.instinct.learner import InstinctLearner

        n = InstinctLearner(storage_path=vibe_dir / "instincts.jsonl").clear()
        cleared.append(f"instincts: {n} pattern(s)")
    if memory:
        from vibesop.core.memory import MemoryManager

        MemoryManager(storage_dir=vibe_dir / "memory").clear_all()
        cleared.append("memory: cleared")
    if sessions:
        session_dir = vibe_dir / "session"
        files = list(session_dir.glob("*.json")) if session_dir.exists() else []
        for f in files:
            f.unlink()
        cleared.append(f"sessions: {len(files)} file(s)")
    if feedback:
        from vibesop.core.feedback import ExecutionFeedbackCollector, FeedbackCollector

        FeedbackCollector().clear_records()
        ExecutionFeedbackCollector().clear_records()
        cleared.append("feedback: cleared")

    console.print("[green]Purged:[/green]")
    for line in cleared:
        console.print(f"  • {line}")


if __name__ == "__main__":
    app()
