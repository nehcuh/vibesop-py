"""Tests for CollaborationProtocol."""

from __future__ import annotations

import json
from unittest.mock import Mock

from vibesop.core.models import AgentRole, AgentSquad, SquadStep
from vibesop.core.orchestration.collaboration_protocol import (
    DebateProtocol,
    HandoffPayload,
    OutputSchema,
    ReviewGateProtocol,
    ReviewVerdict,
    SequentialProtocol,
    create_protocol,
)


class TestCollaborationProtocol:
    """Test collaboration primitives and protocols."""

    def test_handoff_payload_creation(self) -> None:
        payload = HandoffPayload(
            from_role="architect",
            to_role="implementer",
            step_id="step-1",
            output="design doc",
        )
        assert payload.from_role == "architect"
        assert payload.to_role == "implementer"
        assert payload.confidence == 1.0

    def test_output_schema_render(self) -> None:
        schema = OutputSchema(
            schema_type="markdown",
            required_sections=["summary", "details"],
            example="## Summary\n...",
        )
        rendered = schema.render()
        assert "markdown" in rendered
        assert "summary" in rendered
        assert "Example:" in rendered

    def test_sequential_protocol_handoff(self) -> None:
        squad = self._minimal_squad("sequential")
        protocol = SequentialProtocol(squad)
        payload = HandoffPayload(
            from_role="architect",
            to_role="implementer",
            step_id="s1",
            output="architecture design",
        )
        result = protocol.handoff(payload)
        assert "architecture design" in result.output
        assert "implementer" in result.output

    def test_sequential_protocol_review_trivially_passes(self) -> None:
        squad = self._minimal_squad("sequential")
        protocol = SequentialProtocol(squad)
        verdict = protocol.review("implementer", [{"role": "implementer", "content": "code"}])
        assert verdict.passed is True
        assert verdict.score == 10.0

    def test_review_gate_protocol_handoff(self) -> None:
        squad = self._minimal_squad("review_gate", roles=["implementer", "reviewer"])
        protocol = ReviewGateProtocol(squad)
        payload = HandoffPayload(
            from_role="implementer",
            to_role="reviewer",
            step_id="s1",
            output="implemented feature",
        )
        result = protocol.handoff(payload)
        assert "implemented feature" in result.output
        assert "review" in result.output.lower()

    def test_review_gate_protocol_llm_review(self) -> None:
        mock_llm = Mock()
        mock_llm.call.return_value = Mock(
            content=json.dumps(
                {
                    "passed": False,
                    "issues": ["missing tests"],
                    "score": 6.0,
                    "requires_revision": True,
                    "revision_feedback": "Add unit tests.",
                }
            )
        )

        squad = self._minimal_squad("review_gate", roles=["implementer", "reviewer"])
        protocol = ReviewGateProtocol(squad, llm_client=mock_llm)
        verdict = protocol.review(
            "implementer",
            [{"role": "implementer", "content": "def foo(): pass"}],
        )

        assert verdict.passed is False
        assert verdict.requires_revision is True
        assert "missing tests" in verdict.issues
        assert mock_llm.call.called

    def test_review_gate_protocol_bypasses_without_llm(self) -> None:
        squad = self._minimal_squad("review_gate", roles=["implementer", "reviewer"])
        protocol = ReviewGateProtocol(squad, llm_client=None)
        verdict = protocol.review(
            "implementer",
            [{"role": "implementer", "content": "def foo(): pass"}],
        )
        assert verdict.passed is True
        assert "No LLM configured" in verdict.issues[0]

    def test_should_continue_stops_at_max_rounds(self) -> None:
        squad = self._minimal_squad("review_gate")
        protocol = ReviewGateProtocol(squad)
        verdict = ReviewVerdict(
            passed=False,
            reviewer_role="reviewer",
            target_role="implementer",
            issues=["fix me"],
        )
        assert protocol.should_continue(3, 3, [verdict]) is False

    def test_should_continue_stops_when_all_pass(self) -> None:
        squad = self._minimal_squad("review_gate")
        protocol = ReviewGateProtocol(squad)
        verdict = ReviewVerdict(
            passed=True,
            reviewer_role="reviewer",
            target_role="implementer",
            issues=[],
        )
        assert protocol.should_continue(1, 3, [verdict]) is False

    def test_debate_protocol_handoff(self) -> None:
        squad = self._minimal_squad("debate", roles=["debater", "debater", "orchestrator"])
        protocol = DebateProtocol(squad)
        payload = HandoffPayload(
            from_role="debater",
            to_role="orchestrator",
            step_id="s1",
            output="argument A",
        )
        result = protocol.handoff(payload)
        assert "argument A" in result.output
        assert "orchestrator" in result.output

    def test_create_protocol_factory(self) -> None:
        squad = self._minimal_squad("sequential")
        protocol = create_protocol(squad)
        assert isinstance(protocol, SequentialProtocol)

        squad = self._minimal_squad("review_gate")
        protocol = create_protocol(squad)
        assert isinstance(protocol, ReviewGateProtocol)

        squad = self._minimal_squad("debate")
        protocol = create_protocol(squad)
        assert isinstance(protocol, DebateProtocol)

    def _minimal_squad(
        self,
        protocol: str,
        roles: list[str] | None = None,
    ) -> AgentSquad:
        roles = roles or ["architect", "implementer"]
        squad_roles = [
            AgentRole(role_id=r, name=r, description="", required_skills=[]) for r in roles
        ]
        steps = [
            SquadStep(
                step_id=f"{r}-step",
                role_id=r,
                agent_platform="claude-code",
                skill_ids=[],
            )
            for r in roles
        ]
        return AgentSquad(
            squad_id="squad-test",
            roles=squad_roles,
            steps=steps,
            collaboration_protocol=protocol,
            lead_role=roles[-1],
            execution_order=[s.step_id for s in steps],
        )
