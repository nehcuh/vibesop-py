"""Tests for Span dataclass schema (v8.2 extensions)."""

from __future__ import annotations

import pytest

from vibesop.core.observability.models import (
    CURRENT_SPAN_SCHEMA_VERSION,
    Span,
)


@pytest.fixture
def sample_span() -> Span:
    return Span(
        id=Span.new_id(),
        trace_id=Span.new_trace_id(),
        name="llm:claude-opus-4",
        span_kind="llm",
        parent_span_id="parent123",
    )


class TestSpanDefaults:
    def test_schema_version_defaults_to_current(self, sample_span: Span) -> None:
        assert sample_span.schema_version == CURRENT_SPAN_SCHEMA_VERSION

    def test_project_id_defaults_to_default(self, sample_span: Span) -> None:
        assert sample_span.project_id == "default"

    def test_current_span_schema_version_is_one(self) -> None:
        """Lock the version at 1 for v8.2. Bump only on schema-breaking change."""
        assert CURRENT_SPAN_SCHEMA_VERSION == 1


class TestSpanSerialisation:
    def test_to_dict_includes_schema_version(self, sample_span: Span) -> None:
        record = sample_span.to_dict()
        assert record["schema_version"] == CURRENT_SPAN_SCHEMA_VERSION

    def test_to_dict_includes_project_id(self, sample_span: Span) -> None:
        sample_span.project_id = "vibesop-py"
        record = sample_span.to_dict()
        assert record["project_id"] == "vibesop-py"

    def test_to_dict_round_trip_preserves_new_fields(self, sample_span: Span) -> None:
        """Writer → dict → reader (raw dict access, as aggregator does)."""
        sample_span.project_id = "tenant-a"
        record = sample_span.to_dict()
        # Aggregator reads via dict access, not from_dict
        assert record["schema_version"] == sample_span.schema_version
        assert record["project_id"] == "tenant-a"


class TestSpanFluentSetters:
    def test_with_project_id_returns_self(self, sample_span: Span) -> None:
        returned = sample_span.with_project_id("proj-x")
        assert returned is sample_span

    def test_with_project_id_sets_field(self, sample_span: Span) -> None:
        sample_span.with_project_id("proj-x")
        assert sample_span.project_id == "proj-x"


class TestSpanQueryByProjectId:
    """Smoke-test the discriminator use case: filter spans by project."""

    def test_filter_by_project_id(self) -> None:
        spans = [
            Span(id="1", trace_id="t", name="a", span_kind="task", project_id="alpha"),
            Span(id="2", trace_id="t", name="b", span_kind="task", project_id="beta"),
            Span(id="3", trace_id="t", name="c", span_kind="task", project_id="alpha"),
        ]
        alpha_only = [s for s in spans if s.project_id == "alpha"]
        assert {s.id for s in alpha_only} == {"1", "3"}
