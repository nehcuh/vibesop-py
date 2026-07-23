"""Tests for ``vibe trace prune`` CLI command.

Verifies:
* Old spans are pruned, recent ones kept
* Atomic write (temp + rename) — original file intact if write fails
* Dry-run mode makes no changes
* Spans without parseable started_at are kept (defensive)
* Missing span file = graceful no-op
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vibesop.cli.commands.trace_cmd import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _make_span(
    span_id: str,
    *,
    started_at: str,
    kind: str = "task",
    trace_id: str = "t1",
) -> dict:
    return {
        "id": span_id,
        "trace_id": trace_id,
        "parent_span_id": None,
        "span_kind": kind,
        "name": f"{kind}:test",
        "status": "ok",
        "duration_ms": 100,
        "tokens_input": 0,
        "tokens_output": 0,
        "cost_usd": 0.0,
        "started_at": started_at,
        "metadata": "{}",
    }


def _write_spans(path: Path, spans: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for s in spans:
            f.write(json.dumps(s) + "\n")


def _read_span_ids(path: Path) -> list[str]:
    ids: list[str] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                ids.append(json.loads(stripped)["id"])
    return ids


class TestPruneBasic:
    def test_prune_old_spans_keeps_recent(self, runner: CliRunner, tmp_path: Path) -> None:
        """Spans older than --days are pruned; recent ones kept."""
        span_file = tmp_path / "spans.jsonl"
        now = datetime.now(UTC)
        old = now - timedelta(days=60)
        recent = now - timedelta(days=5)

        _write_spans(span_file, [
            _make_span("old-1", started_at=old.isoformat()),
            _make_span("old-2", started_at=old.isoformat()),
            _make_span("recent-1", started_at=recent.isoformat()),
            _make_span("recent-2", started_at=recent.isoformat()),
        ])

        result = runner.invoke(
            app, ["prune", "--days", "30", "--span-file", str(span_file)]
        )
        assert result.exit_code == 0
        assert "Pruned 2 span(s)" in result.output

        remaining = _read_span_ids(span_file)
        assert remaining == ["recent-1", "recent-2"]

    def test_dry_run_makes_no_changes(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """--dry-run reports what would happen but writes nothing."""
        span_file = tmp_path / "spans.jsonl"
        now = datetime.now(UTC)
        old = now - timedelta(days=60)

        original_spans = [
            _make_span("old-1", started_at=old.isoformat()),
            _make_span("recent-1", started_at=now.isoformat()),
        ]
        _write_spans(span_file, original_spans)
        original_content = span_file.read_text()

        result = runner.invoke(
            app,
            ["prune", "--days", "30", "--dry-run", "--span-file", str(span_file)],
        )
        assert result.exit_code == 0
        assert "Dry-run mode" in result.output
        assert "would prune: 1" in result.output

        # File unchanged
        assert span_file.read_text() == original_content

    def test_missing_span_file_graceful(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """No span file → graceful message, no crash."""
        missing = tmp_path / "does-not-exist.jsonl"
        result = runner.invoke(
            app, ["prune", "--span-file", str(missing)]
        )
        assert result.exit_code == 0
        assert "not found" in result.output

    def test_nothing_to_prune(self, runner: CliRunner, tmp_path: Path) -> None:
        """All spans recent → no-op message."""
        span_file = tmp_path / "spans.jsonl"
        now = datetime.now(UTC)
        _write_spans(span_file, [
            _make_span("recent-1", started_at=now.isoformat()),
        ])

        result = runner.invoke(
            app, ["prune", "--days", "30", "--span-file", str(span_file)]
        )
        assert result.exit_code == 0
        assert "Nothing to prune" in result.output

    def test_empty_file_is_noop(self, runner: CliRunner, tmp_path: Path) -> None:
        """An empty span file (total=0) is a no-op, not a crash.

        Edge case kimi flagged: byte-count 0 → loop reads nothing → total=0,
        pruned=0 → 'Nothing to prune' branch. Verifies no exception.
        """
        span_file = tmp_path / "spans.jsonl"
        span_file.write_text("")  # truly empty

        result = runner.invoke(
            app, ["prune", "--days", "30", "--span-file", str(span_file)]
        )
        assert result.exit_code == 0
        assert "Nothing to prune" in result.output
        # File remains empty
        assert span_file.read_text() == ""


class TestPruneAtomicity:
    def test_no_tmp_file_left_on_success(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """After a successful prune, no .tmp file should be left behind.

        Updated for mkstemp: temp file name is randomised (prefix + suffix),
        so we glob for ``*.tmp`` rather than hardcoding ``spans.jsonl.tmp``.
        """
        span_file = tmp_path / "spans.jsonl"
        old = (datetime.now(UTC) - timedelta(days=60)).isoformat()
        _write_spans(span_file, [_make_span("old-1", started_at=old)])

        runner.invoke(app, ["prune", "--days", "30", "--span-file", str(span_file)])

        assert not list(tmp_path.glob("*.tmp"))

    def test_keeps_unparseable_started_at(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Spans with missing/garbled started_at are kept, not dropped."""
        span_file = tmp_path / "spans.jsonl"
        old = (datetime.now(UTC) - timedelta(days=60)).isoformat()

        # Build raw content mixing valid + unparseable timestamps
        with span_file.open("w") as f:
            f.write(json.dumps(_make_span("old-1", started_at=old)) + "\n")
            # Missing started_at
            bad1 = _make_span("bad-1", started_at="")
            f.write(json.dumps(bad1) + "\n")
            # Garbled timestamp
            bad2 = _make_span("bad-2", started_at="not-a-date")
            f.write(json.dumps(bad2) + "\n")

        result = runner.invoke(
            app, ["prune", "--days", "30", "--span-file", str(span_file)]
        )
        assert result.exit_code == 0
        # "old-1" pruned (valid timestamp, old); "bad-1" and "bad-2" kept
        remaining = _read_span_ids(span_file)
        assert "bad-1" in remaining
        assert "bad-2" in remaining
        assert "old-1" not in remaining

    def test_preserves_span_order(self, runner: CliRunner, tmp_path: Path) -> None:
        """Prune preserves the relative order of surviving spans."""
        span_file = tmp_path / "spans.jsonl"
        now = datetime.now(UTC)
        old = (now - timedelta(days=60)).isoformat()

        _write_spans(span_file, [
            _make_span("s1", started_at=old),
            _make_span("s2", started_at=now.isoformat()),
            _make_span("s3", started_at=old),
            _make_span("s4", started_at=now.isoformat()),
        ])

        runner.invoke(app, ["prune", "--days", "30", "--span-file", str(span_file)])

        assert _read_span_ids(span_file) == ["s2", "s4"]
