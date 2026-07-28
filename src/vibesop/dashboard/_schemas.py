"""Pydantic request models for the dashboard API (Phase B).

These schemas are the **API boundary** — they validate input at the FastAPI
edge before the request reaches the core dataclass layer. The core layer
(``Reflection`` dataclass in ``vibesop.core.observability.reflection``)
keeps its own runtime Literal validation as a defensive backstop.

Why two layers:
- **Pydantic here**: gives clients clear 422 errors with field-level
  details via FastAPI's auto-generated response, no manual try/except.
- **Dataclass in core**: keeps the type guarantees if someone constructs
  a ``Reflection`` directly (CLI, tests, future internal callers) without
  going through HTTP.

Literal types are re-imported from the core module so we have ONE source
of truth for the allowed values — schemas can't drift from the dataclass.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from vibesop.core.observability.reflection import (
    ReflectionKind,
    ReflectionStatus,
    TargetType,
)

__all__ = [
    "ReflectionCreate",
    "ReflectionStatusUpdate",
]


class ReflectionCreate(BaseModel):
    """POST /api/reflections request body.

    Required fields mirror ``Reflection.__init__`` minus the auto-generated
    ones (``id``, ``created_at``) and the API-managed ones (``status``
    defaults to ``"open"`` on creation; use PATCH to change it).
    """

    target_type: TargetType
    target_id: str = Field(..., min_length=1)
    task_id: str = Field(..., min_length=1)
    kind: ReflectionKind
    content: str = Field(..., min_length=1, max_length=500)
    severity: Literal["info", "warn", "critical"] = "info"
    linked_action: dict | None = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "target_type": "task",
                    "target_id": "step:plan-1:s1",
                    "task_id": "T-trace-1",
                    "kind": "trigger_vague",
                    "content": "confidence 0.52 still matched — triggers too loose",
                    "severity": "warn",
                }
            ]
        }
    }


class ReflectionStatusUpdate(BaseModel):
    """PATCH /api/reflections/{id} request body.

    Only ``status`` is mutable via PATCH — content edits are NOT supported
    (reflections are append-only by design; if the user disagrees with a
    reflection, they dismiss it and write a new one).
    """

    status: ReflectionStatus
