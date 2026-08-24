"""Tests for scripts/rebuild_route_outcomes.py (gate41 item 4).

Covers the offline remediation logic: S1/S2 dedup signatures (window
boundaries, size=2 guard, cross-platform preservation, "default" session
handling), S3 once-session exclusion counted over the WHOLE spans file,
corrupt-line tolerance (bridge read semantics), and the dry-run/--apply
gate including the 10:1 projection refusal. tool_call_bridge.py is only
imported, never modified — these tests pin that contract too (the rebuild
must route through ``_derive_outcomes``/``_derive_hit_outcomes``).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPT = ROOT / "scripts" / "rebuild_route_outcomes.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("rebuild_route_outcomes", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("rebuild_route_outcomes", module)
    spec.loader.exec_module(module)
    return module


rro = _load_module()

NOW = datetime(2026, 8, 24, 12, 0, 0, tzinfo=UTC)


def _rs(
    span_id: str,
    *,
    task_id: str | None = "task-1",
    session_id: str | None = "sess-a",
    agent_id: str | None = "claude-code",
    ts: datetime = NOW,
    is_cli: bool = False,
    has_match: bool | None = True,
    mode: str | None = "single",
    query: str = "do the thing",
) -> rro._RouteSpan:
    return rro._RouteSpan(
        id=span_id,
        trace_id=f"trace-{span_id}",
        session_id=session_id,
        task_id=task_id,
        agent_id=agent_id,
        project_id="default",
        started_at=ts,
        is_cli=is_cli,
        has_match=has_match,
        mode=mode,
        query=query,
    )


def _route_span_line(span_id: str, **kw) -> dict:
    """Serialize a route span as a spans.jsonl record (metadata as JSON string,
    matching SpanWriter's on-disk shape)."""
    span = _rs(span_id, **kw)
    platform = "vibe-cli" if span.is_cli else (span.agent_id or "claude-code")
    meta = {"query": span.query, "mode": span.mode, "platform": platform}
    if span.has_match is not None:
        meta["has_match"] = span.has_match
    return {
        "id": span.id,
        "trace_id": span.trace_id,
        "span_kind": "task",
        "name": f"route:{span.query[:80]}",
        "task_id": span.task_id,
        "session_id": span.session_id,
        "agent_id": span.agent_id,
        "started_at": span.started_at.isoformat(),
        "metadata": json.dumps(meta, ensure_ascii=False),
    }


def _write_jsonl(path: Path, records: list[dict | str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(record if isinstance(record, str) else json.dumps(record, ensure_ascii=False))
            f.write("\n")


# ---------------------------------------------------------------------------
# S1: cross-session claude×claude double-hook pairs
# ---------------------------------------------------------------------------


def test_s1_drops_later_of_cross_session_pair():
    spans = [
        _rs("first", session_id="sess-a", ts=NOW),
        _rs("second", session_id="sess-b", ts=NOW + timedelta(seconds=5)),
    ]
    assert rro._s1_duplicates(spans) == {"second": "first"}


def test_s1_window_is_inclusive_at_10s():
    pair = lambda dt: [  # noqa: E731
        _rs("first", session_id="sess-a", ts=NOW),
        _rs("second", session_id="sess-b", ts=NOW + timedelta(seconds=dt)),
    ]
    assert rro._s1_duplicates(pair(10.0)) == {"second": "first"}
    assert rro._s1_duplicates(pair(10.5)) == {}


def test_s1_size_guard_keeps_fanout_triple():
    spans = [
        _rs("a", session_id="sess-a", ts=NOW),
        _rs("b", session_id="sess-b", ts=NOW + timedelta(seconds=5)),
        _rs("c", session_id="sess-c", ts=NOW + timedelta(seconds=10)),
    ]
    assert rro._s1_duplicates(spans) == {}


def test_s1_keeps_cross_platform_pair():
    spans = [
        _rs("grok", agent_id="grok-build", session_id="sess-a", ts=NOW),
        _rs("claude", agent_id="claude-code", session_id="sess-b", ts=NOW + timedelta(seconds=1)),
    ]
    assert rro._s1_duplicates(spans) == {}


def test_s1_ignores_same_session_pair():
    spans = [
        _rs("first", session_id="sess-a", ts=NOW),
        _rs("second", session_id="sess-a", ts=NOW + timedelta(seconds=5)),
    ]
    assert rro._s1_duplicates(spans) == {}


def test_s1_ignores_missing_task_id():
    spans = [
        _rs("first", task_id=None, session_id="sess-a", ts=NOW),
        _rs("second", task_id=None, session_id="sess-b", ts=NOW + timedelta(seconds=5)),
    ]
    assert rro._s1_duplicates(spans) == {}


# ---------------------------------------------------------------------------
# S2: same-session claude×claude double-forward pairs
# ---------------------------------------------------------------------------


def test_s2_drops_same_session_pair():
    spans = [
        _rs("first", session_id="sess-a", ts=NOW),
        _rs("second", session_id="sess-a", ts=NOW + timedelta(seconds=14)),
    ]
    assert rro._s2_duplicates(spans, set()) == {"second": "first"}


def test_s2_window_is_exclusive_at_15s():
    spans = [
        _rs("first", session_id="sess-a", ts=NOW),
        _rs("second", session_id="sess-a", ts=NOW + timedelta(seconds=15)),
    ]
    assert rro._s2_duplicates(spans, set()) == {}


def test_s2_skips_default_session():
    spans = [
        _rs("first", session_id="default", ts=NOW),
        _rs("second", session_id="default", ts=NOW + timedelta(seconds=5)),
    ]
    assert rro._s2_duplicates(spans, set()) == {}


def test_s2_skips_already_s1_dropped():
    spans = [
        _rs("first", session_id="sess-a", ts=NOW),
        _rs("second", session_id="sess-a", ts=NOW + timedelta(seconds=5)),
        _rs("third", session_id="sess-a", ts=NOW + timedelta(seconds=9)),
    ]
    # "second" is pre-dropped by S1 and excluded from grouping; the survivors
    # (Δt=9s < 15s) still pair up on their own.
    assert rro._s2_duplicates(spans, {"second"}) == {"third": "first"}


# ---------------------------------------------------------------------------
# S3: once-session exclusion, counted over the whole spans file
# ---------------------------------------------------------------------------


def test_s3_counts_sessions_across_all_span_kinds(tmp_path):
    spans_file = tmp_path / "spans.jsonl"
    tool_span = {
        "id": "tool-1",
        "span_kind": "tool_call",
        "name": "tool:Bash",
        "session_id": "sess-with-tools",
    }
    _write_jsonl(spans_file, [_route_span_line("route-1", session_id="sess-with-tools"), tool_span])
    counts = rro._load_all_session_counts(spans_file)
    assert counts["sess-with-tools"] == 2
    assert not rro._is_once_session(_rs("route-1", session_id="sess-with-tools"), counts)


def test_s3_excludes_once_session_and_non_session_ids():
    counts = Counter({"sess-real": 2, "sess-once": 1, "default": 700})
    assert rro._is_once_session(_rs("x", session_id="sess-once"), counts)
    assert not rro._is_once_session(_rs("y", session_id="sess-real"), counts)
    # "default"/missing do not identify a session (grok NIT-9) → once-only.
    assert rro._is_once_session(_rs("z", session_id="default"), counts)
    assert rro._is_once_session(_rs("w", session_id=None), counts)


def test_loader_skips_corrupt_lines_and_metadata(tmp_path):
    spans_file = tmp_path / "spans.jsonl"
    _write_jsonl(
        spans_file,
        [
            "{not json at all",
            _route_span_line("good"),
            # metadata string that fails json.loads → bridge treats as {}.
            {**_route_span_line("corrupt-meta", session_id="sess-b"), "metadata": '"unterminated'},
        ],
    )
    spans = rro._load_route_spans(spans_file)
    assert [s.id for s in spans] == ["good", "corrupt-meta"]
    assert spans[1].has_match is None  # unknown, never enters hit/miss pools


# ---------------------------------------------------------------------------
# End-to-end: dry-run / --apply / refusal
# ---------------------------------------------------------------------------


def _phantom_pair_project(project: Path) -> Path:
    """Double-hook phantom pair (p1/p2, same task, different real sessions,
    Δt=5s) plus one later different-task span per session. After S1 dedup the
    survivor classifies as hit_session_moved_on instead of phantom reask."""
    t0 = datetime.now(UTC) - timedelta(hours=2)
    records = [
        _route_span_line("p1", task_id="task-1", session_id="sess-a", ts=t0),
        _route_span_line("p2", task_id="task-1", session_id="sess-b", ts=t0 + timedelta(seconds=5)),
        _route_span_line(
            "a2", task_id="task-2", session_id="sess-a", ts=t0 + timedelta(hours=1), query="next a"
        ),
        _route_span_line(
            "b2", task_id="task-3", session_id="sess-b", ts=t0 + timedelta(hours=1), query="next b"
        ),
    ]
    spans_file = project / ".vibe" / "observability" / "spans.jsonl"
    _write_jsonl(spans_file, records)
    outcomes_file = project / ".vibe" / "observability" / "route_outcomes.jsonl"
    phantom = {
        "span_id": "p1",
        "trace_id": "trace-p1",
        "task_id": "task-1",
        "session_id": "sess-a",
        "outcome": "weak_negative",
        "reason": "hit_reask_same_task_id",
        "side": "hit",
        "population": "hook",
        "recorded_at": t0.isoformat(),
    }
    _write_jsonl(outcomes_file, [phantom])
    return outcomes_file


def test_dry_run_does_not_touch_outcomes(tmp_path, capsys):
    outcomes_file = _phantom_pair_project(tmp_path)
    before = outcomes_file.read_bytes()
    assert rro.main(["--project-root", str(tmp_path)]) == 0
    assert outcomes_file.read_bytes() == before
    assert not (outcomes_file.parent / "route_outcomes.jsonl.bak").exists()
    out = capsys.readouterr().out
    assert "dry-run only" in out
    assert "hit_reask_same_task_id" in out  # old-vs-new reason table shown


def test_apply_rebuilds_and_backs_up(tmp_path):
    outcomes_file = _phantom_pair_project(tmp_path)
    before = outcomes_file.read_bytes()
    assert rro.main(["--project-root", str(tmp_path), "--apply"]) == 0

    backup = outcomes_file.parent / "route_outcomes.jsonl.bak"
    assert backup.read_bytes() == before

    rows = [json.loads(line) for line in outcomes_file.read_text().splitlines() if line.strip()]
    assert len(rows) == 1
    assert rows[0]["span_id"] == "p1"
    assert rows[0]["reason"] == "hit_session_moved_on"  # phantom reask repaired


def test_apply_refused_when_projection_over_threshold(tmp_path):
    # Same-session re-ask (Δt=20s escapes S2) with zero moved_on evidence:
    # projection is reask:0-moved_on = ∞ → --apply must refuse.
    t0 = datetime.now(UTC) - timedelta(hours=2)
    records = [
        _route_span_line("r1", task_id="task-r", session_id="sess-r", ts=t0),
        _route_span_line(
            "r2", task_id="task-r", session_id="sess-r", ts=t0 + timedelta(seconds=20)
        ),
    ]
    _write_jsonl(tmp_path / ".vibe" / "observability" / "spans.jsonl", records)
    outcomes_file = tmp_path / ".vibe" / "observability" / "route_outcomes.jsonl"
    _write_jsonl(outcomes_file, [{"span_id": "old", "reason": "hit_session_expired"}])
    before = outcomes_file.read_bytes()

    assert rro.main(["--project-root", str(tmp_path), "--apply"]) == 1
    assert outcomes_file.read_bytes() == before
    assert not (outcomes_file.parent / "route_outcomes.jsonl.bak").exists()


def test_s1_skips_non_identifying_session_ids():
    # gate41 claude NIT-1: "default"×real pairs are NOT proven double-hook
    # pairs — S1 must not drop the real-session leg (S3 would then take the
    # survivor and the prompt would lose both outcome rows).
    spans = [
        _rs("first", session_id="default", ts=NOW),
        _rs("second", session_id="sess-real", ts=NOW + timedelta(seconds=5)),
    ]
    assert rro._s1_duplicates(spans) == {}
    spans_missing = [
        _rs("first", session_id=None, ts=NOW),
        _rs("second", session_id="sess-real", ts=NOW + timedelta(seconds=5)),
    ]
    assert rro._s1_duplicates(spans_missing) == {}


def test_apply_refused_when_backup_exists(tmp_path, capsys):
    # gate41 claude NIT-3: a second --apply must not overwrite the first .bak.
    outcomes_file = _phantom_pair_project(tmp_path)
    assert rro.main(["--project-root", str(tmp_path), "--apply"]) == 0
    backup = outcomes_file.parent / "route_outcomes.jsonl.bak"
    backup_before = backup.read_bytes()
    assert rro.main(["--project-root", str(tmp_path), "--apply"]) == 1
    assert backup.read_bytes() == backup_before
    assert "backup already exists" in capsys.readouterr().out


def test_apply_refused_when_rebuild_empty(tmp_path, capsys):
    # gate41 pi N5: every route span once-session → S3 excludes all → the
    # rebuild is empty; --apply must not replace a non-empty file with it.
    t0 = datetime.now(UTC) - timedelta(hours=2)
    records = [
        _route_span_line("one", task_id="task-1", session_id="sess-once-1", ts=t0),
        _route_span_line("two", task_id="task-2", session_id="sess-once-2", ts=t0),
    ]
    _write_jsonl(tmp_path / ".vibe" / "observability" / "spans.jsonl", records)
    outcomes_file = tmp_path / ".vibe" / "observability" / "route_outcomes.jsonl"
    _write_jsonl(outcomes_file, [{"span_id": "old", "reason": "hit_session_expired"}])
    before = outcomes_file.read_bytes()

    assert rro.main(["--project-root", str(tmp_path), "--apply"]) == 1
    assert outcomes_file.read_bytes() == before
    assert "0 rows" in capsys.readouterr().out


def test_report_shows_hit_only_cut(tmp_path, capsys):
    # gate41 pi N4: `vibe skill outcomes` reads hit-side rows only, so the
    # projection is reported (and gated) on both pooled and hit-only cuts.
    _phantom_pair_project(tmp_path)
    assert rro.main(["--project-root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "(pooled)" in out
    assert "(hit-only)" in out
    assert "both cuts" in out


def test_dry_run_creates_no_state_and_copies_pending_readonly(tmp_path):
    # gate41 claude NIT-4: pin the "bridge state / pending untouched" contract
    # — the scratch-root rebuild must never create tool_call_bridge_state.json
    # in the real project nor modify routing_pending.jsonl.
    _phantom_pair_project(tmp_path)
    pending = tmp_path / ".vibe" / "instincts" / "routing_pending.jsonl"
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_text('{"kind": "miss", "status": "stable"}\n', encoding="utf-8")
    pending_before = pending.read_bytes()

    assert rro.main(["--project-root", str(tmp_path)]) == 0

    assert pending.read_bytes() == pending_before
    assert not (tmp_path / ".vibe" / "observability" / "tool_call_bridge_state.json").exists()
