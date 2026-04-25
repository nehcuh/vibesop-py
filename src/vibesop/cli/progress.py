"""Rich Live progress display for orchestration streaming.

Provides a CLI implementation of OrchestrationCallbacks that renders
real-time progress during the orchestration pipeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from vibesop.core.orchestration.callbacks import (
    OrchestrationPhase,
)

if TYPE_CHECKING:
    from vibesop.core.models import ExecutionPlan
    from vibesop.core.orchestration.callbacks import (
        ErrorPolicy,
        PhaseInfo,
    )


class LiveOrchestrationCallbacks:
    """Rich Live display for orchestration progress.

    Example:
        >>> callbacks = LiveOrchestrationCallbacks()
        >>> with callbacks:
        ...     result = router.orchestrate(query, callbacks=callbacks)
    """

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()
        self._live: Live | None = None
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold]{task.description}"),
            console=self.console,
            transient=True,
        )
        self._task_id = self._progress.add_task("Initializing...", total=None)
        self._phases: list[tuple[OrchestrationPhase, str]] = []

    def __enter__(self) -> LiveOrchestrationCallbacks:
        self._live = Live(self._render(), console=self.console, refresh_per_second=4)
        self._live.start()
        return self

    def __exit__(self, *args: object) -> None:
        if self._live:
            self._live.stop()
            self._live = None

    def _render(self) -> Panel:
        """Render current state as a Rich Panel."""
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Status", width=3)
        table.add_column("Phase", style="bold")
        table.add_column("Detail", style="dim")

        for phase, message in self._phases:
            icon = {
                "routing": "🔍",
                "detection": "🧠",
                "decomposition": "📝",
                "plan_building": "🔀",
                "execution": "⚡",
                "complete": "✅",
            }.get(phase.value, "•")
            table.add_row(icon, phase.value.replace("_", " ").title(), message)

        current = self._progress.tasks[self._task_id].description
        if current and current != "Initializing...":
            table.add_row(
                "⏳",
                "[bold cyan]Current[/bold cyan]",
                current,
            )

        return Panel(
            table,
            title="[bold]Orchestration Progress[/bold]",
            border_style="blue",
        )

    def _update(self, message: str) -> None:
        """Update the live display."""
        self._progress.update(self._task_id, description=message)
        if self._live:
            self._live.update(self._render())

    def on_phase_start(self, info: PhaseInfo) -> None:
        """Called when a new phase begins."""
        self._update(info.message)

    def on_phase_complete(self, info: PhaseInfo) -> None:
        """Called when a phase completes successfully."""
        self._phases.append((info.phase, info.message))
        self._update(info.message)

    def on_phase_error(
        self,
        info: PhaseInfo,
        error: Exception,
        policy: ErrorPolicy,
    ) -> ErrorPolicy:
        """Called when a phase encounters an error."""
        self._phases.append((info.phase, f"[red]Error: {error}[/red]"))
        self._update(f"Error in {info.phase.value}: {error}")
        return policy

    def on_plan_ready(self, plan: ExecutionPlan) -> None:
        """Called when the execution plan is fully built."""
        self._phases.append((
            OrchestrationPhase.PLAN_BUILDING,
            f"Plan ready: {len(plan.steps)} steps ({plan.execution_mode.value})",
        ))
