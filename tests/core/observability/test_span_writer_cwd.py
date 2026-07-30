"""SpanWriter eager path resolution — gates W5.1 Task 1.1.

Verifies that SpanWriter resolves relative paths to absolute at construction
time, so a later os.chdir() between tracer singleton construction and first
span emit does not move the file. The tracer singleton is built lazily on
first emit, so the path must be locked at SpanWriter.__init__ time.

Matches ``process_identity._process_project_id`` eager-cached cwd semantics
— the two must agree on which cwd is authoritative.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

from vibesop.core.observability.dev_detect import ENV_OVERRIDE
from vibesop.core.observability.models import Span
from vibesop.core.observability.span_writer import SpanWriter


def _make_span() -> Span:
    return Span(
        id="test-span",
        trace_id="test-trace",
        name="cwd-test",
        span_kind="task",
        agent_id="test-agent",
        status="ok",
    )


class TestEagerPathResolve:
    def test_relative_path_resolves_against_construction_cwd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv(ENV_OVERRIDE, "prod")
        writer = SpanWriter()

        assert writer._path.is_absolute(), "path must be absolute after construction"
        assert writer._path == (tmp_path / ".vibe" / "observability" / "spans.jsonl").resolve()

    def test_chdir_after_init_does_not_move_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        other_path = tmp_path / "other-cwd"
        other_path.mkdir()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv(ENV_OVERRIDE, "prod")
        writer = SpanWriter()

        original_path = writer._path
        monkeypatch.chdir(other_path)

        writer.write_span(_make_span())

        assert writer._path == original_path, "path must not shift after chdir"
        assert original_path.exists(), "file must land in the original cwd, not the new one"
        assert not (other_path / ".vibe" / "observability" / "spans.jsonl").exists()

    def test_absolute_path_passed_through_unchanged(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(ENV_OVERRIDE, "dev")
        explicit = tmp_path / "custom" / "spans.jsonl"
        writer = SpanWriter(storage_path=explicit)

        assert writer._path == explicit
        assert writer._path.is_absolute()

    def test_relative_storage_path_resolves_against_construction_cwd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv(ENV_OVERRIDE, "prod")
        writer = SpanWriter(storage_path="custom/relative/spans.jsonl")

        assert writer._path.is_absolute()
        assert writer._path == (tmp_path / "custom" / "relative" / "spans.jsonl").resolve()
