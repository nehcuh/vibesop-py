"""Shared helpers for reading span fields (W5.0 review Q3).

``_span_timestamp`` lived in both ``recall.py`` and ``clustering.py`` with
explicit "avoid circular import" justification — but ``recall`` already
imports from ``clustering``, so the dependency is one-way and a shared
util resolves the duplication cleanly.
"""

from __future__ import annotations

__all__ = ["span_timestamp"]


def span_timestamp(span: dict) -> str | None:
    """Read a span's timestamp, preferring ``started_at`` (real schema).

    ``Span.to_dict()`` writes ``started_at`` (models.py:110). Older data
    and some test fixtures use ``timestamp`` instead. This helper reads
    the canonical field first, falls back to the legacy name.

    Returns None when neither field is present. Callers that need to
    filter by time should decide explicitly whether to keep or drop
    spans with missing timestamps (recall keeps them by policy; other
    callers may want stricter semantics).
    """
    ts = span.get("started_at")
    if ts:
        return ts  # type: ignore[return-value]
    return span.get("timestamp")
