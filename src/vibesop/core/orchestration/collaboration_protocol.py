"""CollaborationProtocol — primitives for multi-agent collaboration.

Provides standard payloads, output schemas, and protocol implementations that
govern how agents in a squad hand off outputs, review each other's work, and
converge on a final result.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from vibesop.core.exceptions import LLMError
from vibesop.core.models import AgentSquad, SquadStep

if TYPE_CHECKING:
    from vibesop.llm.base import LLMProvider


class HandoffPayload(BaseModel):
    """Payload passed between agents during a handoff."""

    model_config = {"arbitrary_types_allowed": True}

    from_role: str
    to_role: str
    step_id: str
    output: str
    output_schema: dict[str, Any] = {}
    artifacts: list[str] = []
    confidence: float = 1.0
    metadata: dict[str, Any] = {}


class ReviewVerdict(BaseModel):
    """Verdict produced by a reviewer/red-team agent."""

    model_config = {"arbitrary_types_allowed": True}

    passed: bool
    reviewer_role: str
    target_role: str
    issues: list[str]
    score: float = 0.0
    requires_revision: bool = False
    revision_feedback: str = ""


class OutputSchema(BaseModel):
    """Expected structured output schema for a squad step."""

    model_config = {"arbitrary_types_allowed": True}

    schema_type: str = "markdown"  # "markdown" | "json" | "hybrid"
    required_sections: list[str] = []
    example: str = ""

    def render(self) -> str:
        """Render the schema as a prompt instruction."""
        sections = "\n".join(f"- {s}" for s in self.required_sections)
        example_block = f"\nExample:\n{self.example}" if self.example else ""
        return f"Output format: {self.schema_type}\nRequired sections:\n{sections}{example_block}"


class CollaborationProtocol(ABC):
    """Base class for multi-agent collaboration protocols."""

    def __init__(self, squad: AgentSquad, llm_client: LLMProvider | None = None) -> None:
        self._squad = squad
        self._llm = llm_client

    @abstractmethod
    def handoff(self, payload: HandoffPayload) -> HandoffPayload:
        """Transform and forward a handoff payload to the next agent."""
        ...

    @abstractmethod
    def review(self, target_role: str, outputs: list[dict[str, Any]]) -> ReviewVerdict:
        """Review outputs produced by ``target_role``."""
        ...

    def should_continue(
        self,
        round_number: int,
        max_rounds: int,
        verdicts: list[ReviewVerdict],
    ) -> bool:
        """Return True if the protocol should run another round.

        Stops when max rounds are reached or when every verdict has passed.
        """
        if round_number >= max_rounds:
            return False
        return not (verdicts and all(v.passed for v in verdicts))

    def _step_for_role(self, role_id: str) -> SquadStep | None:
        """Find the squad step owned by ``role_id``."""
        for step in self._squad.steps:
            if step.role_id == role_id:
                return step
        return None


class SequentialProtocol(CollaborationProtocol):
    """Sequential execution: A → B → C, each step receives the previous output."""

    def handoff(self, payload: HandoffPayload) -> HandoffPayload:
        """Wrap upstream output in a clear markdown block."""
        payload.output = (
            f"# Previous output from {payload.from_role}\n\n"
            f"{payload.output}\n\n"
            f"---\n\n"
            f"Your role is **{payload.to_role}**. Continue from the above context."
        )
        return payload

    def review(self, target_role: str, outputs: list[dict[str, Any]]) -> ReviewVerdict:
        """Sequential protocols do not gate execution; return a trivial pass."""
        _ = outputs
        return ReviewVerdict(
            passed=True,
            reviewer_role="system",
            target_role=target_role,
            issues=[],
            score=10.0,
        )


class ParallelProtocol(CollaborationProtocol):
    """Parallel execution: independent agents run concurrently."""

    def handoff(self, payload: HandoffPayload) -> HandoffPayload:
        """Parallel agents receive only their own task context."""
        payload.output = (
            f"You are running in parallel as **{payload.to_role}**. "
            "Focus on your assigned task. Results will be synthesized later."
        )
        return payload

    def review(self, target_role: str, outputs: list[dict[str, Any]]) -> ReviewVerdict:
        _ = outputs
        return ReviewVerdict(
            passed=True,
            reviewer_role="system",
            target_role=target_role,
            issues=[],
            score=10.0,
        )


class ReviewGateProtocol(CollaborationProtocol):
    """Implement → Review → loop until the review passes or max rounds hit."""

    def handoff(self, payload: HandoffPayload) -> HandoffPayload:
        """Forward implementation output to the reviewer with context."""
        payload.output = (
            f"# Implementation by {payload.from_role}\n\n"
            f"{payload.output}\n\n"
            f"---\n\n"
            f"Your role is **{payload.to_role}**. Review the implementation above."
        )
        return payload

    def review(self, target_role: str, outputs: list[dict[str, Any]]) -> ReviewVerdict:
        """Review the target role's output, optionally using an LLM."""
        reviewer_role = self._find_reviewer_role()
        combined_output = "\n\n---\n\n".join(
            f"Output from {o.get('role', 'unknown')}:\n{o.get('content', '')}" for o in outputs
        )

        if self._llm is None:
            return ReviewVerdict(
                passed=True,
                reviewer_role=reviewer_role or "reviewer",
                target_role=target_role,
                issues=["No LLM configured; review gate bypassed."],
                score=10.0,
            )

        prompt = self._build_review_prompt(target_role, combined_output)
        try:
            response = self._llm.call(prompt, max_tokens=400, temperature=0.0)
            content = getattr(response, "content", str(response))
            return self._parse_review_response(reviewer_role or "reviewer", target_role, content)
        except Exception as e:
            raise LLMError(getattr(self._llm, "provider_name", "unknown"), str(e)) from e

    def _find_reviewer_role(self) -> str | None:
        for step in self._squad.steps:
            if step.role_id == "reviewer":
                return step.role_id
        return None

    def _build_review_prompt(self, target_role: str, output_text: str) -> str:
        return (
            "You are a strict code/design reviewer. Review the following output and respond "
            "ONLY with a JSON object in the exact format below.\n\n"
            "Review dimensions: correctness, security, maintainability, performance.\n\n"
            "Output format:\n"
            "{\n"
            '  "passed": true|false,\n'
            '  "issues": ["issue 1", "issue 2"],\n'
            '  "score": 0.0-10.0,\n'
            '  "requires_revision": true|false,\n'
            '  "revision_feedback": "concise revision instructions"\n'
            "}\n\n"
            f"Target role: {target_role}\n\n"
            f"{output_text}\n"
        )

    def _parse_review_response(
        self,
        reviewer_role: str,
        target_role: str,
        content: str,
    ) -> ReviewVerdict:
        import re

        code_match = re.search(r"```(?:json)?\s*(\{.*?})\s*```", content, re.DOTALL)
        json_str = code_match.group(1) if code_match else content

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            # Tolerant fallback: assume failure if JSON is malformed.
            return ReviewVerdict(
                passed=False,
                reviewer_role=reviewer_role,
                target_role=target_role,
                issues=["Review response could not be parsed as JSON."],
                score=0.0,
                requires_revision=True,
                revision_feedback="Please re-run the review step.",
            )

        issues = list(data.get("issues", []))
        passed = bool(data.get("passed", False))
        requires_revision = bool(data.get("requires_revision", not passed))
        score = float(data.get("score", 0.0))

        return ReviewVerdict(
            passed=passed,
            reviewer_role=reviewer_role,
            target_role=target_role,
            issues=issues,
            score=score,
            requires_revision=requires_revision,
            revision_feedback=str(data.get("revision_feedback", "")),
        )


class DebateProtocol(CollaborationProtocol):
    """Debate protocol: contestants argue, orchestrator judges."""

    def handoff(self, payload: HandoffPayload) -> HandoffPayload:
        """Forward one contestant's argument to the next participant."""
        payload.output = (
            f"# Argument from {payload.from_role}\n\n"
            f"{payload.output}\n\n"
            f"---\n\n"
            f"Your role is **{payload.to_role}**. Respond to the argument above."
        )
        return payload

    def review(self, target_role: str, outputs: list[dict[str, Any]]) -> ReviewVerdict:
        """In debate mode, the orchestrator judges all contestant outputs."""
        judge_role = self._squad.lead_role or "orchestrator"
        if self._llm is None:
            return ReviewVerdict(
                passed=True,
                reviewer_role=judge_role,
                target_role=target_role,
                issues=[],
                score=10.0,
            )

        combined_output = "\n\n---\n\n".join(
            f"{o.get('role', 'unknown')}:\n{o.get('content', '')}" for o in outputs
        )
        prompt = (
            "You are the debate judge. Compare the arguments below and decide which is stronger. "
            "Respond ONLY with JSON:\n"
            "{\n"
            '  "passed": true,\n'
            '  "issues": ["why the losing argument is weaker"],\n'
            '  "score": 0.0-10.0,\n'
            '  "requires_revision": false,\n'
            '  "revision_feedback": "which approach won and why"\n'
            "}\n\n"
            f"{combined_output}\n"
        )
        try:
            response = self._llm.call(prompt, max_tokens=400, temperature=0.0)
            content = getattr(response, "content", str(response))
            return self._parse_debate_verdict(judge_role, target_role, content)
        except Exception as e:
            raise LLMError(getattr(self._llm, "provider_name", "unknown"), str(e)) from e

    def _parse_debate_verdict(
        self,
        judge_role: str,
        target_role: str,
        content: str,
    ) -> ReviewVerdict:
        import re

        code_match = re.search(r"```(?:json)?\s*(\{.*?})\s*```", content, re.DOTALL)
        json_str = code_match.group(1) if code_match else content

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return ReviewVerdict(
                passed=True,
                reviewer_role=judge_role,
                target_role=target_role,
                issues=["Judge response could not be parsed as JSON."],
                score=5.0,
                requires_revision=False,
                revision_feedback="",
            )

        return ReviewVerdict(
            passed=bool(data.get("passed", True)),
            reviewer_role=judge_role,
            target_role=target_role,
            issues=list(data.get("issues", [])),
            score=float(data.get("score", 5.0)),
            requires_revision=bool(data.get("requires_revision", False)),
            revision_feedback=str(data.get("revision_feedback", "")),
        )


def create_protocol(
    squad: AgentSquad,
    llm_client: LLMProvider | None = None,
) -> CollaborationProtocol:
    """Factory that returns the correct protocol implementation for a squad."""
    protocol_map: dict[str, type[CollaborationProtocol]] = {
        "sequential": SequentialProtocol,
        "parallel": ParallelProtocol,
        "review_gate": ReviewGateProtocol,
        "red_team": ReviewGateProtocol,
        "debate": DebateProtocol,
    }
    protocol_cls = protocol_map.get(squad.collaboration_protocol, SequentialProtocol)
    return protocol_cls(squad, llm_client)


__all__ = [
    "AgentSquad",
    "CollaborationProtocol",
    "DebateProtocol",
    "HandoffPayload",
    "OutputSchema",
    "ParallelProtocol",
    "ReviewGateProtocol",
    "ReviewVerdict",
    "SequentialProtocol",
    "SquadStep",
    "create_protocol",
]
