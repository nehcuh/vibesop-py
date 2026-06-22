"""Loop models — autonomous scheduled task definitions for VibeSOP.

This module defines data types for time-based autonomous loops, distinct
from the semantic ``LOOP_UNTIL_DRY`` pattern in ``WorkflowEngine``. A
"loop" here is a scheduled, recurring execution of a skill query — cron-
like time triggers, not until-convergent re-orchestration.

Design notes:
    - Uses pydantic ``BaseModel`` for consistency with ``core/models.py``
      (ExecutionPlan, ExecutionStep, AgentSquad are all BaseModel). This
      gives us free JSON round-trip via ``model_dump_json`` /
      ``model_validate_json`` — no hand-written serializers in store.py.
    - Field-level validators cover format checks (kebab-case name, cron
      shape). A model-level validator covers the cross-field "one of
      skill_id / query / workflow_id" constraint.
    - ``LoopState`` tracks runtime status (consecutive failures, recent
      runs) and is system-managed. ``LoopSpec`` is the user-editable
      definition. They are intentionally separate so users can git-track
      specs and gitignore state.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_NAME_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
# 5-field cron: minute hour day-of-month month day-of-week
# Each field accepts: * / N / N-M / N-M/S / N,M,K
_CRON_FIELD_PATTERN = re.compile(
    r"^\*|(?:\d+|\*/\d+|\d+-\d+(?:/\d+)?|\d+(?:,\d+)*)(?:,\d+|\d+-\d+(?:/\d+)?)*$"
)
_CRON_FIELD_RANGES: tuple[tuple[int, int], ...] = (
    (0, 59),  # minute
    (0, 23),  # hour
    (1, 31),  # day-of-month
    (1, 12),  # month
    (0, 6),  # day-of-week (0 = Sunday)
)


class LoopStatus(StrEnum):
    """Runtime status persisted to ``state.json``.

    System-managed; users may read but not directly edit.
    """

    ACTIVE = "active"  # Running normally
    PAUSED = "paused"  # User-paused (spec unchanged)
    FAILING = "failing"  # Consecutive failures under threshold
    DEAD = "dead"  # Exceeded max_failures, will not run again
    RETIRED = "retired"  # User-archived


class LoopTrigger(StrEnum):
    """How the loop is fired. v1 ships CRON only."""

    CRON = "cron"


class LoopSpec(BaseModel):
    """User-editable loop definition.

    Persisted to ``~/.vibe/loops/{name}/spec.json``. Tracked-into-git safe
    (no runtime state stored here).
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        ...,
        description="Globally unique identifier (kebab-case).",
        pattern=r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$",
    )
    description: str = Field(
        default="",
        description="Human-readable purpose. Cannot be empty.",
        min_length=1,
    )
    trigger: LoopTrigger = Field(
        default=LoopTrigger.CRON,
        description="Trigger type. v1 only supports CRON.",
    )
    schedule: str = Field(
        default="0 0 * * *",
        description="5-field cron expression: minute hour day month day-of-week.",
    )
    skill_id: str = Field(
        default="",
        description="Target skill ID. Mutually exclusive with query/workflow_id.",
    )
    query: str = Field(
        default="",
        description="Natural-language routing query. Mutually exclusive with skill_id/workflow_id.",
    )
    workflow_id: str = Field(
        default="",
        description="Cross-cutting workflow ID. Mutually exclusive with skill_id/query.",
    )
    max_failures: int = Field(
        default=3,
        ge=1,
        description="Consecutive failure count that flips status to DEAD.",
    )
    guard: str = Field(
        default="",
        description="Reserved for v2 human-approval gate. Empty in v1.",
    )
    tags: list[str] = Field(default_factory=list, description="Categorisation tags.")
    env_overrides: dict[str, str] = Field(
        default_factory=dict,
        description="Per-loop env var overrides applied at execution time.",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC creation timestamp.",
    )

    @field_validator("schedule")
    @classmethod
    def _validate_schedule(cls, v: str) -> str:
        parts = v.strip().split()
        if len(parts) != 5:
            raise ValueError(
                f"cron expression must have 5 fields (min hour day month dow), "
                f"got {len(parts)}: {v!r}"
            )
        for idx, (field_str, (lo, hi)) in enumerate(zip(parts, _CRON_FIELD_RANGES)):
            if field_str == "*":
                continue
            if not _CRON_FIELD_PATTERN.match(field_str):
                raise ValueError(f"cron field {idx} ({field_str!r}) has invalid syntax")
            for token in field_str.split(","):
                for piece in token.split("-"):
                    base = piece.split("/")[0]
                    if base and base.isdigit() and not (lo <= int(base) <= hi):
                        raise ValueError(f"cron field {idx} value {base} out of range [{lo}, {hi}]")
        return v

    @model_validator(mode="after")
    def _exactly_one_target(self) -> LoopSpec:
        targets = [self.skill_id, self.query, self.workflow_id]
        non_empty = [t for t in targets if t.strip()]
        if len(non_empty) != 1:
            raise ValueError(
                f"exactly one of skill_id / query / workflow_id must be set (got {len(non_empty)})"
            )
        return self


class LoopRunRecord(BaseModel):
    """Single loop execution record."""

    model_config = ConfigDict(extra="forbid")

    loop_name: str = Field(..., description="Name of the loop that was ticked.")
    started_at: datetime = Field(..., description="UTC start time.")
    finished_at: datetime | None = Field(default=None, description="UTC finish time.")
    success: bool = Field(default=False, description="Whether the tick succeeded.")
    matched_skill: str = Field(default="", description="Skill ID the runtime matched.")
    output_summary: str = Field(default="", description="Truncated decision message.")
    error: str = Field(default="", description="Error message on failure.")
    duration_s: float = Field(default=0.0, ge=0.0, description="Wall-clock duration in seconds.")


class LoopState(BaseModel):
    """Runtime state of a loop, persisted to ``state.json``.

    System-managed; mutation should go through ``record_run`` to keep
    status transitions consistent with ``max_failures``.
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    spec: LoopSpec = Field(..., description="The loop definition this state belongs to.")
    status: LoopStatus = Field(default=LoopStatus.ACTIVE, description="Runtime status.")
    consecutive_failures: int = Field(default=0, ge=0)
    total_runs: int = Field(default=0, ge=0)
    last_run_at: datetime | None = Field(default=None)
    last_success_at: datetime | None = Field(default=None)
    next_run_at: datetime | None = Field(default=None)
    recent_runs: list[LoopRunRecord] = Field(
        default_factory=list,
        description="Most recent runs (capped at 20).",
    )

    _RECENT_RUN_CAP: int = 20

    def record_run(self, record: LoopRunRecord) -> None:
        """Record one execution result and update status.

        Transition rules:
            - success: reset consecutive_failures to 0; status → ACTIVE
              (unless user-paused or DEAD — both are terminal until an
              explicit resume; a stray success must NOT revive a DEAD loop).
            - failure: increment consecutive_failures. If the count
              reaches ``spec.max_failures``, status → DEAD; otherwise
              status → FAILING. A PAUSED loop is left PAUSED — record_run
              is called only by the executor, which already skips paused
              loops, but we guard defensively.
        """
        self.total_runs += 1
        self.last_run_at = record.started_at
        self.recent_runs.append(record)
        if len(self.recent_runs) > self._RECENT_RUN_CAP:
            self.recent_runs = self.recent_runs[-self._RECENT_RUN_CAP :]

        if record.success:
            self.consecutive_failures = 0
            self.last_success_at = record.finished_at or record.started_at
            # PAUSED is sticky (cleared only by explicit resume). DEAD is also
            # terminal — a stray successful tick must NOT revive a DEAD loop and
            # zero its failure budget (revival is explicit). Pre-fix only PAUSED
            # was guarded, so one success revived DEAD -> ACTIVE.
            if self.status not in (LoopStatus.PAUSED, LoopStatus.DEAD):
                self.status = LoopStatus.ACTIVE
            return

        if self.status == LoopStatus.PAUSED:
            # Defensive: executor should not tick paused loops.
            return

        self.consecutive_failures += 1
        if self.consecutive_failures >= self.spec.max_failures:
            self.status = LoopStatus.DEAD
        else:
            self.status = LoopStatus.FAILING


__all__ = [
    "LoopRunRecord",
    "LoopSpec",
    "LoopState",
    "LoopStatus",
    "LoopTrigger",
]
