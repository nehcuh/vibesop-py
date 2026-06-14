"""Tests for SkillComposer and SkillIsolationContext."""

from __future__ import annotations

from unittest.mock import Mock

from vibesop.core.models import AgentRole, AgentSquad, SquadStep
from vibesop.core.orchestration.skill_composer import (
    SkillComposer,
    SkillIsolationContext,
)


class TestSkillComposer:
    """Test skill assignment logic."""

    def test_required_skills_are_included(self) -> None:
        squad = self._make_squad(
            roles=[
                AgentRole(
                    role_id="architect",
                    name="架构师",
                    description="",
                    required_skills=["system-design"],
                )
            ]
        )
        global_skills = [
            {"id": "system-design", "name": "System Design"},
            {"id": "code-review", "name": "Code Review"},
        ]

        result = SkillComposer().compose_for_squad(squad, global_skills)
        assert "system-design" in result.steps[0].skill_ids

    def test_excluded_skills_are_removed(self) -> None:
        squad = self._make_squad(
            roles=[
                AgentRole(
                    role_id="architect",
                    name="架构师",
                    description="",
                    required_skills=["system-design"],
                    excluded_skills=["code-review"],
                )
            ]
        )
        global_skills = [
            {"id": "system-design", "name": "System Design", "capabilities": ["design"]},
            {"id": "code-review", "name": "Code Review", "capabilities": ["review"]},
        ]

        result = SkillComposer(top_k=1).compose_for_squad(squad, global_skills)
        assert "system-design" in result.steps[0].skill_ids
        assert "code-review" not in result.steps[0].skill_ids

    def test_top_k_supplements_relevant_skills(self) -> None:
        squad = self._make_squad(
            roles=[
                AgentRole(
                    role_id="red_team",
                    name="红队",
                    description="安全审计",
                    required_skills=["security-audit"],
                )
            ]
        )
        global_skills = [
            {"id": "security-audit", "name": "Security Audit", "capabilities": ["security"]},
            {"id": "penetration-test", "name": "Penetration Test", "capabilities": ["security"]},
            {"id": "refactor", "name": "Refactor", "capabilities": ["refactor"]},
        ]

        result = SkillComposer(top_k=1).compose_for_squad(squad, global_skills)
        assert "security-audit" in result.steps[0].skill_ids
        assert "penetration-test" in result.steps[0].skill_ids
        assert "refactor" not in result.steps[0].skill_ids

    def test_conflict_resolution_gives_optional_skill_to_lead_role(self) -> None:
        squad = self._make_squad(
            roles=[
                AgentRole(role_id="architect", name="架构师", description="", required_skills=[]),
                AgentRole(role_id="implementer", name="实现者", description="", required_skills=[]),
            ],
            lead_role="architect",
        )
        global_skills = [
            {
                "id": "shared-skill",
                "name": "Architect Shared Skill",
                "capabilities": ["design", "architecture"],
            },
        ]

        result = SkillComposer(top_k=1).compose_for_squad(squad, global_skills)
        assert "shared-skill" in result.steps[0].skill_ids
        assert "shared-skill" not in result.steps[1].skill_ids

    def test_required_skill_conflict_keeps_for_priority_role(self) -> None:
        squad = self._make_squad(
            roles=[
                AgentRole(
                    role_id="reviewer",
                    name="审查者",
                    description="",
                    required_skills=["code-review"],
                ),
                AgentRole(
                    role_id="red_team",
                    name="红队",
                    description="",
                    required_skills=["code-review"],
                ),
            ]
        )
        global_skills = [{"id": "code-review", "name": "Code Review"}]

        result = SkillComposer().compose_for_squad(squad, global_skills)
        # red_team has higher priority than reviewer, so it wins the required conflict.
        assert "code-review" in result.steps[1].skill_ids

    def test_compose_single_binds_top_skill(self) -> None:
        mock_router = Mock()
        mock_router.route.return_value = Mock(primary=Mock(skill_id="gstack/debug"))

        binding = SkillComposer().compose_single("debug this error", mock_router)
        assert binding.role_id == "default"
        assert binding.skill_allowlist == ["gstack/debug"]

    def test_isolation_context_filters_by_role(self) -> None:
        squad = self._make_squad(
            roles=[
                AgentRole(
                    role_id="architect", name="架构师", description="", required_skills=["design"]
                ),
                AgentRole(
                    role_id="implementer", name="实现者", description="", required_skills=["coding"]
                ),
            ]
        )
        global_skills = [
            {"id": "design", "name": "Design"},
            {"id": "coding", "name": "Coding"},
        ]
        squad = SkillComposer().compose_for_squad(squad, global_skills)

        ctx = SkillIsolationContext(squad)
        assert ctx.is_allowed("architect", "design")
        assert not ctx.is_allowed("architect", "coding")
        assert ctx.to_routing_filter("implementer")("coding")
        assert not ctx.to_routing_filter("implementer")("design")

    def _make_squad(
        self,
        roles: list[AgentRole],
        lead_role: str = "",
        protocol: str = "sequential",
    ) -> AgentSquad:
        steps = [
            SquadStep(
                step_id=f"{role.role_id}-step",
                role_id=role.role_id,
                agent_platform="claude-code",
                skill_ids=[],
            )
            for role in roles
        ]
        return AgentSquad(
            squad_id="squad-test",
            roles=roles,
            steps=steps,
            collaboration_protocol=protocol,
            lead_role=lead_role or roles[-1].role_id,
            execution_order=[s.step_id for s in steps],
        )
