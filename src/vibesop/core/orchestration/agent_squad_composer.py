"""AgentSquadComposer — turns semantic intent analysis into an agent squad.

Given an `IntentAnalysis` (roles, facets, per-agent skills, collaboration
protocol), this module produces an `AgentSquad` complete with `AgentRole`
definitions, `SquadStep`s mapped to the best agent platforms, execution order,
and inter-step dependencies.
"""

from __future__ import annotations

import uuid

from vibesop.core.models import AgentRole, AgentSquad, IntentAnalysis, SquadStep, TrustLevel
from vibesop.core.orchestration.agent_capability import RoleToPlatformMapper

# Human-readable metadata and prompt-template keys for supported roles.
ROLE_METADATA: dict[str, dict[str, str]] = {
    "architect": {
        "name": "架构师",
        "description": "负责系统架构设计、技术选型、模块依赖分析",
        "prompt_template": "architect",
    },
    "implementer": {
        "name": "实现者",
        "description": "负责代码实现、重构、功能开发、测试编写",
        "prompt_template": "implementer",
    },
    "reviewer": {
        "name": "审查者",
        "description": "负责代码审查、质量把关、最佳实践检查",
        "prompt_template": "reviewer",
    },
    "tester": {
        "name": "测试者",
        "description": "负责测试策略、测试用例编写、覆盖率分析",
        "prompt_template": "tester",
    },
    "red_team": {
        "name": "红队",
        "description": "负责安全审计、攻击面分析、漏洞挖掘",
        "prompt_template": "red_team",
    },
    "debater": {
        "name": "辩论者",
        "description": "负责提出对立方案、挑战设计决策",
        "prompt_template": "debater",
    },
    "documenter": {
        "name": "文档者",
        "description": "负责文档编写、说明、注释",
        "prompt_template": "documenter",
    },
    "operator": {
        "name": "运维者",
        "description": "负责部署、CI/CD、配置管理",
        "prompt_template": "operator",
    },
    "orchestrator": {
        "name": "协调者",
        "description": "负责汇总多角色输出、生成最终结果",
        "prompt_template": "orchestrator",
    },
}


class AgentSquadComposer:
    """Compose an AgentSquad from a semantic IntentAnalysis.

    The composer performs the following steps:

    1. Normalize the requested roles (e.g. debate protocols get an orchestrator
       judge if one is not already present).
    2. Create an ``AgentRole`` for each role with human-readable metadata and
       required skills.
    3. Map every role to the best available agent platform via
       ``RoleToPlatformMapper``.
    4. Create ``SquadStep`` objects, wiring ``input_from`` dependencies based on
       the selected collaboration protocol.
    5. Return a fully populated ``AgentSquad``.
    """

    def __init__(
        self,
        platform_mapper: RoleToPlatformMapper | None = None,
        available_platforms: list[str] | None = None,
    ) -> None:
        """Initialize the composer.

        Args:
            platform_mapper: Optional custom role-to-platform mapper.
            available_platforms: Optional pool of platforms the composer may
                choose from.  If None, the mapper's full preference list is used.
        """
        self._mapper = platform_mapper or RoleToPlatformMapper()
        self._available_platforms = available_platforms

    def compose(self, analysis: IntentAnalysis) -> AgentSquad:
        """Compose an AgentSquad from a semantic IntentAnalysis."""
        squad_id = f"squad-{uuid.uuid4().hex[:8]}"

        # Normalize roles for the requested protocol.
        role_ids = self._normalize_roles(analysis.suggested_roles, analysis.collaboration_protocol)

        roles: list[AgentRole] = []
        steps: list[SquadStep] = []

        for role_id in role_ids:
            role = self._create_role(role_id, analysis)
            roles.append(role)
            steps.append(self._create_step(role, analysis))

        execution_order = self._build_execution_order(steps, analysis.collaboration_protocol)

        # Wire dependencies (input_from) based on execution order and protocol.
        self._wire_dependencies(steps, execution_order, analysis.collaboration_protocol)

        lead_role = self._select_lead_role(role_ids, analysis.collaboration_protocol)

        return AgentSquad(
            squad_id=squad_id,
            roles=roles,
            steps=steps,
            collaboration_protocol=analysis.collaboration_protocol,
            lead_role=lead_role,
            execution_order=execution_order,
        )

    def _normalize_roles(self, suggested_roles: list[str], protocol: str) -> list[str]:
        """Ensure role list satisfies protocol-specific constraints."""
        roles = list(suggested_roles)

        if protocol == "debate":
            # Debate needs at least two contestants and an orchestrator judge.
            if "orchestrator" not in roles:
                roles.append("orchestrator")
            if len(roles) < 3:
                # If only orchestrator + one debater, add a second debater.
                if "debater" not in roles:
                    roles.insert(0, "debater")
                if len(roles) == 2:
                    roles.insert(0, "debater")

        elif protocol == "review_gate":
            if "reviewer" not in roles:
                roles.append("reviewer")

        elif protocol == "red_team":
            if "red_team" not in roles:
                roles.append("red_team")

        return roles

    def _create_role(self, role_id: str, analysis: IntentAnalysis) -> AgentRole:
        """Create an AgentRole with metadata and required skills."""
        role_meta = ROLE_METADATA.get(role_id, {})
        per_agent_skills = analysis.per_agent_skills.get(role_id, [])
        return AgentRole(
            role_id=role_id,
            name=role_meta.get("name", role_id),
            description=role_meta.get("description", ""),
            required_skills=per_agent_skills,
            system_prompt_template=role_meta.get("prompt_template", "default"),
        )

    def _create_step(self, role: AgentRole, _analysis: IntentAnalysis) -> SquadStep:
        """Create a SquadStep mapped to the best platform for the role."""
        platform = self._mapper.best_platform_for_role(
            role.role_id,
            available_platforms=self._available_platforms,
        )
        return SquadStep(
            step_id=f"{role.role_id}-{uuid.uuid4().hex[:4]}",
            role_id=role.role_id,
            agent_platform=platform,
            skill_ids=list(role.required_skills),
            output_schema={"schema_type": "markdown", "required_sections": ["summary"]},
            trust_level=TrustLevel.NORMAL,
        )

    def _build_execution_order(
        self,
        steps: list[SquadStep],
        protocol: str,
    ) -> list[str]:
        """Return the ordered step IDs for the given protocol."""
        step_ids = [s.step_id for s in steps]

        if protocol == "red_team":
            # Implementer first, then red_team challenge.
            return self._order_by_role(steps, ["implementer", "red_team"])

        if protocol == "review_gate":
            # Implementer first, then reviewer.
            return self._order_by_role(steps, ["implementer", "reviewer"])

        if protocol == "debate":
            # Contestants first, orchestrator (judge) last.
            return self._order_by_role(steps, ["debater"], last=["orchestrator"])

        # sequential / parallel / unknown: preserve suggested role order.
        return step_ids

    def _order_by_role(
        self,
        steps: list[SquadStep],
        first: list[str],
        last: list[str] | None = None,
    ) -> list[str]:
        """Sort step IDs so ``first`` roles come first and ``last`` roles last."""
        last = last or []
        role_to_step: dict[str, SquadStep] = {s.role_id: s for s in steps}

        ordered: list[str] = []
        for role_id in first:
            if role_id in role_to_step:
                ordered.append(role_to_step.pop(role_id).step_id)

        last_ids: list[str] = []
        for role_id in last:
            if role_id in role_to_step:
                last_ids.append(role_to_step.pop(role_id).step_id)

        # Everything else stays in original order.
        remaining = [s.step_id for s in steps if s.step_id not in ordered + last_ids]
        return ordered + remaining + last_ids

    def _wire_dependencies(
        self,
        steps: list[SquadStep],
        execution_order: list[str],
        protocol: str,
    ) -> None:
        """Populate ``input_from`` on steps based on protocol semantics."""
        if protocol in ("parallel",):
            return

        step_by_id = {s.step_id: s for s in steps}
        for idx, step_id in enumerate(execution_order):
            if idx == 0:
                continue
            current = step_by_id[step_id]
            previous_id = execution_order[idx - 1]
            current.input_from.append(previous_id)

    def _select_lead_role(self, role_ids: list[str], protocol: str) -> str:
        """Pick the role that leads/finalizes squad output."""
        if protocol == "debate" and "orchestrator" in role_ids:
            return "orchestrator"
        if "orchestrator" in role_ids:
            return "orchestrator"
        if role_ids:
            return role_ids[-1]
        return "orchestrator"


__all__ = [
    "ROLE_METADATA",
    "AgentSquadComposer",
]
