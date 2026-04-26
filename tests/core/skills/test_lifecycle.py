"""Tests for skill lifecycle management.

Covers: SkillLifecycleManager state transitions, routability, enablement.
"""

from __future__ import annotations

import pytest

from vibesop.core.models import SkillLifecycle
from vibesop.core.skills.lifecycle import SkillLifecycleManager, SkillScope


class TestSkillLifecycleManager:
    """Test SkillLifecycleManager state machine."""

    def test_valid_transitions(self) -> None:
        """All valid transitions should succeed."""
        assert SkillLifecycleManager.can_transition(
            SkillLifecycle.DRAFT, SkillLifecycle.ACTIVE
        )
        assert SkillLifecycleManager.can_transition(
            SkillLifecycle.ACTIVE, SkillLifecycle.DEPRECATED
        )
        assert SkillLifecycleManager.can_transition(
            SkillLifecycle.ACTIVE, SkillLifecycle.ARCHIVED
        )
        assert SkillLifecycleManager.can_transition(
            SkillLifecycle.DEPRECATED, SkillLifecycle.ACTIVE
        )
        assert SkillLifecycleManager.can_transition(
            SkillLifecycle.DEPRECATED, SkillLifecycle.ARCHIVED
        )

    def test_invalid_transitions(self) -> None:
        """Invalid transitions should return False."""
        assert not SkillLifecycleManager.can_transition(
            SkillLifecycle.ACTIVE, SkillLifecycle.DRAFT
        )
        assert not SkillLifecycleManager.can_transition(
            SkillLifecycle.ARCHIVED, SkillLifecycle.ACTIVE
        )
        assert not SkillLifecycleManager.can_transition(
            SkillLifecycle.ARCHIVED, SkillLifecycle.DEPRECATED
        )
        assert not SkillLifecycleManager.can_transition(
            SkillLifecycle.DRAFT, SkillLifecycle.DEPRECATED
        )

    def test_transition_success(self) -> None:
        """Valid transition returns target state."""
        result = SkillLifecycleManager.transition(
            SkillLifecycle.DRAFT, SkillLifecycle.ACTIVE
        )
        assert result == SkillLifecycle.ACTIVE

    def test_transition_failure(self) -> None:
        """Invalid transition raises ValueError."""
        with pytest.raises(ValueError, match="Invalid transition"):
            SkillLifecycleManager.transition(
                SkillLifecycle.ACTIVE, SkillLifecycle.DRAFT
            )

    def test_is_routable(self) -> None:
        """Only ACTIVE skills are routable."""
        assert SkillLifecycleManager.is_routable(SkillLifecycle.ACTIVE)
        assert not SkillLifecycleManager.is_routable(SkillLifecycle.DEPRECATED)
        assert not SkillLifecycleManager.is_routable(SkillLifecycle.DRAFT)
        assert not SkillLifecycleManager.is_routable(SkillLifecycle.ARCHIVED)

    def test_is_enabled_explicit_disabled(self) -> None:
        """Explicitly disabled skill is not enabled."""
        assert not SkillLifecycleManager.is_enabled(
            SkillLifecycle.ACTIVE, explicit_enabled=False
        )

    def test_is_enabled_routable(self) -> None:
        """Routable skill without explicit disable is enabled."""
        assert SkillLifecycleManager.is_enabled(SkillLifecycle.ACTIVE)
        assert not SkillLifecycleManager.is_enabled(SkillLifecycle.DEPRECATED)

    def test_is_enabled_non_routable(self) -> None:
        """Non-routable skill is not enabled."""
        assert not SkillLifecycleManager.is_enabled(SkillLifecycle.DRAFT)
        assert not SkillLifecycleManager.is_enabled(SkillLifecycle.ARCHIVED)


class TestSkillScope:
    """Test SkillScope constants."""

    def test_scope_values(self) -> None:
        assert SkillScope.GLOBAL == "global"
        assert SkillScope.PROJECT == "project"
