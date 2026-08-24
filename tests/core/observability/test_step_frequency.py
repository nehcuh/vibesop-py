"""W4.B — step frequency labeling tests.

Verifies ``label_step_frequency`` classifies each step name as
``core`` / ``common`` / ``optional`` by span coverage.

Thresholds (per W4 design):
- ``core``: appears in ≥70% of cluster spans
- ``common``: 30–70%
- ``optional``: <30%

Coverage semantics: each span contributes a SET of step names. A step
that appears multiple times within one span (e.g. in a nested
``metadata.steps`` list) counts once toward that span's coverage. We
count span-coverage, not raw occurrences.
"""

from __future__ import annotations

from vibesop.core.observability.skill_promote import label_step_frequency


def _span(name: str, *, steps: list[str] | None = None) -> dict:
    """Build a minimal span dict."""
    metadata = {"steps": steps} if steps is not None else {}
    return {"name": name, "metadata": metadata}


class TestStepFrequency:
    def test_core_when_step_in_all_spans(self) -> None:
        """100% coverage → core."""
        spans = [_span("route:query")] * 5
        freq, labels, core_steps = label_step_frequency(spans, total_span_count=5)
        assert freq["route:query"] == 5
        assert labels["route:query"] == "core"
        assert core_steps == ["route:query"]

    def test_core_threshold_70pct_boundary(self) -> None:
        """Exactly 70% coverage → core (inclusive lower bound)."""
        # 7 of 10 spans include this step.
        spans = [_span("route:query")] * 7 + [_span("other")] * 3
        _, labels, core_steps = label_step_frequency(spans, total_span_count=10)
        assert labels["route:query"] == "core"
        assert core_steps == ["route:query"]

    def test_common_50pct(self) -> None:
        """50% coverage → common."""
        spans = [_span("tool:edit")] * 5 + [_span("tool:read")] * 5
        _, labels, _ = label_step_frequency(spans, total_span_count=10)
        assert labels["tool:edit"] == "common"
        assert labels["tool:read"] == "common"

    def test_common_threshold_30pct_boundary(self) -> None:
        """Exactly 30% coverage → common (inclusive lower bound)."""
        # 3 of 10 spans.
        spans = [_span("tool:edit")] * 3 + [_span("route:query")] * 7
        _, labels, _ = label_step_frequency(spans, total_span_count=10)
        assert labels["tool:edit"] == "common"

    def test_optional_below_30pct(self) -> None:
        """<30% coverage → optional."""
        # 2 of 10 spans = 20%.
        spans = [_span("rare:step")] * 2 + [_span("route:query")] * 8
        _, labels, _ = label_step_frequency(spans, total_span_count=10)
        assert labels["rare:step"] == "optional"

    def test_empty_spans_returns_empty(self) -> None:
        """Empty spans input → empty freq / labels / core_steps."""
        freq, labels, core_steps = label_step_frequency([], total_span_count=10)
        assert freq == {}
        assert labels == {}
        assert core_steps == []

    def test_zero_total_span_count_returns_empty(self) -> None:
        """Zero denominator → empty (avoids divide-by-zero)."""
        freq, labels, core_steps = label_step_frequency([_span("x")], total_span_count=0)
        assert freq == {}
        assert labels == {}
        assert core_steps == []

    def test_dedup_per_span(self) -> None:
        """A step name appearing multiple times WITHIN one span (via
        nested ``metadata.steps``) counts once toward that span's
        coverage. We count span-coverage, not raw occurrences.

        Concretely: 1 span with ``name=route:query`` AND
        ``metadata.steps=["tool:edit", "tool:edit", "tool:edit"]`` →
        each step name counts 1 from this span, not 3 for tool:edit.
        """
        spans = [
            _span("route:query", steps=["tool:edit", "tool:edit", "tool:edit"]),
            _span("route:query"),
            _span("route:query"),
        ]
        freq, _, _ = label_step_frequency(spans, total_span_count=3)
        assert freq["route:query"] == 3  # in all 3 spans
        assert freq["tool:edit"] == 1  # only 1 span covers it (deduped)

    def test_core_steps_sorted_by_freq_desc(self) -> None:
        """When multiple steps are core, ``core_steps`` is sorted by
        frequency desc (then name asc for ties). The highest-frequency
        core step goes first — it's the most reliable signal."""
        # 10 spans, all include both route:query AND tool:edit, but
        # tool:edit appears in metadata.steps of fewer spans.
        spans = []
        for _ in range(7):
            spans.append(_span("route:query", steps=["tool:edit"]))
        for _ in range(3):
            spans.append(_span("route:query"))
        # route:query coverage = 10/10 = 100% → core
        # tool:edit coverage = 7/10 = 70% → core (boundary)
        _, _, core_steps = label_step_frequency(spans, total_span_count=10)
        assert core_steps == ["route:query", "tool:edit"]
