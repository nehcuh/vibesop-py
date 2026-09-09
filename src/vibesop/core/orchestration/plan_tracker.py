"""Plan tracker — persists and retrieves execution plan state.

Stores plans as JSONL in `.vibe/execution_plans.jsonl` for durability.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Generator, Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any

from vibesop.core.models import ExecutionPlan, PlanStatus, StepStatus
from vibesop.utils.file_lock import cross_process_lock

logger = logging.getLogger(__name__)

__all__ = ["PlanTracker", "load_plans_for_trace"]


def _lock_path_for(plans_path: Path) -> Path:
    """Sibling lock file per file_lock gate44 contract (never the data file)."""
    return plans_path.with_name(plans_path.name + ".lock")


@contextmanager
def _read_lock(plans_path: Path) -> Generator[None, None, None]:
    """Read-only mounts cannot create a lock; retain best-effort reads there.

    Only lock acquisition can fall back. Writers always require the lock.
    The line reader skips incomplete records if a non-cooperating writer races.
    """
    with ExitStack() as stack:
        try:
            stack.enter_context(cross_process_lock(_lock_path_for(plans_path), shared=True))
        except OSError as exc:
            logger.warning("Cannot lock plan store for reading %s: %s", plans_path, exc)
        yield


def _iter_valid_plans(plans_path: Path) -> Iterator[tuple[str, ExecutionPlan]]:
    """Yield ``(plan_id, plan)`` for every *valid* line, skipping corrupt ones.

    Uniform line semantics for get/list/load_plans_for_trace: a line that is
    truncated JSON, legal JSON of a non-object type, or an object whose schema
    cannot rebuild an ExecutionPlan is skipped WITHOUT aborting the rest of the
    file and WITHOUT masking an earlier valid version of the same plan_id.
    """
    if not plans_path.exists():
        return
    try:
        with plans_path.open("rb") as f:
            for raw_line in f:
                try:
                    line = raw_line.decode("utf-8").strip()
                except UnicodeDecodeError:
                    logger.warning("Skipping invalid UTF-8 plan line in %s", plans_path)
                    continue
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    logger.debug("Skipping unparseable plan line in %s", plans_path)
                    continue
                if not isinstance(data, dict):
                    logger.debug("Skipping non-object plan line in %s", plans_path)
                    continue
                plan_id = data.get("plan_id")
                if not isinstance(plan_id, str) or not plan_id:
                    logger.debug("Skipping plan line without string plan_id in %s", plans_path)
                    continue
                try:
                    plan = ExecutionPlan.from_dict(data)
                except Exception as e:
                    logger.warning(
                        "Skipping malformed plan line for %s in %s: %s",
                        plan_id,
                        plans_path,
                        e,
                    )
                    continue
                yield plan_id, plan
    except OSError as e:
        logger.warning("Failed to read plans from %s: %s", plans_path, e)


class PlanTracker:
    """Tracks execution plan state with append-only JSONL storage.

    Each plan update is appended as a new line. Latest state for a plan
    is found by reading all lines and taking the last *valid* one with
    matching plan_id. Reads take a shared cross-process lock and the
    read-modify-write in ``update_step_status`` holds an exclusive lock,
    so concurrent step updates from separate processes cannot lose each
    other's changes.
    """

    def __init__(self, storage_dir: str | Path = ".vibe"):
        self.storage_path = Path(storage_dir) / "execution_plans.jsonl"
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_path = _lock_path_for(self.storage_path)

    def create_plan(self, plan: ExecutionPlan) -> None:
        """Persist a new plan."""
        self._append(plan.to_dict())
        logger.debug("Created plan %s with %d steps", plan.plan_id, len(plan.steps))

    def update_step_status(
        self,
        plan_id: str,
        step_id: str,
        status: StepStatus,
        result_summary: str | None = None,
    ) -> None:
        """Update a step's status within a plan.

        Reads latest plan state, updates the step, and writes back — the
        whole read-modify-write cycle holds the exclusive cross-process
        lock so parallel updates to different steps of the same plan are
        serialized instead of losing one update.
        """
        with cross_process_lock(self._lock_path):
            latest: ExecutionPlan | None = None
            for pid, plan in self._iter_plans():
                if pid == plan_id:
                    latest = plan
            if latest is None:
                logger.warning("Plan %s not found for step update", plan_id)
                return

            for step in latest.steps:
                if step.step_id == step_id:
                    step.status = status if isinstance(status, StepStatus) else StepStatus(status)  # pyright: ignore[reportUnnecessaryIsInstance]
                    if result_summary is not None:
                        step.result_summary = result_summary
                    break

            # Update plan status if all steps completed
            if all(s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED) for s in latest.steps):
                latest.status = PlanStatus.COMPLETED
            elif any(s.status == StepStatus.IN_PROGRESS for s in latest.steps):
                latest.status = PlanStatus.ACTIVE

            self._append_locked(latest.to_dict())

    def get_active_plan(self) -> ExecutionPlan | None:
        """Get the most recently created plan that is not completed."""
        plans = self.list_plans(limit=10)
        for plan in reversed(plans):
            if plan.status in (PlanStatus.PENDING, PlanStatus.ACTIVE):
                return plan
        return None

    def get_plan(self, plan_id: str) -> ExecutionPlan | None:
        """Get latest valid state of a specific plan."""
        latest: ExecutionPlan | None = None
        with _read_lock(self.storage_path):
            for pid, plan in self._iter_plans():
                if pid == plan_id:
                    latest = plan
        return latest

    def list_plans(self, limit: int = 10) -> list[ExecutionPlan]:
        """List most recently updated plans (unique by plan_id)."""
        plans_by_id: dict[str, ExecutionPlan] = {}
        last_pos: dict[str, int] = {}
        with _read_lock(self.storage_path):
            for pos, (plan_id, plan) in enumerate(self._iter_plans()):
                plans_by_id[plan_id] = plan
                last_pos[plan_id] = pos

        selected = sorted(plans_by_id, key=lambda p: last_pos[p], reverse=True)[:limit]
        # Return oldest-first for consistent ordering
        return [plans_by_id[p] for p in reversed(selected)]

    def _iter_plans(self) -> Iterator[tuple[str, ExecutionPlan]]:
        """Unlocked read of valid lines — used inside critical sections only."""
        yield from _iter_valid_plans(self.storage_path)

    def _append(self, data: dict[str, Any]) -> None:
        """Append a plan state line to JSONL under the exclusive lock."""
        with cross_process_lock(self._lock_path):
            self._append_locked(data)

    def _append_locked(self, data: dict[str, Any]) -> None:
        """Unlocked append — caller must hold the exclusive lock."""
        try:
            with self.storage_path.open("a+b") as f:
                # A crash can leave an unterminated final line. Separate it
                # before appending so it cannot swallow the next valid update.
                if f.tell():
                    f.seek(-1, 2)
                    if f.read(1) != b"\n":
                        f.write(b"\n")
                f.write((json.dumps(data, ensure_ascii=False) + "\n").encode("utf-8"))
        except OSError as e:
            logger.error("Failed to write plan state: %s", e)


def load_plans_for_trace(
    trace_id: str,
    storage_dir: str | Path = ".vibe",
) -> list[ExecutionPlan]:
    """Return all plans whose ``metadata.trace_id`` matches ``trace_id``.

    Cross-process JOIN contract (v3 Phase A Task 10): the DAG rebuilder uses
    this to find plans that belong to a given trace root. Plans persisted
    before Task 10 lack ``metadata.trace_id`` and are silently skipped
    (NOT crashed on) so historical data stays readable.

    Line semantics match ``PlanTracker.get_plan()`` / ``list_plans()``:
    unparseable lines, legal-JSON non-objects, and schema-corrupted objects
    are skipped per line, and the last *valid* entry per ``plan_id`` wins.

    Args:
        trace_id: The root trace id produced by ``orchestrate()``.
        storage_dir: Directory containing ``execution_plans.jsonl``. Defaults
            to ``.vibe`` — same default as ``PlanTracker``.

    Returns:
        Plans whose latest valid persisted state has
        ``metadata.trace_id == trace_id``, deduplicated by ``plan_id``.
        Empty list if no match or the JSONL file does not exist.

    .. warning::
        ``storage_dir`` resolves relative to **CWD** when passed as a relative
        path. The Orchestrator writes to ``router.project_root / ".vibe"``
        (always absolute); callers reading from a different CWD will silently
        get ``[]``. **DAG rebuilder callers must pass an absolute path**
        (typically ``project_root / ".vibe"``) to avoid this footgun.
        (Flagged independently by grok + pi review of Task 10.)
    """
    plans_path = Path(storage_dir) / "execution_plans.jsonl"
    if not plans_path.exists():
        return []

    seen: dict[str, ExecutionPlan] = {}
    with _read_lock(plans_path):
        for plan_id, plan in _iter_valid_plans(plans_path):
            # Last valid write wins — append-only model means later lines
            # supersede earlier ones for the same plan_id.
            seen[plan_id] = plan

    result: list[ExecutionPlan] = []
    for plan in seen.values():
        metadata = plan.metadata or {}
        if metadata.get("trace_id") == trace_id:
            result.append(plan)
    return result
