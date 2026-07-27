"""Reflection dataclass — human-style annotation against routing / skill / task spans.

A Reflection captures a learning note the user (or the system) wants to
attach to a specific observability target:

- ``route_span``     — a routing decision (skill match / fallback)
- ``skill_span``     — a skill execution
- ``task``           — an entire task
- ``subagent``       — a sub-agent execution
- ``decision_node``  — a workflow graph fork (e.g. classifier pattern choice)

7 reflection kinds cover the dashboard v3 taxonomy:

- ``routing_miss``      — should have routed elsewhere
- ``skill_misuse``      — wrong skill invocation pattern
- ``trigger_vague``     — query was too vague to route cleanly
- ``cost_blow``         — spent too many tokens / tool calls
- ``agent_choice``      — wrong sub-agent assigned
- ``positive_pattern``  — something worked well (promote to instinct)
- ``context_note``      — generic annotation

Status lifecycle: ``open`` → ``addressed`` | ``dismissed`` (Task 8/9 store
handles transitions; here we only define the literals + JSON round-trip).

Round-trip contract: ``Reflection.from_dict(r.to_dict()) == r`` for any
Reflection, including ``created_at`` (ISO 8601 with tz) and ``linked_action``
(arbitrary dict or None).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, get_args

__all__ = [
    "Reflection",
    "ReflectionKind",
    "ReflectionStatus",
    "TargetType",
]


ReflectionKind = Literal[
    "routing_miss",
    "skill_misuse",
    "trigger_vague",
    "cost_blow",
    "agent_choice",
    "positive_pattern",
    "context_note",
]

ReflectionStatus = Literal["open", "addressed", "dismissed"]

TargetType = Literal["route_span", "skill_span", "task", "subagent", "decision_node"]

_VALID_KINDS: frozenset[str] = frozenset(get_args(ReflectionKind))
_VALID_STATUS: frozenset[str] = frozenset(get_args(ReflectionStatus))
_VALID_TARGET_TYPES: frozenset[str] = frozenset(get_args(TargetType))
_VALID_SEVERITY: frozenset[str] = frozenset({"info", "warn", "critical"})


def _validate_choice(value: str, valid: frozenset[str], field_name: str) -> str:
    """Runtime-validate a Literal field — keeps the dataclass a normal
    dataclass (no Pydantic dependency) while still rejecting bad values
    at construction time."""
    if value not in valid:
        msg = f"{field_name}={value!r} is not one of {sorted(valid)}"
        raise ValueError(msg)
    return value


@dataclass
class Reflection:
    """A single reflection annotation.

    Identity: ``id`` (uuid4 hex). Equality includes every field, so two
    Reflections with the same id but different content are NOT equal —
    round-trip identity requires every field to match.
    """

    target_type: TargetType
    target_id: str
    task_id: str
    kind: ReflectionKind
    content: str
    severity: Literal["info", "warn", "critical"] = "info"
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    status: ReflectionStatus = "open"
    linked_action: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        # Runtime-validate the Literal fields. dataclass + Literal alone
        # does not enforce at runtime — without this, Reflection(target_type="x",
        # ..., kind="invalid_kind", ...) would silently construct an invalid
        # object that only fails when serialized.
        _validate_choice(self.target_type, _VALID_TARGET_TYPES, "target_type")
        _validate_choice(self.kind, _VALID_KINDS, "kind")
        _validate_choice(self.severity, _VALID_SEVERITY, "severity")
        _validate_choice(self.status, _VALID_STATUS, "status")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict.

        ``created_at`` becomes ISO 8601 with tz offset; ``linked_action``
        passes through unchanged (caller is responsible for JSON-safety of
        nested values — same contract as ``Span.metadata``).
        """
        return {
            "target_type": self.target_type,
            "target_id": self.target_id,
            "task_id": self.task_id,
            "kind": self.kind,
            "content": self.content,
            "severity": self.severity,
            "id": self.id,
            "created_at": self.created_at.isoformat(),
            "status": self.status,
            "linked_action": self.linked_action,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Reflection:
        """Deserialize from ``to_dict`` output.

        Re-parses ``created_at`` (ISO 8601 → aware datetime). Other
        Literal fields are validated again on construction (defensive —
        a hand-edited JSON file could carry an invalid kind).
        """
        payload = dict(d)
        raw_created = payload.get("created_at")
        if isinstance(raw_created, str):
            payload["created_at"] = datetime.fromisoformat(raw_created)
        return cls(**payload)
