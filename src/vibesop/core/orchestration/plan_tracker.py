"""Plan tracker — persists and retrieves execution plan state.

Stores plans as JSONL in `.vibe/execution_plans.jsonl` for durability.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from vibesop.core.models import ExecutionPlan, PlanStatus, StepStatus

logger = logging.getLogger(__name__)


class PlanTracker:
    """Tracks execution plan state with append-only JSONL storage.

    Each plan update is appended as a new line. Latest state for a plan
    is found by reading all lines and taking the last one with matching plan_id.
    """

    def __init__(self, storage_dir: str | Path = ".vibe"):
        self.storage_path = Path(storage_dir) / "execution_plans.jsonl"
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

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

        Reads latest plan state, updates the step, and writes back.
        """
        plan = self.get_plan(plan_id)
        if plan is None:
            logger.warning("Plan %s not found for step update", plan_id)
            return

        for step in plan.steps:
            if step.step_id == step_id:
                if isinstance(status, StepStatus):
                    step.status = status
                else:
                    step.status = StepStatus(status)
                if result_summary is not None:
                    step.result_summary = result_summary
                break

        # Update plan status if all steps completed
        if all(s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED) for s in plan.steps):
            plan.status = PlanStatus.COMPLETED
        elif any(s.status == StepStatus.IN_PROGRESS for s in plan.steps):
            plan.status = PlanStatus.ACTIVE

        self._append(plan.to_dict())

    def get_active_plan(self) -> ExecutionPlan | None:
        """Get the most recently created plan that is not completed."""
        plans = self.list_plans(limit=10)
        for plan in reversed(plans):
            if plan.status in (PlanStatus.PENDING, PlanStatus.ACTIVE):
                return plan
        return None

    def get_plan(self, plan_id: str) -> ExecutionPlan | None:
        """Get latest state of a specific plan."""
        if not self.storage_path.exists():
            return None

        latest: dict[str, Any] | None = None
        try:
            with self.storage_path.open("r", encoding="utf-8") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    if data.get("plan_id") == plan_id:
                        latest = data
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Failed to read plan %s: %s", plan_id, e)
            return None

        if latest is None:
            return None

        return self._dict_to_plan(latest)

    def list_plans(self, limit: int = 10) -> list[ExecutionPlan]:
        """List most recently updated plans (unique by plan_id)."""
        if not self.storage_path.exists():
            return []

        seen: set[str] = set()
        plans: list[ExecutionPlan] = []

        try:
            with self.storage_path.open("r", encoding="utf-8") as f:
                lines = f.readlines()

            # Read from end to get latest first
            for raw_line in reversed(lines):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    plan_id = data.get("plan_id")
                    if plan_id and plan_id not in seen:
                        seen.add(plan_id)
                        plans.append(self._dict_to_plan(data))
                        if len(plans) >= limit:
                            break
                except json.JSONDecodeError:
                    continue
        except OSError as e:
            logger.warning("Failed to list plans: %s", e)

        # Return oldest-first for consistent ordering
        return list(reversed(plans))

    def _append(self, data: dict[str, Any]) -> None:
        """Append a plan state line to JSONL."""
        try:
            with self.storage_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
        except OSError as e:
            logger.error("Failed to write plan state: %s", e)

    def _dict_to_plan(self, data: dict[str, Any]) -> ExecutionPlan:
        """Rehydrate ExecutionPlan from dict."""
        from vibesop.core.models import ExecutionStep

        steps = [
            ExecutionStep(
                step_id=s["step_id"],
                step_number=s["step_number"],
                skill_id=s["skill_id"],
                intent=s.get("intent", ""),
                input_query=s.get("input_query", ""),
                output_as=s.get("output_as", ""),
                status=StepStatus(s.get("status", "pending")),
                result_summary=s.get("result_summary"),
                started_at=s.get("started_at"),
                completed_at=s.get("completed_at"),
            )
            for s in data.get("steps", [])
        ]

        return ExecutionPlan(
            plan_id=data["plan_id"],
            original_query=data.get("original_query", ""),
            steps=steps,
            detected_intents=data.get("detected_intents", []),
            reasoning=data.get("reasoning", ""),
            created_at=data.get("created_at", ""),
            status=PlanStatus(data.get("status", "pending")),
        )
