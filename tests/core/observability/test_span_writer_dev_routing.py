"""SpanWriter dev/prod path routing — gates W0.B.

Verifies that SpanWriter routes spans to ``spans.dev.jsonl`` when running
inside a dev/test context, and to ``spans.jsonl`` in production.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

from vibesop.core.observability.dev_detect import ENV_OVERRIDE
from vibesop.core.observability.models import Span
from vibesop.core.observability.span_writer import SpanWriter


def _make_span(name: str = "test") -> Span:
    return Span(
        id="test-span",
        trace_id="test-trace",
        name=name,
        span_kind="task",
        agent_id="test-agent",
        status="ok",
    )


class TestDefaultPathRouting:
    def test_dev_context_routes_to_dev_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv(ENV_OVERRIDE, "dev")
        writer = SpanWriter()
        assert writer._path.name == "spans.dev.jsonl"
        # SpanWriter uses relative path; resolved parent should be under tmp_path
        assert writer._path.resolve().parent == (tmp_path / ".vibe" / "observability").resolve()

    def test_prod_context_routes_to_prod_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv(ENV_OVERRIDE, "prod")
        writer = SpanWriter()
        assert writer._path.name == "spans.jsonl"

    def test_explicit_storage_path_wins(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Even in dev context, explicit path takes precedence
        monkeypatch.setenv(ENV_OVERRIDE, "dev")
        explicit = tmp_path / "custom" / "spans.jsonl"
        writer = SpanWriter(storage_path=explicit)
        assert writer._path == explicit


class TestDevProdIsolation:
    def test_dev_writes_do_not_pollute_prod_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv(ENV_OVERRIDE, "dev")

        writer = SpanWriter()
        writer.write_span(_make_span("dev-action"))

        dev_file = tmp_path / ".vibe" / "observability" / "spans.dev.jsonl"
        prod_file = tmp_path / ".vibe" / "observability" / "spans.jsonl"

        assert dev_file.exists()
        assert not prod_file.exists()

    def test_prod_writes_do_not_pollute_dev_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv(ENV_OVERRIDE, "prod")

        writer = SpanWriter()
        writer.write_span(_make_span("prod-action"))

        dev_file = tmp_path / ".vibe" / "observability" / "spans.dev.jsonl"
        prod_file = tmp_path / ".vibe" / "observability" / "spans.jsonl"

        assert prod_file.exists()
        assert not dev_file.exists()
