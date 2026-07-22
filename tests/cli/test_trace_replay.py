"""Tests for ``vibe trace replay`` CLI command.

Covers:
* Basic replay: reads span JSONL, groups by trace_id, renders tree
* Trace ID filter
* Span file missing → graceful panel
* Empty span file → graceful message
* JSON output mode returns structured data
* Multi-trace files respect --limit
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vibesop.cli.commands.trace_cmd import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _make_span(
    span_id: str,
    trace_id: str,
    *,
    parent: str | None = None,
    kind: str = "task",
    name: str = "test",
    status: str = "ok",
    duration_ms: int = 100,
    tokens_in: int = 0,
    tokens_out: int = 0,
    cost_usd: float = 0.0,
    skill_id: str | None = None,
    started_at: str = "2026-07-22T10:00:00+00:00",
) -> dict:
    metadata: dict = {}
    if skill_id is not None:
        metadata["skill_id"] = skill_id
    return {
        "id": span_id,
        "trace_id": trace_id,
        "parent_span_id": parent,
        "span_kind": kind,
        "name": name,
        "status": status,
        "duration_ms": duration_ms,
        "tokens_input": tokens_in,
        "tokens_output": tokens_out,
        "cost_usd": cost_usd,
        "started_at": started_at,
        "metadata": json.dumps(metadata) if metadata else "{}",
    }


def _write_spans(path: Path, spans: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for s in spans:
            f.write(json.dumps(s) + "\n")


class TestReplayBasic:
    def test_replay_single_trace(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        span_file = tmp_path / "spans.jsonl"
        _write_spans(span_file, [
            _make_span("task-1", "trace-1", kind="task", name="route:hello", skill_id="mcp-install"),
            _make_span(
                "llm-1", "trace-1", parent="task-1", kind="llm",
                name="llm:deepseek:v4", duration_ms=80,
                tokens_in=120, tokens_out=30, cost_usd=0.0001,
            ),
            _make_span(
                "llm-2", "trace-1", parent="task-1", kind="llm",
                name="llm:deepseek:v4", status="error",
                tokens_in=60, tokens_out=0,
            ),
        ])

        result = runner.invoke(app, ["replay", "--span-file", str(span_file)])
        assert result.exit_code == 0
        assert "trace-1" in result.output
        assert "route:hello" in result.output
        assert "llm:deepseek:v4" in result.output
        assert "mcp-install" in result.output
        assert "LLM: 2" in result.output

    def test_replay_no_span_file(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        missing = tmp_path / "does-not-exist.jsonl"
        result = runner.invoke(app, ["replay", "--span-file", str(missing)])
        assert result.exit_code == 0  # graceful panel, not crash
        assert "No Span Data" in result.output or "not found" in result.output

    def test_replay_empty_span_file(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        empty = tmp_path / "empty.jsonl"
        empty.write_text("")
        result = runner.invoke(app, ["replay", "--span-file", str(empty)])
        assert result.exit_code == 0
        assert "No spans" in result.output


class TestReplayFiltering:
    def test_trace_id_prefix_filter(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        span_file = tmp_path / "spans.jsonl"
        _write_spans(span_file, [
            _make_span("t1", "trace-aaa", kind="task", name="route:a"),
            _make_span("t2", "trace-bbb", kind="task", name="route:b"),
        ])

        result = runner.invoke(
            app, ["replay", "--span-file", str(span_file), "--trace-id", "trace-a"]
        )
        assert result.exit_code == 0
        assert "trace-aaa" in result.output
        assert "trace-bbb" not in result.output

    def test_trace_id_no_match_exits_1(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        span_file = tmp_path / "spans.jsonl"
        _write_spans(span_file, [_make_span("t1", "trace-aaa", kind="task")])

        result = runner.invoke(
            app, ["replay", "--span-file", str(span_file), "--trace-id", "zzz"]
        )
        assert result.exit_code == 1

    def test_limit_caps_traces(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        span_file = tmp_path / "spans.jsonl"
        spans = []
        for i in range(5):
            spans.append(_make_span(
                f"t{i}", f"trace-{i}", kind="task",
                name=f"route:q{i}", started_at=f"2026-07-22T10:0{i}:00+00:00",
            ))
        _write_spans(span_file, spans)

        result = runner.invoke(
            app, ["replay", "--span-file", str(span_file), "--limit", "2"]
        )
        assert result.exit_code == 0
        assert "2 trace(s)" in result.output


class TestReplayJsonOutput:
    def test_json_output_structure(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        span_file = tmp_path / "spans.jsonl"
        _write_spans(span_file, [
            _make_span("task-1", "trace-x", kind="task", name="route:x"),
            _make_span(
                "llm-1", "trace-x", parent="task-1", kind="llm",
                name="llm:deepseek:v4", tokens_in=100, tokens_out=20,
            ),
        ])

        result = runner.invoke(
            app, ["replay", "--span-file", str(span_file), "--json"]
        )
        assert result.exit_code == 0
        # Output is JSON — parse and verify shape
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["trace_id"] == "trace-x"
        assert len(data[0]["spans"]) == 2


class TestReplayTree:
    def test_nested_tree_indentation(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Multi-level nesting renders with indentation."""
        span_file = tmp_path / "spans.jsonl"
        _write_spans(span_file, [
            _make_span("root", "t1", kind="task", name="route:root"),
            _make_span(
                "child1", "t1", parent="root", kind="llm",
                name="llm:deepseek:v4",
            ),
            _make_span(
                "child2", "t1", parent="root", kind="tool_call",
                name="tool:read_file",
            ),
            _make_span(
                "grandchild", "t1", parent="child2", kind="file_edit",
                name="file:foo.py",
            ),
        ])

        result = runner.invoke(app, ["replay", "--span-file", str(span_file)])
        assert result.exit_code == 0
        lines = result.output.splitlines()
        # Find the lines for each span — depth inferred by leading spaces
        grandchild_line = next(ln for ln in lines if "file:foo.py" in ln)
        # Grandchild should be indented more than child2
        child2_line = next(ln for ln in lines if "tool:read_file" in ln)
        assert grandchild_line.index("F") > child2_line.index("X")

    def test_mid_tree_orphan_marked(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Span whose parent_span_id points to a missing span is rendered at
        depth 0 with an ORPHAN marker (not silently dropped). Regression for
        Pi's A.1 finding."""
        span_file = tmp_path / "spans.jsonl"
        _write_spans(span_file, [
            _make_span("root", "t1", kind="task", name="route:root"),
            _make_span(
                "ghost-child", "t1", parent="missing-parent-id",
                kind="llm", name="llm:deepseek:v4",
            ),
        ])

        result = runner.invoke(app, ["replay", "--span-file", str(span_file)])
        assert result.exit_code == 0
        assert "ORPHAN" in result.output
        assert "ghost-child" in result.output or "llm:deepseek:v4" in result.output
        assert "Orphans: 1" in result.output

    def test_zero_duration_rendered_not_dash(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """duration_ms=0 is a valid sub-millisecond span, must render as 0ms
        not '-'. Regression for Pi's A.1 finding."""
        span_file = tmp_path / "spans.jsonl"
        _write_spans(span_file, [
            _make_span("fast", "t1", kind="task", name="route:fast", duration_ms=0),
        ])

        result = runner.invoke(app, ["replay", "--span-file", str(span_file)])
        assert result.exit_code == 0
        assert "0ms" in result.output
        assert "route:fast" in result.output

    def test_none_cost_rendered_as_dash_zero_as_zero(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """cost_usd=None renders as '-'; cost_usd=0.0 renders as '$0.00'.
        Regression for Pi's A.5 finding."""
        span_file = tmp_path / "spans.jsonl"
        _write_spans(span_file, [
            _make_span("free", "t1", kind="task", name="route:free", cost_usd=0.0),
            _make_span("unknown", "t2", kind="task", name="route:unknown", cost_usd=0.0),
        ])
        # Patch 'unknown' to have null cost_usd (simulating missing field)
        text = span_file.read_text()
        text = text.replace(
            '"name": "route:unknown", "cost_usd": 0.0',
            '"name": "route:unknown", "cost_usd": null',
        )
        span_file.write_text(text)

        result = runner.invoke(app, ["replay", "--span-file", str(span_file)])
        assert result.exit_code == 0
        assert "$0.00" in result.output  # free span shows $0.00, not -
        assert "route:free" in result.output
        assert "route:unknown" in result.output

    def test_error_status_spans_render(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """status='error' must render (red) without crashing."""
        span_file = tmp_path / "spans.jsonl"
        _write_spans(span_file, [
            _make_span("task-1", "t1", kind="task", name="route:x", status="ok"),
            _make_span(
                "llm-failed", "t1", parent="task-1", kind="llm",
                name="llm:deepseek:v4", status="error",
            ),
        ])

        result = runner.invoke(app, ["replay", "--span-file", str(span_file)])
        assert result.exit_code == 0
        assert "error" in result.output
        assert "llm:deepseek:v4" in result.output


class TestMetricsCommand:
    """Closes GAP-3: vibe trace metrics consumes SpanAggregator."""

    def test_metrics_no_data_graceful(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        span_file = tmp_path / "spans.jsonl"
        _write_spans(span_file, [
            _make_span("t1", "trace-x", kind="task", skill_id="other-skill"),
        ])

        result = runner.invoke(
            app,
            ["metrics", "missing-skill", "--span-file", str(span_file)],
        )
        assert result.exit_code == 0
        assert "No span data" in result.output

    def test_metrics_returns_aggregated_values(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        span_file = tmp_path / "spans.jsonl"
        _write_spans(span_file, [
            _make_span("task-1", "trace-1", kind="task", skill_id="mcp-install"),
            _make_span(
                "llm-1", "trace-1", parent="task-1", kind="llm",
                name="llm:ds:v4", tokens_in=100, tokens_out=20, cost_usd=0.002,
            ),
            _make_span(
                "llm-2", "trace-1", parent="task-1", kind="llm",
                name="llm:ds:v4", tokens_in=50, tokens_out=10, cost_usd=0.001,
            ),
        ])

        result = runner.invoke(
            app,
            ["metrics", "mcp-install", "--span-file", str(span_file), "--json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["skill_id"] == "mcp-install"
        assert data["source"] == "spans"
        assert data["total_executions"] == 1
        assert data["llm_call_count"] == 2
        assert data["llm_success_rate"] == 1.0
        assert data["avg_tokens"] == 90  # (100+20 + 50+10) / 2 = 90
        assert data["total_cost_usd"] == pytest.approx(0.003, abs=1e-6)

    def test_metrics_project_id_filter(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """project_id filter excludes spans from other projects."""
        span_file = tmp_path / "spans.jsonl"
        # Two task-spans, same skill_id but different project_id
        s1 = _make_span("t1", "tr1", kind="task", skill_id="skill-x")
        s1["project_id"] = "proj-a"
        s2 = _make_span("t2", "tr2", kind="task", skill_id="skill-x")
        s2["project_id"] = "proj-b"
        _write_spans(span_file, [s1, s2])

        # Filter to proj-a only
        result = runner.invoke(
            app,
            [
                "metrics", "skill-x",
                "--span-file", str(span_file),
                "--project-id", "proj-a",
                "--json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["total_executions"] == 1  # only proj-a span counted
