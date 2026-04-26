"""Skill lifecycle management.

Manages skill states: DRAFT → ACTIVE → DEPRECATED → ARCHIVED.
Provides enable/disable and scope (project vs global) controls.
"""

from __future__ import annotations

from vibesop.core.models import SkillLifecycle

# Re-export for backward compatibility
__all__ = ["SkillLifecycle", "SkillLifecycleManager", "SkillScope"]


class SkillScope:
    """Scope of a skill's availability."""

    GLOBAL = "global"  # Available across all projects
    PROJECT = "project"  # Only available in specific project


class SkillLifecycleManager:
    """Manages lifecycle state transitions for skills.

    Valid transitions:
        DRAFT → ACTIVE
        ACTIVE → DEPRECATED
        ACTIVE → ARCHIVED
        DEPRECATED → ACTIVE
        DEPRECATED → ARCHIVED
    """

    @classmethod
    def _valid_transitions(cls) -> dict[SkillLifecycle, frozenset[SkillLifecycle]]:
        return {
            SkillLifecycle.DRAFT: frozenset({SkillLifecycle.ACTIVE}),
            SkillLifecycle.ACTIVE: frozenset({SkillLifecycle.DEPRECATED, SkillLifecycle.ARCHIVED}),
            SkillLifecycle.DEPRECATED: frozenset({SkillLifecycle.ACTIVE, SkillLifecycle.ARCHIVED}),
            SkillLifecycle.ARCHIVED: frozenset(),  # Terminal state
        }

    @classmethod
    def can_transition(
        cls,
        from_state: SkillLifecycle,
        to_state: SkillLifecycle,
    ) -> bool:
        """Check if a lifecycle transition is valid."""
        return to_state in cls._valid_transitions().get(from_state, frozenset())

    @classmethod
    def transition(
        cls,
        current: SkillLifecycle,
        target: SkillLifecycle,
    ) -> SkillLifecycle:
        """Perform a lifecycle transition.

        Args:
            current: Current lifecycle state
            target: Desired target state

        Returns:
            The new state (same as target if valid)

        Raises:
            ValueError: If transition is invalid
        """
        if not cls.can_transition(current, target):
            msg = f"Invalid transition: {current.value} → {target.value}"
            raise ValueError(msg)
        return target

    @classmethod
    def is_routable(cls, state: SkillLifecycle) -> bool:
        """Check if a skill in this state can be routed to.

        Only ACTIVE skills are routable.
        DEPRECATED and ARCHIVED skills are excluded from routing.
        """
        return state == SkillLifecycle.ACTIVE

    @classmethod
    def is_enabled(cls, state: SkillLifecycle, explicit_enabled: bool | None = None) -> bool:
        """Check if a skill is effectively enabled.

        A skill is enabled if:
        1. Its lifecycle state is routable, AND
        2. It is not explicitly disabled
        """
        if explicit_enabled is False:
            return False
        return cls.is_routable(state)
