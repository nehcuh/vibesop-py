"""Tests for the Reflection dataclass (v3 Phase A Task 7).

Foundation for the Reflection Store (Task 8/9). A Reflection captures a
human-style annotation against a routing span / skill span / task /
sub-agent / decision node — 7 kinds covering the dashboard's reflection
taxonomy. The dataclass must round-trip losslessly through JSON so the
store can persist + reload without losing fields.

Co-located with the rest of ``vibesop.core.observability`` (tracer /
aggregator / span_writer / models) — matches the existing convention
rather than fragmenting observability code across two top-level packages.
"""

from __future__ import annotations

import pytest

from vibesop.core.observability.reflection import (
    Reflection,
    ReflectionKind,
)


class TestReflectionRoundTrip:
    def test_reflection_round_trip(self) -> None:
        """to_dict → from_dict must reproduce the original Reflection
        exactly (id, created_at, every field)."""
        r = Reflection(
            target_type="route_span",
            target_id="span-abc",
            task_id="task-xyz",
            kind="routing_miss",
            content="should have routed to code-review",
            severity="warn",
        )
        d = r.to_dict()
        r2 = Reflection.from_dict(d)
        assert r2 == r
        assert r2.id == r.id

    def test_round_trip_preserves_created_at(self) -> None:
        """created_at must survive JSON round-trip — datetime → ISO → datetime."""
        r = Reflection(
            target_type="task",
            target_id="t1",
            task_id="task-1",
            kind="positive_pattern",
            content="great flow",
        )
        r2 = Reflection.from_dict(r.to_dict())
        assert r2.created_at == r.created_at
        # tz-aware UTC — not naive
        assert r2.created_at.tzinfo is not None

    def test_round_trip_preserves_linked_action(self) -> None:
        """linked_action (arbitrary dict) must round-trip intact."""
        action = {"type": "promote_instinct", "target": "code-review"}
        r = Reflection(
            target_type="decision_node",
            target_id="d1",
            task_id="task-1",
            kind="positive_pattern",
            content="",
            linked_action=action,
        )
        r2 = Reflection.from_dict(r.to_dict())
        assert r2.linked_action == action

    def test_round_trip_with_linked_action_none(self) -> None:
        """Default linked_action=None must survive round-trip."""
        r = Reflection(
            target_type="subagent",
            target_id="s1",
            task_id="task-1",
            kind="agent_choice",
            content="",
        )
        r2 = Reflection.from_dict(r.to_dict())
        assert r2.linked_action is None


class TestReflectionKindValidation:
    def test_reflection_kind_must_be_valid(self) -> None:
        """Invalid kind must raise (ValidationError or ValueError)."""
        with pytest.raises((ValueError, TypeError)):
            Reflection(
                target_type="x",
                target_id="y",
                task_id="z",
                kind="invalid_kind",  # type: ignore[arg-type]
                content="c",
            )

    def test_all_seven_kinds_accepted(self) -> None:
        """All 7 kinds from ReflectionKind must construct successfully."""
        kinds: list[ReflectionKind] = [
            "routing_miss",
            "skill_misuse",
            "trigger_vague",
            "cost_blow",
            "agent_choice",
            "positive_pattern",
            "context_note",
        ]
        for kind in kinds:
            r = Reflection(
                target_type="task",
                target_id="t",
                task_id="task",
                kind=kind,
                content="",
            )
            assert r.kind == kind

    def test_target_type_must_be_valid(self) -> None:
        """Invalid target_type must raise."""
        with pytest.raises((ValueError, TypeError)):
            Reflection(
                target_type="not_a_real_type",  # type: ignore[arg-type]
                target_id="t",
                task_id="task",
                kind="context_note",
                content="",
            )

    def test_severity_must_be_valid(self) -> None:
        """Invalid severity must raise."""
        with pytest.raises((ValueError, TypeError)):
            Reflection(
                target_type="task",
                target_id="t",
                task_id="task",
                kind="context_note",
                content="",
                severity="panic",  # type: ignore[arg-type]
            )

    def test_status_defaults_to_open(self) -> None:
        """Newly created Reflections start in 'open' status."""
        r = Reflection(
            target_type="task",
            target_id="t",
            task_id="task",
            kind="context_note",
            content="",
        )
        assert r.status == "open"

    def test_status_must_be_valid(self) -> None:
        """Invalid status must raise."""
        with pytest.raises((ValueError, TypeError)):
            Reflection(
                target_type="task",
                target_id="t",
                task_id="task",
                kind="context_note",
                content="",
                status="wontfix",  # type: ignore[arg-type]
            )


class TestReflectionId:
    def test_id_is_unique_per_instance(self) -> None:
        """Each Reflection gets a fresh uuid by default."""
        r1 = Reflection(
            target_type="task",
            target_id="t",
            task_id="task",
            kind="context_note",
            content="",
        )
        r2 = Reflection(
            target_type="task",
            target_id="t",
            task_id="task",
            kind="context_note",
            content="",
        )
        assert r1.id != r2.id

    def test_id_is_hex_string(self) -> None:
        """id is a 32-char hex string (uuid4 .hex)."""
        r = Reflection(
            target_type="task",
            target_id="t",
            task_id="task",
            kind="context_note",
            content="",
        )
        assert isinstance(r.id, str)
        assert len(r.id) == 32
        int(r.id, 16)  # raises if not hex


class TestReflectionExports:
    """Type aliases must be exported for downstream type-checking."""

    def test_kind_status_target_exported(self) -> None:
        """__all__ must export the 3 Literal aliases + the dataclass."""
        from vibesop.core.observability.reflection import __all__

        assert "Reflection" in __all__
        assert "ReflectionKind" in __all__
        assert "ReflectionStatus" in __all__
        assert "TargetType" in __all__
