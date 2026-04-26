"""Agent Execution Protocol — standard interface for AI Agents to execute plans.

Defines the contract between VibeSOP (plan producer) and AI Agents
(plan consumers). Agents implement this protocol to receive and report
multi-step execution plans.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from vibesop.core.models import ExecutionPlan


class StepResultStatus(StrEnum):
    """Status of a single step execution."""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StepResult:
    """Result of executing a single step in a plan."""

    step_id: str
    skill_id: str
    status: StepResultStatus
    output: str = ""
    error: str | None = None
    duration_ms: float = 0.0


@dataclass
class PlanExecutionResult:
    """Result of executing a full plan."""

    plan_id: str
    results: list[StepResult] = field(default_factory=list)

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.results if r.status == StepResultStatus.SUCCESS)

    @property
    def all_succeeded(self) -> bool:
        return all(r.status == StepResultStatus.SUCCESS for r in self.results)


class ExecutionProtocol:
    """Protocol for AI Agents to consume and report on execution plans.

    VibeSOP produces ExecutionPlan → Agent receives via this protocol
    Agent executes steps → Agent reports results via this protocol
    """

    @staticmethod
    def plan_to_agent_instructions(plan: ExecutionPlan) -> str:
        """Convert an ExecutionPlan into natural language instructions for the agent.

        The output is a Markdown-formatted string the AI Agent can directly
        use as a prompt for step-by-step execution.
        """
        lines = [
            f"# Execution Plan: {plan.original_query}",
            "",
            f"**Strategy**: {plan.execution_mode.value}",
            f"**Steps**: {len(plan.steps)}",
            f"**Reasoning**: {plan.reasoning}",
            "",
            "---",
            "",
        ]
        for step in plan.steps:
            deps = f" (depends on: {', '.join(step.dependencies)})" if step.dependencies else ""
            lines.append(f"## Step {step.step_number}: {step.intent}{deps}")
            lines.append(f"- **Skill**: `{step.skill_id}`")
            lines.append(f"- **Task**: {step.input_query}")
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def plan_to_json(plan: ExecutionPlan) -> dict[str, Any]:
        """Serialize an ExecutionPlan to JSON for programmatic consumption."""
        return plan.to_dict()

    @staticmethod
    def validate_results(plan: ExecutionPlan, results: PlanExecutionResult) -> bool:
        """Validate that execution results cover all plan steps."""
        plan_step_ids = {step.step_id for step in plan.steps}
        result_step_ids = {r.step_id for r in results.results}
        return plan_step_ids == result_step_ids
