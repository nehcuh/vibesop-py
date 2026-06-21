"""SkillComposer — assigns a per-role skill subset from a global skill catalog.

Ensures that each role in an ``AgentSquad`` only sees the skills it is allowed
to use.  Required skills are always included, excluded skills are always
removed, and conflicts over optional skills are resolved using role priority.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from vibesop.core.models import AgentRole, AgentSkillBinding, AgentSquad

# Default number of additional (non-required) skills to assign per role.
_DEFAULT_TOP_K = 3

# Role priority order used for conflict resolution (lower index = higher priority).
# Lead roles such as architect and red_team are preferred over support roles.
_ROLE_PRIORITY: tuple[str, ...] = (
    "orchestrator",
    "architect",
    "red_team",
    "reviewer",
    "implementer",
    "tester",
    "debater",
    "documenter",
    "operator",
)

# Default skill IDs per role. Used by the fast multi-role detection path
# (IntentInterceptor._build_quick_squad_analysis) to populate per_agent_skills
# without consulting the global catalog or an LLM. Keep these aligned with
# the public skill packs that VibeSOP ships or installs by default.
ROLE_DEFAULT_SKILLS: dict[str, list[str]] = {
    "architect": ["system-design", "architect", "design-review"],
    "implementer": ["implement_feature", "refactor", "code-generation"],
    "reviewer": ["code_review", "review", "pr-review"],
    "tester": ["test", "systematic-debugging", "coverage"],
    "red_team": ["security_audit", "vulnerability-scan", "penetration-test"],
    "debater": ["brainstorm", "compare-approaches", "decision-matrix"],
    "documenter": ["document", "readme", "api-doc"],
    "operator": ["deploy", "ci_cd", "release"],
    "orchestrator": ["orchestrate", "plan", "session-end"],
}


def infer_skills_for_role(role_id: str) -> list[str]:
    """Return the default skill ID list for a role (fast path, no LLM).

    Args:
        role_id: One of the keys in :data:`ROLE_DEFAULT_SKILLS`.

    Returns:
        A copy of the default skill list for the role, or an empty list if
        the role is unknown. The caller may freely mutate the result.
    """
    return list(ROLE_DEFAULT_SKILLS.get(role_id, []))


def _role_priority_index(role_id: str) -> int:
    """Return the conflict-resolution priority index for a role."""
    try:
        return _ROLE_PRIORITY.index(role_id)
    except ValueError:
        return len(_ROLE_PRIORITY)


class SkillComposer:
    """Compose per-role skill allowlists for agent squads.

    Rules:
    1. ``required_skills`` (from the role) are always included.
    2. ``excluded_skills`` (from the role) are always removed.
    3. Up to ``top_k`` additional skills are chosen from the global catalog by
       lightweight keyword relevance.
    4. Optional skills claimed by multiple roles are resolved by role priority
       (lead role > architect/red_team > implementer/reviewer > ...).
    5. Required skills are never stripped, even if multiple roles require them.
    """

    def __init__(self, top_k: int = _DEFAULT_TOP_K) -> None:
        self._top_k = max(0, top_k)

    def compose_for_squad(
        self,
        squad: AgentSquad,
        global_skills: list[dict[str, Any]],
    ) -> AgentSquad:
        """Populate ``SquadStep.skill_ids`` for every step in ``squad``."""
        role_by_id = {role.role_id: role for role in squad.roles}
        skill_index = self._index_skills(global_skills)

        # Phase 1: required skills (forced inclusion).
        assignments: dict[str, set[str]] = {}
        for role in squad.roles:
            required = set(role.required_skills)
            excluded = set(role.excluded_skills)
            available = self._filter_skills(skill_index, required, excluded)
            assignments[role.role_id] = available

        # Phase 2: supplement with top-k relevant optional skills.
        already_assigned = set().union(*assignments.values()) if assignments else set()
        for role in squad.roles:
            existing = assignments.get(role.role_id, set())
            excluded = set(role.excluded_skills)
            candidates = [
                skill_id
                for skill_id in skill_index
                if skill_id not in existing
                and skill_id not in excluded
                and skill_id not in already_assigned
            ]
            top_k = self._rank_by_relevance(candidates, role, skill_index, k=self._top_k)
            assignments[role.role_id].update(top_k)
            already_assigned.update(top_k)

        # Phase 3: resolve conflicts among optional skills.
        assignments = self._resolve_conflicts(assignments, role_by_id, squad.lead_role)

        # Phase 4: write assignments back into squad steps.
        for step in squad.steps:
            step.skill_ids = sorted(assignments.get(step.role_id, set()))

        return squad

    def compose_single(
        self,
        query: str,
        router: Any,
    ) -> AgentSkillBinding:
        """Single-agent path: route the query and bind the top skill.

        Args:
            query: User query to route.
            router: A routing object with a ``route(query)`` method.

        Returns:
            AgentSkillBinding for a default single-agent execution.
        """
        route_method = getattr(router, "route", None)
        if route_method is None:
            raise ValueError("router must provide a route() method")

        result = route_method(query)
        primary = getattr(result, "primary", None)
        skill_id = primary.skill_id if primary else "fallback-llm"

        return AgentSkillBinding(
            role_id="default",
            agent_platform="claude-code",
            skill_allowlist=[skill_id],
        )

    def _index_skills(
        self,
        global_skills: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """Index skills by ID and normalize fields used for ranking."""
        index: dict[str, dict[str, Any]] = {}
        for skill in global_skills:
            skill_id = skill.get("id") or skill.get("skill_id")
            if not skill_id:
                continue
            index[skill_id] = skill
        return index

    def _filter_skills(
        self,
        skill_index: dict[str, dict[str, Any]],
        required: set[str],
        excluded: set[str],
    ) -> set[str]:
        """Return required skills that exist and are not excluded."""
        return {
            skill_id
            for skill_id in required
            if skill_id in skill_index and skill_id not in excluded
        }

    def _rank_by_relevance(
        self,
        candidate_ids: list[str],
        role: AgentRole,
        skill_index: dict[str, dict[str, Any]],
        k: int,
    ) -> list[str]:
        """Score optional skills against a role and return the top k."""
        if k <= 0 or not candidate_ids:
            return []

        role_keywords = self._extract_role_keywords(role)
        scored: list[tuple[float, str]] = []
        for skill_id in candidate_ids:
            skill = skill_index.get(skill_id, {})
            score = self._score_skill(skill, role_keywords)
            if score > 0:
                scored.append((score, skill_id))

        scored.sort(reverse=True, key=lambda x: x[0])
        return [skill_id for _, skill_id in scored[:k]]

    def _extract_role_keywords(self, role: AgentRole) -> set[str]:
        """Extract keywords describing a role for matching against skills."""
        keywords: set[str] = set()
        keywords.add(role.role_id)
        keywords.update(role.role_id.replace("_", "-").split("-"))
        keywords.update(role.name.lower().split())
        keywords.update(role.description.lower().split())
        for skill_id in role.required_skills:
            keywords.add(skill_id)
            for sep in ("/", "-", "_"):
                keywords.update(skill_id.lower().split(sep))
        return {kw for kw in keywords if len(kw) > 1}

    def _score_skill(
        self,
        skill: dict[str, Any],
        role_keywords: set[str],
    ) -> float:
        """Score a skill by keyword overlap with role keywords."""

        def _normalize(value: Any) -> str:
            if isinstance(value, list):
                return " ".join(str(v) for v in value)
            return str(value)

        skill_text = " ".join(
            _normalize(skill.get(field, ""))
            for field in (
                "id",
                "skill_id",
                "name",
                "description",
                "intent",
                "tags",
                "capabilities",
                "triggers",
            )
        ).lower()

        tokens: set[str] = set()
        for sep in ("/", "-", "_"):
            skill_text = skill_text.replace(sep, " ")
        tokens.update(skill_text.split())

        matches = role_keywords & tokens
        return float(len(matches))

    def _resolve_conflicts(
        self,
        assignments: dict[str, set[str]],
        role_by_id: dict[str, AgentRole],
        lead_role: str,
    ) -> dict[str, set[str]]:
        """Resolve optional-skill conflicts while preserving required skills."""
        # Determine required skills per role.
        required_by_role: dict[str, set[str]] = {
            role_id: set(role.required_skills) for role_id, role in role_by_id.items()
        }

        # Build skill -> roles map.
        skill_to_roles: dict[str, list[str]] = {}
        for role_id, skills in assignments.items():
            for skill_id in skills:
                skill_to_roles.setdefault(skill_id, []).append(role_id)

        result: dict[str, set[str]] = {role_id: set() for role_id in assignments}

        for skill_id, roles_using in skill_to_roles.items():
            if len(roles_using) <= 1:
                for role_id in roles_using:
                    result[role_id].add(skill_id)
                continue

            # Required skills are never stripped.
            required_users = [
                role_id
                for role_id in roles_using
                if skill_id in required_by_role.get(role_id, set())
            ]
            if required_users:
                # Give to the highest-priority required user.
                winner = min(required_users, key=_role_priority_index)
                result[winner].add(skill_id)
                continue

            # Lead role wins optional conflicts.
            if lead_role and lead_role in roles_using:
                result[lead_role].add(skill_id)
                continue

            # Otherwise, highest-priority role wins.
            winner = min(roles_using, key=_role_priority_index)
            result[winner].add(skill_id)

        return result


class SkillIsolationContext:
    """Isolation context that restricts each role to its assigned skills.

    Used by the router/executor to ensure a squad agent cannot invoke skills
    that belong to another role.
    """

    def __init__(self, squad: AgentSquad) -> None:
        self._squad = squad
        self._per_role: dict[str, set[str]] = {
            step.role_id: set(step.skill_ids) for step in squad.steps
        }

    def get_accessible_skills(self, role_id: str) -> list[str]:
        """Return the skill IDs accessible to ``role_id``."""
        return sorted(self._per_role.get(role_id, set()))

    def to_routing_filter(self, role_id: str) -> Callable[[str], bool]:
        """Return a filter callable: skill_id -> bool (allowed)."""
        allowed = self._per_role.get(role_id, set())
        return lambda skill_id: skill_id in allowed

    def is_allowed(self, role_id: str, skill_id: str) -> bool:
        """Check whether ``role_id`` may use ``skill_id``."""
        return skill_id in self._per_role.get(role_id, set())


__all__ = [
    "ROLE_DEFAULT_SKILLS",
    "SkillComposer",
    "SkillIsolationContext",
    "infer_skills_for_role",
]
