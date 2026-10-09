"""Shared span-record payload helpers (reader-side tolerance).

``SpanWriter`` serialises ``metadata`` (and ``input_data`` / ``output_data``)
to JSON-encoded strings on disk (span_writer.py:116-133), while in-memory
``Span.to_dict()`` records carry dicts. Every disk reader must tolerate both
shapes. Several modules already re-implement this decode locally
(``skill_health.py:78-83``, ``skill_consumption.py:180``,
``route_observe.py:217``, ``aggregator.py:368-378``); this module is the
shared copy for consumers going forward (D12/B7: recall + dashboard).
"""

from __future__ import annotations

import json
from typing import Any

__all__ = ["decode_span_metadata", "span_skill_id"]


def decode_span_metadata(span: dict[str, Any]) -> dict[str, Any]:
    """Return the span's ``metadata`` as a dict.

    Tolerates both on-disk shapes:
    - ``dict`` (in-memory ``Span.to_dict()`` records)
    - JSON-encoded ``str`` (``SpanWriter`` serialisation)

    Malformed JSON, non-dict payloads, or missing metadata → ``{}``
    (never raises — mirrors the string-or-dict tolerance of
    ``skill_health._route_hit_skill_id_raw``).
    """
    raw = span.get("metadata")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}


def span_skill_id(span: dict[str, Any]) -> str | None:
    """Skill id recorded on the span, or None.

    Checks the top-level ``skill_id`` field first (newer schema), then
    ``metadata.skill_id`` — tolerating the writer's JSON-string metadata
    shape via :func:`decode_span_metadata`. Empty/non-string values → None.
    """
    top = span.get("skill_id")
    if isinstance(top, str) and top:
        return top
    sk = decode_span_metadata(span).get("skill_id")
    return sk if isinstance(sk, str) and sk else None
