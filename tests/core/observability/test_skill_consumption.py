"""F2 skill-consumption ledger tests (selected/read/applicable/executed/accepted).

Fixtures are built from the REAL producer shapes — ``Span`` objects written
through ``SpanWriter`` (metadata serialised to a JSON string, as production
does) plus one file hand-written from ``Span.to_dict()`` (metadata as a dict)
so both wire forms are covered. No hand-rolled key guesses.

The load-bearing assertions are NEGATIVE: the four unmeasurable segments must
stay ``state is None`` with their exact reason strings, and neither proxy
(``injection_attempted``, ``read_like_tool_calls``) may ever be promoted into
``read.state``. R6 is the cautionary case: 10 read-like calls, 0 of them a
SKILL.md.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vibesop.cli.commands import observe_cmd
from vibesop.core.observability.models import Span
from vibesop.core.observability.skill_consumption import (
    LEDGER_FILENAME,
    ROTATED_FILENAME,
    R_HIT_WITHOUT_SKILL,
    R_MISSING_HAS_MATCH,
    R_NON_BOOLEAN_HAS_MATCH,
    R_NOT_OBSERVABLE,
    R_NO_HARNESS_RECEIPT,
    R_NO_STEP_RECEIPT,
    R_NO_VERIFICATION_RECEIPT,
    SCHEMA,
    SCHEMA_VERSION,
    build_row,
    consumption_report,
    record_consumption,
    render_human,
)
from vibesop.core.observability.span_writer import SpanWriter
from vibesop.core.observability.task_id import derive_task_id
from vibesop.core.observability.tool_call_bridge import (
    _spans_filename,
    bridge_entries,
)

T0 = datetime(2026, 9, 21, 10, 0, 0, tzinfo=UTC)
#: Sentinel query carried by every fixture span (privacy regression: this
#: string must never reach the ledger).
SENTINEL_QUERY = "SENTINEL-QUERY-TEXT-do-not-persist"
runner = CliRunner()


def _observability_dir(root: Path) -> Path:
    return root / ".vibe" / "observability"


def _spans_path(root: Path) -> Path:
    # Under pytest is_dev_environment() is True → producers/readers use the dev
    # spans file; fixtures must make the same selection.
    return _observability_dir(root) / _spans_filename()


def _ledger_path(root: Path) -> Path:
    return _observability_dir(root) / LEDGER_FILENAME


def _rotated_path(root: Path) -> Path:
    return _observability_dir(root) / ROTATED_FILENAME


def _make_route_span(
    root: Path,
    *,
    query: str = SENTINEL_QUERY,
    session: str | None = "sess-1",
    started: datetime = T0,
    metadata: dict | None = None,
    span_id: str | None = None,
    trace_id: str | None = None,
    task_id: str | None = None,
    agent_id: str | None = "claude-code",
) -> Span:
    """A route span in the exact producer shape, written via SpanWriter."""
    meta = {"query": query[:200], "platform": "claude-code", "mode": "single"}
    meta.update(metadata or {})
    span = Span(
        id=span_id or Span.new_id(),
        trace_id=trace_id or Span.new_trace_id(),
        name=f"route:{query[:40]}",
        span_kind="task",
        task_id=task_id if task_id is not None else derive_task_id(query),
        session_id=session,
        agent_id=agent_id,
        status="ok",
        started_at=started,
        ended_at=started,
        metadata=meta,
    )
    SpanWriter(storage_path=_spans_path(root)).write_span(span)
    return span


def _make_tool_span(
    root: Path,
    *,
    parent: Span,
    tool: str,
    at: datetime = T0 + timedelta(minutes=1),
) -> Span:
    """A bridged tool_call span in the shape tool_call_bridge writes."""
    span = Span(
        id=Span.new_id(),
        trace_id=parent.trace_id,
        name=f"tool:{tool}",
        span_kind="tool_call",
        task_id=parent.task_id,
        session_id=parent.session_id,
        agent_id=parent.agent_id,
        parent_span_id=parent.id,
        status="ok",
        started_at=at,
        ended_at=at,
        metadata={"tool": tool, "source": "tool_call_bridge"},
    )
    SpanWriter(storage_path=_spans_path(root)).write_span(span)
    return span


def _rows(root: Path) -> list[dict]:
    path = _ledger_path(root)
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _row_for(root: Path, span_id: str) -> dict:
    for row in _rows(root):
        if row["span_id"] == span_id:
            return row
    raise AssertionError(f"no ledger row for span {span_id}")


# ---------------------------------------------------------------------------
# selected — the one segment that lands this round
# ---------------------------------------------------------------------------


class TestSelected:
    def test_hit_writes_selected_yes_with_ordered_skill_ids(self, tmp_path: Path) -> None:
        span = _make_route_span(
            tmp_path,
            metadata={
                "has_match": True,
                "skill_id": "builtin/code-review",
                "top_skills": ["builtin/code-review", "superpowers-tdd", "fallback-llm", ""],
                "mode": "single",
            },
        )
        assert record_consumption(tmp_path) == 1

        row = _row_for(tmp_path, span.id)
        assert row["schema"] == SCHEMA
        assert row["schema_version"] == SCHEMA_VERSION
        # Real serialiser field names, not hand-rolled ones.
        assert row["task_id"] == span.task_id
        assert row["session_id"] == "sess-1"
        assert row["agent_id"] == "claude-code"
        assert row["route_started_at"] == span.started_at.isoformat()
        assert row["route_population"] == "hook"
        assert row["selected"]["state"] == "yes"
        assert row["selected"]["reason"] is None
        assert row["selected"]["primary"] == "builtin/code-review"
        # Deduped, sentinel/empty dropped, capped at 3.
        assert row["selected"]["skill_ids"] == ["builtin/code-review", "superpowers-tdd"]

    def test_miss_writes_selected_no(self, tmp_path: Path) -> None:
        span = _make_route_span(tmp_path, metadata={"has_match": False, "skill_id": ""})
        record_consumption(tmp_path)
        row = _row_for(tmp_path, span.id)
        assert row["selected"]["state"] == "no"
        assert row["selected"]["reason"] is None
        assert row["selected"]["skill_ids"] == []

    @pytest.mark.parametrize(
        ("metadata", "reason"),
        [
            ({"skill_id": "x"}, R_MISSING_HAS_MATCH),
            ({"has_match": None, "skill_id": "x"}, R_MISSING_HAS_MATCH),
            ({"has_match": "yes", "skill_id": "x"}, R_NON_BOOLEAN_HAS_MATCH),
            ({"has_match": 1, "skill_id": "x"}, R_NON_BOOLEAN_HAS_MATCH),
            # gate41 hole: has_match=true with no real skill id is never a hit.
            ({"has_match": True, "skill_id": ""}, R_HIT_WITHOUT_SKILL),
            ({"has_match": True, "skill_id": "fallback-llm"}, R_HIT_WITHOUT_SKILL),
        ],
    )
    def test_unscorable_verdicts_are_null_with_reason(
        self, tmp_path: Path, metadata: dict, reason: str
    ) -> None:
        span = _make_route_span(tmp_path, metadata=metadata)
        record_consumption(tmp_path)
        selected = _row_for(tmp_path, span.id)["selected"]
        assert selected["state"] is None
        assert selected["reason"] == reason

    def test_dict_metadata_form_from_to_dict(self, tmp_path: Path) -> None:
        """The raw ``Span.to_dict()`` form (metadata as a dict) also parses."""
        span = Span(
            id="span-dict-form",
            trace_id="trace-1",
            name=f"route:{SENTINEL_QUERY[:40]}",
            span_kind="task",
            task_id=derive_task_id(SENTINEL_QUERY),
            session_id="sess-dict",
            agent_id="grok-build",
            status="ok",
            started_at=T0,
            ended_at=T0,
            metadata={"query": SENTINEL_QUERY, "mode": "single", "has_match": False},
        )
        path = _spans_path(tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(span.to_dict()) + "\n", encoding="utf-8")

        assert record_consumption(tmp_path) == 1
        row = _row_for(tmp_path, "span-dict-form")
        assert row["selected"]["state"] == "no"
        assert row["project_id"] == "default"


# ---------------------------------------------------------------------------
# The honest nulls — the load-bearing negative assertions
# ---------------------------------------------------------------------------


class TestHonestNulls:
    def test_four_segments_are_null_with_exact_reasons(self, tmp_path: Path) -> None:
        span = _make_route_span(
            tmp_path, metadata={"has_match": True, "skill_id": "builtin/code-review"}
        )
        record_consumption(tmp_path)
        row = _row_for(tmp_path, span.id)

        assert row["read"]["state"] is None
        assert row["read"]["reason"] == R_NO_HARNESS_RECEIPT
        assert row["applicable"] == {"state": None, "reason": R_NOT_OBSERVABLE}
        assert row["executed"] == {"state": None, "reason": R_NO_STEP_RECEIPT}
        assert row["accepted"] == {"state": None, "reason": R_NO_VERIFICATION_RECEIPT}

    def test_r6_shape_read_calls_never_promote_read_state(self, tmp_path: Path) -> None:
        """R6: a miss with 10 read-like tool calls still read NOTHING (of the skill)."""
        span = _make_route_span(tmp_path, metadata={"has_match": False, "skill_id": ""})
        for _ in range(10):
            _make_tool_span(tmp_path, parent=span, tool="Read")
        record_consumption(tmp_path)

        read = _row_for(tmp_path, span.id)["read"]
        assert read["state"] is None
        assert read["reason"] == R_NO_HARNESS_RECEIPT
        assert read["evidence"]["read_like_tool_calls"] == 10
        assert read["evidence"]["injection_attempted"] is False
        # The proxy is a proxy: no field on the segment claims a SKILL.md read.
        assert "skill_read" not in read
        assert "skill_path" not in read["evidence"]

    def test_hit_injection_attempted_true_but_read_still_null(self, tmp_path: Path) -> None:
        span = _make_route_span(
            tmp_path, metadata={"has_match": True, "skill_id": "builtin/code-review"}
        )
        record_consumption(tmp_path)
        read = _row_for(tmp_path, span.id)["read"]
        assert read["evidence"]["injection_attempted"] is True
        assert read["state"] is None

    def test_unknown_verdict_leaves_injection_unknown(self, tmp_path: Path) -> None:
        span = _make_route_span(tmp_path, metadata={"skill_id": ""})
        record_consumption(tmp_path)
        read = _row_for(tmp_path, span.id)["read"]
        assert read["evidence"]["injection_attempted"] is None
        assert read["state"] is None


# ---------------------------------------------------------------------------
# Proxies and skip rules
# ---------------------------------------------------------------------------


class TestProxies:
    def test_cli_population_never_injects_even_on_a_hit(self, tmp_path: Path) -> None:
        span = _make_route_span(
            tmp_path,
            metadata={
                "has_match": True,
                "skill_id": "builtin/code-review",
                "platform": "vibe-cli",
            },
        )
        record_consumption(tmp_path)
        row = _row_for(tmp_path, span.id)
        assert row["route_population"] == "cli"
        assert row["read"]["evidence"]["injection_attempted"] is False

    def test_source_cli_marker_also_counts_as_cli(self, tmp_path: Path) -> None:
        span = _make_route_span(
            tmp_path, metadata={"has_match": True, "skill_id": "x", "source": "cli"}
        )
        record_consumption(tmp_path)
        assert _row_for(tmp_path, span.id)["route_population"] == "cli"

    def test_read_like_allowlist_is_case_insensitive_and_reports_all_tools(
        self, tmp_path: Path
    ) -> None:
        span = _make_route_span(tmp_path, metadata={"has_match": True, "skill_id": "x"})
        for tool in ("Read", "read_file", "view", "Bash", "Edit", "Bash"):
            _make_tool_span(tmp_path, parent=span, tool=tool)
        record_consumption(tmp_path)

        evidence = _row_for(tmp_path, span.id)["read"]["evidence"]
        assert evidence["read_like_tool_calls"] == 3
        assert evidence["tools"] == ["Bash", "Edit", "Read", "read_file", "view"]

    def test_only_tool_spans_parented_to_the_route_span_count(self, tmp_path: Path) -> None:
        first = _make_route_span(tmp_path, span_id="span-a", started=T0)
        second = _make_route_span(tmp_path, span_id="span-b", started=T0 + timedelta(minutes=5))
        _make_tool_span(tmp_path, parent=first, tool="Read")
        _make_tool_span(tmp_path, parent=first, tool="Read")
        _make_tool_span(tmp_path, parent=second, tool="Bash")
        record_consumption(tmp_path)

        assert _row_for(tmp_path, "span-a")["read"]["evidence"]["read_like_tool_calls"] == 2
        assert _row_for(tmp_path, "span-b")["read"]["evidence"]["read_like_tool_calls"] == 0

    @pytest.mark.parametrize("mode", ["not_intercepted", "slash_command"])
    def test_non_attempt_modes_write_no_row(self, tmp_path: Path, mode: str) -> None:
        _make_route_span(tmp_path, span_id="skip-me", metadata={"has_match": False, "mode": mode})
        _make_route_span(
            tmp_path, span_id="keep-me", metadata={"has_match": False, "mode": "single"}
        )
        record_consumption(tmp_path)

        assert [row["span_id"] for row in _rows(tmp_path)] == ["keep-me"]

    def test_non_route_task_and_non_task_spans_write_no_row(self, tmp_path: Path) -> None:
        writer = SpanWriter(storage_path=_spans_path(tmp_path))
        writer.write_span(
            Span(
                id="task-1",
                trace_id="t1",
                name="build",
                span_kind="task",
                started_at=T0,
                metadata={"has_match": True, "skill_id": "x"},
            )
        )
        writer.write_span(
            Span(
                id="llm-1",
                trace_id="t1",
                name="route:fake-llm-span",
                span_kind="llm_call",
                started_at=T0,
                metadata={"has_match": True, "skill_id": "x"},
            )
        )
        assert record_consumption(tmp_path) == 0
        assert _rows(tmp_path) == []


# ---------------------------------------------------------------------------
# Persistence: idempotency, upsert, rotation
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_rerun_without_changes_touches_nothing(self, tmp_path: Path) -> None:
        _make_route_span(tmp_path, span_id="span-a", metadata={"has_match": False})
        assert record_consumption(tmp_path) == 1
        first = _ledger_path(tmp_path).read_text(encoding="utf-8")
        mtime = _ledger_path(tmp_path).stat().st_mtime_ns

        assert record_consumption(tmp_path) == 0
        assert _ledger_path(tmp_path).read_text(encoding="utf-8") == first
        assert _ledger_path(tmp_path).stat().st_mtime_ns == mtime

    def test_later_bridged_tool_calls_refresh_the_row(self, tmp_path: Path) -> None:
        span = _make_route_span(
            tmp_path, span_id="span-a", metadata={"has_match": True, "skill_id": "x"}
        )
        record_consumption(tmp_path)
        recorded_at = _row_for(tmp_path, "span-a")["recorded_at"]
        assert _row_for(tmp_path, "span-a")["read"]["evidence"]["read_like_tool_calls"] == 0

        _make_tool_span(tmp_path, parent=span, tool="Read")
        assert record_consumption(tmp_path) == 1
        row = _row_for(tmp_path, "span-a")
        assert row["read"]["evidence"]["read_like_tool_calls"] == 1
        # First-write timestamp is preserved (the row is refreshed, not re-created).
        assert row["recorded_at"] == recorded_at

    def test_rows_outliving_the_spans_file_are_preserved(self, tmp_path: Path) -> None:
        _make_route_span(tmp_path, span_id="old-span", metadata={"has_match": False})
        record_consumption(tmp_path)
        _spans_path(tmp_path).unlink()

        assert record_consumption(tmp_path) == 0
        assert [row["span_id"] for row in _rows(tmp_path)] == ["old-span"]

    def test_no_spans_file_is_a_silent_no_op(self, tmp_path: Path) -> None:
        assert record_consumption(tmp_path) == 0
        assert not _ledger_path(tmp_path).exists()

    def test_rotation_moves_the_live_file_aside(self, tmp_path: Path) -> None:
        _make_route_span(tmp_path, span_id="span-a", started=T0, metadata={"has_match": False})
        assert record_consumption(tmp_path) == 1
        assert not _rotated_path(tmp_path).exists()

        # The next pass sees an oversize live file and rotates it aside first,
        # then rewrites the still-live route span into a fresh live ledger.
        assert record_consumption(tmp_path, max_bytes=1) == 1
        assert _rotated_path(tmp_path).exists()

        _make_route_span(
            tmp_path,
            span_id="span-b",
            started=T0 + timedelta(minutes=1),
            metadata={"has_match": False},
        )
        assert record_consumption(tmp_path, max_bytes=10**9) == 1

        result = consumption_report(_ledger_path(tmp_path))
        assert result.exit_code == 0
        # Live ∪ rotation, deduped by span_id.
        assert [row["span_id"] for row in result.report["rows"]] == ["span-a", "span-b"]
        assert result.report["counts"]["n_rows"] == 2
        assert result.report["counts"]["n_rotated_rows"] == 1

    def test_ledger_never_contains_query_text(self, tmp_path: Path) -> None:
        span = _make_route_span(
            tmp_path, metadata={"has_match": True, "skill_id": "builtin/code-review"}
        )
        record_consumption(tmp_path)
        text = _ledger_path(tmp_path).read_text(encoding="utf-8")
        assert SENTINEL_QUERY not in text
        assert "SENTINEL" not in text
        assert span.task_id is not None and span.task_id in text

    def test_corrupt_ledger_lines_are_dropped_on_rewrite(self, tmp_path: Path) -> None:
        _make_route_span(tmp_path, span_id="span-a", metadata={"has_match": False})
        record_consumption(tmp_path)
        with _ledger_path(tmp_path).open("a", encoding="utf-8") as handle:
            handle.write("{not json}\n")

        _make_route_span(tmp_path, span_id="span-b", metadata={"has_match": False})
        assert record_consumption(tmp_path) == 1
        assert {row["span_id"] for row in _rows(tmp_path)} == {"span-a", "span-b"}


# ---------------------------------------------------------------------------
# Bridge wiring
# ---------------------------------------------------------------------------


class TestBridgeWiring:
    def test_assembly_run_records_the_ledger(self, tmp_path: Path) -> None:
        span = _make_route_span(
            tmp_path,
            span_id="span-a",
            metadata={"has_match": True, "skill_id": "builtin/code-review"},
        )
        stats = bridge_entries([("Read", T0 + timedelta(minutes=1), "sess-1")], tmp_path)

        assert stats.consumption_rows == 1
        row = _row_for(tmp_path, span.id)
        assert row["selected"]["state"] == "yes"
        assert row["read"]["evidence"]["read_like_tool_calls"] == 1


# ---------------------------------------------------------------------------
# Read side / report
# ---------------------------------------------------------------------------


class TestReport:
    def test_missing_ledger_is_fail_soft_exit_zero(self, tmp_path: Path) -> None:
        result = consumption_report(tmp_path / "nope" / LEDGER_FILENAME)
        assert result.exit_code == 0
        assert result.fault is False
        assert result.report["ledger"]["exists"] is False
        assert result.report["rows"] == []
        assert result.report["counts"]["n_rows"] == 0
        assert result.report["segments"]["selected"] == {
            "yes": 0,
            "no": 0,
            "unknown": 0,
            "reasons": {},
        }

    def test_unreadable_ledger_is_a_fault(self, tmp_path: Path) -> None:
        ledger = _ledger_path(tmp_path)
        ledger.mkdir(parents=True)  # a directory cannot be read as a file
        result = consumption_report(ledger)
        assert result.exit_code == 3
        assert result.fault is True
        assert result.report["error"]["kind"] == "unreadable_ledger"

    def test_negative_limit_is_a_usage_error(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="--limit"):
            consumption_report(tmp_path / LEDGER_FILENAME, limit=-1)

    def test_bad_window_is_a_usage_error(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="--since"):
            consumption_report(tmp_path / LEDGER_FILENAME, since="not-a-date")

    def test_report_has_no_rates_or_scores(self, tmp_path: Path) -> None:
        _make_route_span(tmp_path, span_id="span-a", metadata={"has_match": True, "skill_id": "x"})
        record_consumption(tmp_path)
        report = consumption_report(_ledger_path(tmp_path)).report

        assert set(report) == {
            "schema",
            "schema_version",
            "generated_at",
            "ledger",
            "filters",
            "counts",
            "segments",
            "rows",
            "note",
        }
        blob = json.dumps(report).lower()
        for forbidden in ('"rate"', '"ratio"', '"score"', '"grade"', '"success"'):
            assert forbidden not in blob

    def test_segments_count_matched_rows_only(self, tmp_path: Path) -> None:
        _make_route_span(tmp_path, span_id="hit", metadata={"has_match": True, "skill_id": "x"})
        _make_route_span(
            tmp_path,
            span_id="miss",
            started=T0 + timedelta(minutes=1),
            metadata={"has_match": False},
        )
        _make_route_span(
            tmp_path, span_id="murky", started=T0 + timedelta(minutes=2), metadata={"skill_id": ""}
        )
        record_consumption(tmp_path)

        report = consumption_report(_ledger_path(tmp_path)).report
        assert report["segments"]["selected"] == {
            "yes": 1,
            "no": 1,
            "unknown": 1,
            "reasons": {R_MISSING_HAS_MATCH: 1},
        }
        assert report["segments"]["read"]["unknown"] == 3
        assert report["segments"]["read"]["reasons"] == {R_NO_HARNESS_RECEIPT: 3}
        assert report["segments"]["read"]["injection_attempted"] == 1
        assert report["segments"]["applicable"] == {"unknown": 3, "reasons": {R_NOT_OBSERVABLE: 3}}

    def test_filters_window_and_limit(self, tmp_path: Path) -> None:
        _make_route_span(
            tmp_path,
            span_id="old",
            started=T0,
            session="sess-a",
            metadata={"has_match": False},
        )
        _make_route_span(
            tmp_path,
            span_id="new",
            started=T0 + timedelta(hours=2),
            session="sess-b",
            metadata={"has_match": True, "skill_id": "builtin/code-review"},
        )
        record_consumption(tmp_path)
        ledger = _ledger_path(tmp_path)

        by_session = consumption_report(ledger, session_id="sess-b").report
        assert [row["span_id"] for row in by_session["rows"]] == ["new"]

        by_span = consumption_report(ledger, span_id="old").report
        assert [row["span_id"] for row in by_span["rows"]] == ["old"]
        assert by_span["counts"]["n_matched"] == 1

        windowed = consumption_report(ledger, since=(T0 + timedelta(hours=1)).isoformat()).report
        assert [row["span_id"] for row in windowed["rows"]] == ["new"]

        limited = consumption_report(ledger, limit=1).report
        assert limited["counts"]["n_matched"] == 2
        assert limited["counts"]["n_printed"] == 1
        assert [row["span_id"] for row in limited["rows"]] == ["old"]

    def test_window_drops_rows_without_a_timestamp(self, tmp_path: Path) -> None:
        _make_route_span(tmp_path, span_id="span-a", metadata={"has_match": False})
        record_consumption(tmp_path)
        ledger = _ledger_path(tmp_path)
        rows = _rows(tmp_path)
        rows[0]["route_started_at"] = None
        rows[0]["recorded_at"] = None
        ledger.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

        plain = consumption_report(ledger).report
        assert plain["counts"]["n_matched"] == 1

        windowed = consumption_report(ledger, since=T0.isoformat()).report
        assert windowed["counts"]["n_matched"] == 0
        assert windowed["counts"]["n_no_ts"] == 1

    def test_live_ledger_wins_over_rotation(self, tmp_path: Path) -> None:
        _make_route_span(tmp_path, span_id="span-a", metadata={"has_match": False})
        record_consumption(tmp_path)
        rotated = json.loads(_ledger_path(tmp_path).read_text(encoding="utf-8").strip())
        rotated["selected"]["state"] = "yes"
        _rotated_path(tmp_path).write_text(json.dumps(rotated) + "\n", encoding="utf-8")

        result = consumption_report(_ledger_path(tmp_path))
        assert result.report["counts"]["n_rows"] == 1
        assert result.report["counts"]["n_rotated_rows"] == 1
        assert result.report["rows"][0]["selected"]["state"] == "no"

    def test_corrupt_and_skipped_lines_are_counted(self, tmp_path: Path) -> None:
        _make_route_span(tmp_path, span_id="span-a", metadata={"has_match": False})
        record_consumption(tmp_path)
        with _ledger_path(tmp_path).open("a", encoding="utf-8") as handle:
            handle.write("{not json}\n")
            handle.write(json.dumps({"selected": {}}) + "\n")  # no span_id
        result = consumption_report(_ledger_path(tmp_path))
        assert result.report["counts"]["n_corrupt"] == 1
        assert result.report["counts"]["n_skipped"] == 1
        assert result.report["counts"]["n_rows"] == 1

    def test_report_is_deterministic(self, tmp_path: Path) -> None:
        for index in range(3):
            _make_route_span(
                tmp_path,
                span_id=f"span-{index}",
                started=T0 + timedelta(minutes=index),
                metadata={"has_match": index % 2 == 0, "skill_id": "x" if index % 2 == 0 else ""},
            )
        record_consumption(tmp_path)
        first = json.dumps(
            consumption_report(_ledger_path(tmp_path), now=T0).report, sort_keys=True
        )
        second = json.dumps(
            consumption_report(_ledger_path(tmp_path), now=T0).report, sort_keys=True
        )
        assert first == second

    def test_render_human_mentions_the_no_score_discipline(self, tmp_path: Path) -> None:
        _make_route_span(tmp_path, span_id="span-a", metadata={"has_match": False})
        record_consumption(tmp_path)
        rendered = render_human(consumption_report(_ledger_path(tmp_path)).report)
        assert "raw counts only" in rendered
        assert "selected:" in rendered
        assert "span=span-a" in rendered


# ---------------------------------------------------------------------------
# CLI contract
# ---------------------------------------------------------------------------


class TestCliContract:
    def test_consumption_json_exit_zero(self, tmp_path: Path) -> None:
        _make_route_span(
            tmp_path,
            span_id="span-a",
            metadata={"has_match": True, "skill_id": "builtin/code-review"},
        )
        record_consumption(tmp_path)
        result = runner.invoke(
            observe_cmd.app, ["consumption", "--ledger", str(_ledger_path(tmp_path)), "--json"]
        )
        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["schema"] == SCHEMA
        assert payload["rows"][0]["read"]["state"] is None

    def test_consumption_missing_ledger_is_soft(self, tmp_path: Path) -> None:
        result = runner.invoke(
            observe_cmd.app,
            ["consumption", "--ledger", str(tmp_path / "missing.jsonl"), "--json"],
        )
        assert result.exit_code == 0
        assert json.loads(result.stdout)["ledger"]["exists"] is False

    def test_consumption_usage_error_exits_two(self, tmp_path: Path) -> None:
        result = runner.invoke(
            observe_cmd.app,
            ["consumption", "--ledger", str(_ledger_path(tmp_path)), "--since", "nope"],
        )
        assert result.exit_code == 2

    def test_consumption_human_output(self, tmp_path: Path) -> None:
        _make_route_span(tmp_path, span_id="span-a", metadata={"has_match": False})
        record_consumption(tmp_path)
        result = runner.invoke(
            observe_cmd.app, ["consumption", "--ledger", str(_ledger_path(tmp_path))]
        )
        assert result.exit_code == 0
        assert "skill consumption ledger" in result.stdout


# ---------------------------------------------------------------------------
# Pure builder (no I/O)
# ---------------------------------------------------------------------------


class TestBuildRowPure:
    def test_build_row_keeps_the_envelope_on_every_segment(self) -> None:
        record = {
            "id": "span-1",
            "trace_id": "trace-1",
            "name": "route:q",
            "span_kind": "task",
            "task_id": "task-1",
            "session_id": "sess-1",
            "agent_id": "claude-code",
            "project_id": "default",
            "started_at": T0.isoformat(),
            "metadata": {"query": SENTINEL_QUERY, "has_match": False, "mode": "single"},
        }
        row = build_row(record, [], recorded_at="2026-09-21T10:00:00+00:00")
        for segment in ("selected", "read", "applicable", "executed", "accepted"):
            assert "state" in row[segment]
            assert "reason" in row[segment]
        assert row["selected"]["state"] == "no"
        assert SENTINEL_QUERY not in json.dumps(row)

    def test_build_row_tolerates_missing_fields(self) -> None:
        row = build_row(
            {"id": "span-1", "metadata": {}}, [], recorded_at="2026-09-21T10:00:00+00:00"
        )
        assert row["route_started_at"] is None
        assert row["session_id"] is None
        assert row["project_id"] == "default"
        assert row["selected"]["state"] is None
        assert row["selected"]["reason"] == R_MISSING_HAS_MATCH
