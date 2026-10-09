"""Agent Execution Protocol — standard interface for AI Agents to execute plans.

Defines the contract between VibeSOP (plan producer) and AI Agents
(plan consumers). Agents implement this protocol to receive and report
multi-step execution plans.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from vibesop.core.models import ExecutionPlan

if TYPE_CHECKING:
    from vibesop.agent.step_runner import StepOutcome


class StepResultStatus(StrEnum):
    """Status of a single step execution."""

    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"
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
    review_status: str = "not_required"

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.results if r.status == StepResultStatus.SUCCESS)

    @property
    def all_succeeded(self) -> bool:
        """Execution success ONLY — every step ran to a success outcome.

        This says nothing about review acceptance: a squad run whose required
        review gate errored can report all_succeeded=True while
        ``review_status`` is "error" (acceptance unknown). Consumers gating on
        acceptance must check ``review_status`` (accepted / rejected / error /
        not_required), never infer it from this property.
        """
        return all(r.status == StepResultStatus.SUCCESS for r in self.results)

    @classmethod
    def from_step_runner_dict(
        cls,
        result: dict[str, Any],
        plan: ExecutionPlan | None = None,
        step_outcomes: list[StepOutcome] | None = None,
    ) -> PlanExecutionResult:
        """Thin adapter: normalize a StepRunner.execute_all() legacy dict into
        the public PlanExecutionResult/StepResult face (B3).

        One vocabulary, no third result model: per-step ``status`` values map
        1:1 onto StepResultStatus, and both legacy result shapes are accepted —
        the static/squad per-step entry lists (``{"step_id", "status", ...}``)
        and the dynamic lane's dict keyed by step identity (values classified
        with the shared acceptance predicate; the legacy dict shape itself is
        never rewritten). Blocked steps carry the legacy "failed" entry status
        (F2 value-domain contract). The additive ``review_status`` key passes
        through to :attr:`PlanExecutionResult.review_status`. ``plan`` is
        optional and only used to backfill ``skill_id`` for entries that lack
        it.

        Post-corrective (P1): when ``step_outcomes`` — the producer's shared
        per-step ``StepOutcome`` list (``runner.last_plan_outcome.steps``) —
        is supplied, per-step statuses are taken from it verbatim as the
        single source of truth. No second classification predicate runs, so
        the adapter cannot disagree with the runner's own verdict: ordinary
        hard-reject feedback text (no ``blocked:`` prefix) and dict sentinels
        (``{"status": "blocked"}``) classify exactly as the producer did.

        P1 corrective: the producer stamps every per-step entry it emits with
        the additive ``outcome_status`` key — the shared ``StepOutcomeStatus``
        verdict serialized as its enum value string (``"success"`` /
        ``"failed"`` / ``"blocked"`` / ``"skipped"``). The adapter reads this
        fact by DEFAULT (it survives a JSON round trip of the plain dict), so
        the ordinary two-argument call classifies exactly as the producer did.
        Legacy payloads written before this key existed (no ``outcome_status``
        on the entry) keep the full fallback semantics below — nothing about
        old serialized results changes.

        Fallback order when neither the additive entry key nor
        ``step_outcomes`` is available: recover blocked granularity from the
        payload with the shared blocked predicate
        (:func:`vibesop.agent.step_runner._is_blocked_output`): a blocked
        sentinel in the recorded error text or the preserved raw output of a
        "failed" entry, or a blocked sentinel value in the dynamic dict lane.
        Ordinary (non-sentinel) hard-reject feedback text stays FAILED on
        that path — producers that predate the additive key cannot be
        distinguished from real failures dict-only, which is why the producer
        now stamps ``outcome_status``.
        """
        from vibesop.agent.step_runner import _is_blocked_output
        from vibesop.core.orchestration.verification_loop import is_acceptance_failure

        skill_by_step = {s.step_id: s.skill_id for s in plan.steps} if plan is not None else {}

        # Preferred source of truth (P1): the producer's shared per-step
        # outcomes, mapped 1:1 onto StepResultStatus by value.
        outcome_status_by_step: dict[str, StepResultStatus] = {}
        if step_outcomes:
            for outcome in step_outcomes:
                outcome_status_by_step[str(outcome.step_id)] = StepResultStatus(str(outcome.status))

        def _status(
            value: Any,
            legacy: str | None,
            error: Any = None,
            step_id: str | None = None,
        ) -> StepResultStatus:
            if step_id is not None:
                shared = outcome_status_by_step.get(step_id)
                if shared is not None:
                    return shared
            if legacy == "completed":
                return StepResultStatus.SUCCESS
            if legacy == "skipped":
                return StepResultStatus.SKIPPED
            if legacy == "blocked":
                return StepResultStatus.BLOCKED
            if legacy == "failed":
                # F2: the legacy entry status value domain is completed/failed
                # — a blocked step is persisted as "failed". On the fallback
                # path the blocked granularity is recovered from the recorded
                # error text or the preserved raw output with the shared
                # blocked predicate; ordinary feedback text stays FAILED
                # (use step_outcomes for those).
                if _is_blocked_output(error) or _is_blocked_output(value):
                    return StepResultStatus.BLOCKED
                return StepResultStatus.FAILED
            if is_acceptance_failure(value):
                return (
                    StepResultStatus.BLOCKED
                    if _is_blocked_output(value)
                    else StepResultStatus.FAILED
                )
            return StepResultStatus.SUCCESS

        steps: list[StepResult] = []
        raw_results = result.get("results") or {}
        if isinstance(raw_results, list):
            for entry in raw_results:
                if not isinstance(entry, dict) or "step_id" not in entry:
                    continue
                # P1 corrective: the producer's additive per-step fact is the
                # default source of truth — it rides inside the plain dict and
                # survives a JSON transport. An absent or unrecognized value
                # means a legacy payload: fall through to step_outcomes, then
                # to the legacy classification predicate.
                status: StepResultStatus | None = None
                additive = entry.get("outcome_status")
                if isinstance(additive, str):
                    try:
                        status = StepResultStatus(additive.strip().lower())
                    except ValueError:
                        status = None
                if status is None:
                    status = _status(
                        entry.get("output"),
                        entry.get("status"),
                        entry.get("error"),
                        step_id=str(entry["step_id"]),
                    )
                steps.append(
                    StepResult(
                        step_id=str(entry["step_id"]),
                        skill_id=str(
                            entry.get("skill_id") or skill_by_step.get(entry["step_id"], "")
                        ),
                        status=status,
                        output="" if entry.get("output") is None else str(entry.get("output")),
                        error=entry.get("error"),
                    )
                )
        else:
            for step_id, value in raw_results.items():
                steps.append(
                    StepResult(
                        step_id=str(step_id),
                        skill_id=str(skill_by_step.get(step_id, "")),
                        status=_status(value, None, step_id=str(step_id)),
                        output="" if value is None else str(value),
                    )
                )
        review_status = str(result.get("review_status") or "not_required")
        return cls(
            plan_id=str(result.get("plan_id", "")), results=steps, review_status=review_status
        )


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
