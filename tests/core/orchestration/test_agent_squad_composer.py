"""Tests for AgentSquadComposer."""

from __future__ import annotations

from vibesop.core.models import IntentAnalysis
from vibesop.core.orchestration.agent_squad_composer import (
    ROLE_METADATA,
    AgentSquadComposer,
)


class TestAgentSquadComposer:
    """Test agent squad composition logic."""

    def test_compose_simple_squad(self) -> None:
        analysis = IntentAnalysis(
            complexity="multi_agent",
            facets=["architecture", "security"],
            squad_needed=True,
            suggested_roles=["architect", "red_team"],
            collaboration_protocol="red_team",
            per_agent_skills={
                "architect": ["system-design"],
                "red_team": ["security_audit"],
            },
            confidence=0.9,
        )

        squad = AgentSquadComposer().compose(analysis)

        assert squad.squad_id.startswith("squad-")
        assert len(squad.roles) == 2
        assert {r.role_id for r in squad.roles} == {"architect", "red_team"}
        assert len(squad.steps) == 2
        assert squad.collaboration_protocol == "red_team"
        assert squad.lead_role in {r.role_id for r in squad.roles}

    def test_roles_get_required_skills(self) -> None:
        analysis = IntentAnalysis(
            complexity="multi_agent",
            facets=["architecture"],
            squad_needed=True,
            suggested_roles=["architect"],
            collaboration_protocol="sequential",
            per_agent_skills={"architect": ["system-design", "design-review"]},
            confidence=0.9,
        )

        squad = AgentSquadComposer().compose(analysis)
        architect = next(r for r in squad.roles if r.role_id == "architect")
        assert "system-design" in architect.required_skills

        step = next(s for s in squad.steps if s.role_id == "architect")
        assert "system-design" in step.skill_ids

    def test_debate_protocol_adds_orchestrator(self) -> None:
        analysis = IntentAnalysis(
            complexity="multi_agent",
            facets=["brainstorm"],
            squad_needed=True,
            suggested_roles=["debater"],
            collaboration_protocol="debate",
            per_agent_skills={"debater": ["brainstorm"]},
            confidence=0.9,
        )

        squad = AgentSquadComposer().compose(analysis)

        role_ids = [r.role_id for r in squad.roles]
        assert "orchestrator" in role_ids
        assert len(role_ids) >= 3
        assert squad.lead_role == "orchestrator"

    def test_review_gate_protocol_adds_reviewer(self) -> None:
        analysis = IntentAnalysis(
            complexity="composite",
            facets=["implement_feature"],
            squad_needed=False,
            suggested_roles=["implementer"],
            collaboration_protocol="review_gate",
            per_agent_skills={"implementer": ["implement_feature"]},
            confidence=0.8,
        )

        squad = AgentSquadComposer().compose(analysis)

        role_ids = [r.role_id for r in squad.roles]
        assert "reviewer" in role_ids
        assert "implementer" in role_ids

    def test_execution_order_for_review_gate(self) -> None:
        analysis = IntentAnalysis(
            complexity="composite",
            facets=["implement_feature"],
            squad_needed=False,
            suggested_roles=["implementer", "reviewer"],
            collaboration_protocol="review_gate",
            per_agent_skills={
                "implementer": ["implement_feature"],
                "reviewer": ["code_review"],
            },
            confidence=0.8,
        )

        squad = AgentSquadComposer().compose(analysis)

        implementer_step = next(s for s in squad.steps if s.role_id == "implementer")
        reviewer_step = next(s for s in squad.steps if s.role_id == "reviewer")
        assert squad.execution_order.index(implementer_step.step_id) < squad.execution_order.index(
            reviewer_step.step_id
        )
        assert reviewer_step.input_from == [implementer_step.step_id]

    def test_platform_mapping_uses_preference(self) -> None:
        analysis = IntentAnalysis(
            complexity="simple",
            facets=["architecture"],
            squad_needed=False,
            suggested_roles=["architect"],
            collaboration_protocol="sequential",
            per_agent_skills={"architect": ["system-design"]},
            confidence=0.9,
        )

        squad = AgentSquadComposer().compose(analysis)
        step = squad.steps[0]
        assert step.agent_platform == "claude-code"

    def test_platform_mapping_respects_available_platforms(self) -> None:
        analysis = IntentAnalysis(
            complexity="simple",
            facets=["architecture"],
            squad_needed=False,
            suggested_roles=["architect"],
            collaboration_protocol="sequential",
            per_agent_skills={"architect": ["system-design"]},
            confidence=0.9,
        )

        composer = AgentSquadComposer(available_platforms=["opencode"])
        squad = composer.compose(analysis)
        step = squad.steps[0]
        assert step.agent_platform == "opencode"

    def test_role_metadata_is_complete(self) -> None:
        required_keys = {"name", "description", "prompt_template"}
        for role_id, meta in ROLE_METADATA.items():
            assert required_keys.issubset(meta.keys()), f"Role {role_id} missing metadata keys"
