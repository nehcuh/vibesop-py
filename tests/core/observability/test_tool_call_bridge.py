"""Tests for the M12 M1 tool-call bridge + route outcome signals.

Covers the join strategies (session hit / time-window fallback / ambiguity
refusal / CLI-span exclusion), idempotent re-runs, the three outcome-signal
branches, and an end-to-end pass: spans.jsonl + tool_sequences.jsonl
fixtures → ``assemble_tool_sequences`` fan-out → bridged tool_call spans
consumed by ``SpanAggregator.get_pattern_sequences``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from vibesop.core.instinct.learner import InstinctLearner
from vibesop.core.instinct.tool_sequences import assemble_tool_sequences, sequences_path
from vibesop.core.observability.aggregator import SpanAggregator
from vibesop.core.observability.models import Span
from vibesop.core.observability.span_writer import SpanWriter
from vibesop.core.observability.task_id import derive_task_id
from vibesop.core.observability.tool_call_bridge import (
    OUTCOMES_FILENAME,
    BridgeStats,
    bridge_entries,
    run_bridge,
)

T0 = datetime(2026, 8, 20, 10, 0, 0, tzinfo=UTC)


def _spans_path(root: Path) -> Path:
    return root / ".vibe" / "observability" / "spans.jsonl"


def _outcomes_path(root: Path) -> Path:
    return root / ".vibe" / "observability" / OUTCOMES_FILENAME


def _route_span(
    root: Path,
    *,
    query: str = "how do I deploy the service",
    session: str | None = "sess-1",
    started: datetime = T0,
    has_match: bool | None = False,
    platform: str = "claude-code",
    mode: str = "single",
    source: str | None = None,
    span_id: str | None = None,
    trace_id: str | None = None,
    task_id: str | None = None,
) -> Span:
    meta: dict = {"query": query, "platform": platform, "mode": mode}
    if has_match is not None:
        meta["has_match"] = has_match
    if source is not None:
        meta["source"] = source
    span = Span(
        id=span_id or Span.new_id(),
        trace_id=trace_id or Span.new_trace_id(),
        name=f"route:{query[:40]}",
        span_kind="task",
        task_id=task_id if task_id is not None else derive_task_id(query),
        session_id=session,
        agent_id=platform,
        status="ok",
        started_at=started,
        ended_at=started,
        metadata=meta,
    )
    SpanWriter(storage_path=_spans_path(root)).write_span(span)
    return span


def _read_spans(root: Path) -> list[dict]:
    if not _spans_path(root).exists():
        return []
    records = []
    for line in _spans_path(root).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        meta = rec.get("metadata")
        if isinstance(meta, str):
            rec["metadata"] = json.loads(meta)
        records.append(rec)
    return records


def _tool_spans(root: Path) -> list[dict]:
    return [s for s in _read_spans(root) if s.get("span_kind") == "tool_call"]


def _read_outcomes(root: Path) -> list[dict]:
    path = _outcomes_path(root)
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _event(tool: str, ts: datetime | None, session: str | None):
    return (tool, ts, session)


class TestSessionJoin:
    def test_joins_latest_preceding_route_span_in_session(self, tmp_path: Path) -> None:
        first = _route_span(tmp_path, query="first question", started=T0, span_id="span-a")
        second = _route_span(
            tmp_path,
            query="second question",
            started=T0 + timedelta(minutes=10),
            span_id="span-b",
        )
        stats = bridge_entries([_event("Read", T0 + timedelta(minutes=15), "sess-1")], tmp_path)

        assert stats.bridged == 1
        assert stats.joined_session == 1
        tool_spans = _tool_spans(tmp_path)
        assert len(tool_spans) == 1
        bridged = tool_spans[0]
        assert bridged["parent_span_id"] == second.id
        assert bridged["trace_id"] == second.trace_id
        assert bridged["trace_id"] != first.trace_id
        assert bridged["name"] == "tool:Read"
        assert bridged["span_kind"] == "tool_call"
        assert bridged["session_id"] == "sess-1"
        assert bridged["task_id"] == second.task_id
        assert bridged["status"] == "ok"
        # privacy: tool name only in metadata
        assert set(bridged["metadata"]) <= {"tool", "source"}

    def test_event_before_session_spans_falls_to_window(self, tmp_path: Path) -> None:
        route = _route_span(tmp_path, started=T0, span_id="span-a")
        # Event predates the only route span of its session by 5 min, still
        # inside the join window → window fallback rescues the attachment.
        stats = bridge_entries([_event("Read", T0 - timedelta(minutes=5), "sess-1")], tmp_path)
        assert stats.joined_window == 1
        assert _tool_spans(tmp_path)[0]["parent_span_id"] == route.id


class TestWindowFallback:
    def test_sessionless_event_joins_unique_span_in_window(self, tmp_path: Path) -> None:
        route = _route_span(tmp_path, session="other-session", started=T0)
        stats = bridge_entries([_event("Bash", T0 + timedelta(minutes=20), None)], tmp_path)
        assert stats.joined_window == 1
        bridged = _tool_spans(tmp_path)[0]
        assert bridged["parent_span_id"] == route.id
        assert bridged["session_id"] == "other-session"  # inherited from route

    def test_outside_window_unmatched(self, tmp_path: Path) -> None:
        _route_span(tmp_path, started=T0)
        stats = bridge_entries([_event("Bash", T0 + timedelta(hours=2), None)], tmp_path)
        assert stats.unmatched == 1
        assert _tool_spans(tmp_path) == []

    def test_ambiguous_window_refused(self, tmp_path: Path) -> None:
        _route_span(tmp_path, session="s-a", started=T0, query="question one")
        _route_span(
            tmp_path,
            session="s-b",
            started=T0 + timedelta(minutes=5),
            query="question two",
        )
        stats = bridge_entries([_event("Bash", T0 + timedelta(minutes=10), None)], tmp_path)
        assert stats.ambiguous == 1
        assert stats.bridged == 0
        assert _tool_spans(tmp_path) == []


class TestCLIExclusion:
    def test_cli_route_spans_never_joined(self, tmp_path: Path) -> None:
        _route_span(
            tmp_path,
            platform="vibe-cli",
            source="cli",
            session="minted-per-invocation",
            started=T0,
        )
        # Session-less event in the same window: the CLI span must not be a
        # window candidate, so the event stays unmatched.
        stats = bridge_entries([_event("Bash", T0 + timedelta(minutes=5), None)], tmp_path)
        assert stats.unmatched == 1
        assert _tool_spans(tmp_path) == []

    def test_cli_session_id_not_matched(self, tmp_path: Path) -> None:
        _route_span(
            tmp_path,
            platform="vibe-cli",
            source="cli",
            session="minted-per-invocation",
            started=T0,
        )
        # Even an event literally carrying the CLI span's session id must not
        # attach (agent hook events can never legitimately carry it).
        stats = bridge_entries(
            [_event("Bash", T0 + timedelta(minutes=5), "minted-per-invocation")], tmp_path
        )
        assert stats.unmatched == 1
        assert _tool_spans(tmp_path) == []


class TestIdempotency:
    def test_repeated_entries_never_duplicate_spans(self, tmp_path: Path) -> None:
        _route_span(tmp_path, started=T0, span_id="span-a")
        entries = [_event("Read", T0 + timedelta(minutes=5), "sess-1")]

        first = bridge_entries(entries, tmp_path)
        second = bridge_entries(entries, tmp_path)

        assert first.bridged == 1
        assert second.bridged == 0
        assert second.dedup_skipped == 1
        assert len(_tool_spans(tmp_path)) == 1

    def test_run_bridge_manual_rerun_is_safe(self, tmp_path: Path) -> None:
        _route_span(tmp_path, started=T0, span_id="span-a")
        ts = (T0 + timedelta(minutes=5)).isoformat()
        sequences_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
        sequences_path(tmp_path).write_text(
            json.dumps({"tool": "Read", "ts": ts, "session": "sess-1"}) + "\n",
            encoding="utf-8",
        )
        assert run_bridge(tmp_path).bridged == 1
        rerun = run_bridge(tmp_path)
        assert rerun.bridged == 0
        assert rerun.dedup_skipped == 1
        assert len(_tool_spans(tmp_path)) == 1


class TestOutcomeSignals:
    def test_explicit_accept_is_strong_positive(self, tmp_path: Path) -> None:
        query = "how do I rotate the signing keys"
        miss = _route_span(tmp_path, query=query, started=T0, span_id="miss-1")
        pending = tmp_path / ".vibe" / "instincts" / "routing_pending.jsonl"
        pending.parent.mkdir(parents=True, exist_ok=True)
        pending.write_text(
            json.dumps(
                {
                    "id": "rp-1",
                    "query": query,
                    "skill_id": "deploy",
                    "kind": "no_match",
                    "status": "accepted",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        stats = bridge_entries([], tmp_path)
        outcomes = _read_outcomes(tmp_path)
        assert stats.outcomes_recorded == 1
        assert outcomes[0]["span_id"] == miss.id
        assert outcomes[0]["outcome"] == "strong_positive"
        assert outcomes[0]["reason"] == "explicit_accept"

    def test_reask_same_task_id_is_weak_negative(self, tmp_path: Path) -> None:
        query = "how do I rotate the signing keys"
        # now-relative: the newer span must stay inside SESSION_COMPLETE_HOURS
        # so "no evidence yet" — not expiry — is what keeps it undecided.
        now = datetime.now(UTC)
        older = _route_span(
            tmp_path, query=query, started=now - timedelta(hours=2), span_id="miss-old"
        )
        newer = _route_span(
            tmp_path, query=query, started=now - timedelta(hours=1), span_id="miss-new"
        )
        bridge_entries([], tmp_path)
        outcomes = {o["span_id"]: o for o in _read_outcomes(tmp_path)}
        assert outcomes[older.id]["outcome"] == "weak_negative"
        assert outcomes[older.id]["reason"] == "reask_same_task_id"
        # The newer span has no later re-ask and no completion evidence yet
        # (same session, same task, recent) → stays undecided.
        assert newer.id not in outcomes

    def test_session_continued_is_weak_positive(self, tmp_path: Path) -> None:
        miss = _route_span(tmp_path, query="question one", started=T0, span_id="miss-1")
        _route_span(
            tmp_path,
            query="a different question",
            started=T0 + timedelta(minutes=30),
            span_id="other-1",
        )
        bridge_entries([], tmp_path)
        outcomes = _read_outcomes(tmp_path)
        assert len(outcomes) == 1
        assert outcomes[0]["span_id"] == miss.id
        assert outcomes[0]["outcome"] == "weak_positive"
        assert outcomes[0]["reason"] == "session_continued_without_reask"

    def test_expired_session_is_weak_positive(self, tmp_path: Path) -> None:
        miss = _route_span(
            tmp_path, started=datetime.now(UTC) - timedelta(hours=48), span_id="miss-1"
        )
        bridge_entries([], tmp_path)
        outcomes = _read_outcomes(tmp_path)
        assert len(outcomes) == 1
        assert outcomes[0]["span_id"] == miss.id
        assert outcomes[0]["reason"] == "session_expired_without_reask"

    def test_unknown_and_not_intercepted_never_enter_miss_pool(self, tmp_path: Path) -> None:
        _route_span(tmp_path, has_match=None, started=T0)  # no has_match key
        _route_span(tmp_path, has_match=False, mode="not_intercepted", started=T0, query="继续")
        _route_span(tmp_path, has_match=True, started=T0, query="a matched question")
        stats = bridge_entries([], tmp_path)
        assert stats.outcomes_recorded == 0
        assert _read_outcomes(tmp_path) == []

    def test_recent_miss_without_evidence_stays_undecided(self, tmp_path: Path) -> None:
        _route_span(tmp_path, started=datetime.now(UTC) - timedelta(minutes=5))
        stats = bridge_entries([], tmp_path)
        assert stats.outcomes_recorded == 0

    def test_outcomes_not_duplicated_on_rerun(self, tmp_path: Path) -> None:
        _route_span(tmp_path, started=datetime.now(UTC) - timedelta(hours=48), span_id="miss-1")
        assert bridge_entries([], tmp_path).outcomes_recorded == 1
        assert bridge_entries([], tmp_path).outcomes_recorded == 0
        assert len(_read_outcomes(tmp_path)) == 1

    def test_corrupt_outcome_lines_skipped(self, tmp_path: Path) -> None:
        _route_span(tmp_path, started=datetime.now(UTC) - timedelta(hours=48), span_id="miss-1")
        path = _outcomes_path(tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{broken json\n", encoding="utf-8")
        stats = bridge_entries([], tmp_path)
        assert stats.outcomes_recorded == 1

    def _accepted_pending(self, root: Path, query: str) -> None:
        pending = root / ".vibe" / "instincts" / "routing_pending.jsonl"
        pending.parent.mkdir(parents=True, exist_ok=True)
        pending.write_text(
            json.dumps({"id": "rp-1", "query": query, "kind": "no_match", "status": "accepted"})
            + "\n",
            encoding="utf-8",
        )

    def test_short_query_prefix_is_not_strong_positive(self, tmp_path: Path) -> None:
        # gate16 claude nit: an untruncated short miss ("run tests") must NOT
        # prefix-match an accepted pending that merely extends it.
        miss = _route_span(
            tmp_path,
            query="run tests",
            started=datetime.now(UTC) - timedelta(hours=48),
            span_id="miss-1",
        )
        self._accepted_pending(tmp_path, "run tests with coverage in ci")
        bridge_entries([], tmp_path)
        outcomes = {o["span_id"]: o for o in _read_outcomes(tmp_path)}
        # No task_id equality → no strong signal; the miss decays to the
        # expiry weak positive instead of a false accept.
        assert outcomes[miss.id]["outcome"] == "weak_positive"

    def test_truncated_span_query_prefix_matches_accepted(self, tmp_path: Path) -> None:
        # The prefix fallback is legitimate exactly at the 200-char
        # truncation boundary: the span query IS a true prefix of the
        # pending query there.
        span_query = "a" * 200
        miss = _route_span(tmp_path, query=span_query, started=T0, span_id="miss-1")
        self._accepted_pending(tmp_path, span_query + " with coverage in ci")
        bridge_entries([], tmp_path)
        outcomes = {o["span_id"]: o for o in _read_outcomes(tmp_path)}
        assert outcomes[miss.id]["outcome"] == "strong_positive"

    def test_cli_miss_spans_never_get_outcomes(self, tmp_path: Path) -> None:
        # gate16 pi nit: per-invocation CLI sessions could only decay into
        # hollow expiry weak positives — exclude them like the join does.
        _route_span(
            tmp_path,
            platform="vibe-cli",
            source="cli",
            session="minted-per-invocation",
            started=datetime.now(UTC) - timedelta(hours=48),
            span_id="cli-miss",
        )
        stats = bridge_entries([], tmp_path)
        assert stats.outcomes_recorded == 0
        assert _read_outcomes(tmp_path) == []


class TestEndToEnd:
    def test_assemble_fans_out_to_bridge_and_aggregator_consumes(self, tmp_path: Path) -> None:
        now = datetime.now(UTC)
        route = _route_span(
            tmp_path,
            query="how do I deploy the service",
            session="sess-e2e",
            started=now - timedelta(minutes=10),
            span_id="route-e2e",
        )
        entries = [
            {
                "tool": tool,
                "ts": (now - timedelta(minutes=5 - i)).isoformat(),
                "session": "sess-e2e",
            }
            for i, tool in enumerate(["Read", "Edit", "Bash"])
        ]
        sequences_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
        sequences_path(tmp_path).write_text(
            "".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8"
        )

        learner = InstinctLearner(storage_path=tmp_path / ".vibe" / "instincts.jsonl")
        fed = assemble_tool_sequences(tmp_path, learner=learner)
        assert fed == 1  # InstinctLearner still fed via the same reader

        tool_spans = _tool_spans(tmp_path)
        assert len(tool_spans) == 3
        assert all(s["parent_span_id"] == route.id for s in tool_spans)
        assert all(s["trace_id"] == route.trace_id for s in tool_spans)

        # The pre-existing consumer reads the bridged spans back.
        agg = SpanAggregator(_spans_path(tmp_path))
        patterns = agg.get_pattern_sequences(min_occurrences=1)
        assert len(patterns) == 1
        assert patterns[0].steps == ["Read", "Edit", "Bash"]

        # Second assemble: watermark advanced → no duplicate bridge output.
        fed_again = assemble_tool_sequences(tmp_path, learner=learner)
        assert fed_again == 0
        assert len(_tool_spans(tmp_path)) == 3

    def test_bridge_failure_never_breaks_assembly(self, tmp_path: Path, monkeypatch) -> None:
        import vibesop.core.observability.tool_call_bridge as bridge_mod

        def _boom(entries, root):
            raise RuntimeError("bridge exploded")

        monkeypatch.setattr(bridge_mod, "bridge_entries", _boom)
        learner = InstinctLearner(storage_path=tmp_path / ".vibe" / "instincts.jsonl")
        sequences_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
        sequences_path(tmp_path).write_text(
            "".join(
                json.dumps({"tool": t, "ts": None, "session": "s"}) + "\n"
                for t in ("Read", "Edit", "Bash")
            ),
            encoding="utf-8",
        )
        # The fan-out in assemble swallows bridge failures by design…
        assert assemble_tool_sequences(tmp_path, learner=learner) == 1

    def test_bridge_entries_itself_never_raises(self, tmp_path: Path) -> None:
        # …and even called directly (broken spans file) it degrades quietly.
        spans_dir = tmp_path / ".vibe" / "observability"
        spans_dir.mkdir(parents=True)
        (spans_dir / "spans.jsonl").write_text("{broken\n", encoding="utf-8")
        stats = bridge_entries([_event("Read", T0, "s")], tmp_path)
        assert isinstance(stats, BridgeStats)
        assert stats.bridged == 0


class TestHookPathMissPredicate:
    """gate20 (pi NIT-1 = claude NIT-2) — the bridge now sees hook-path misses.

    Since gate20, ``agent_runtime.handle_query`` writes the router's real
    verdict into span metadata ``has_match`` (previously a mode-derived
    value that was never False on intercepted misses). Hook-path misses
    therefore enter ``_is_miss`` for the first time. Direction is correct:
    hook spans carry the real platform session_id (route-hook forwarding),
    so session/re-ask outcome evidence is meaningful — NOT the hollow
    weak-positive case the CLI exclusion guards.
    """

    def test_is_miss_accepts_hook_path_miss_span(self, tmp_path: Path) -> None:
        from vibesop.core.observability.tool_call_bridge import _as_route_span, _is_miss

        _route_span(
            tmp_path,
            has_match=False,
            mode="single",
            platform="claude-code",
            session="real-platform-session-uuid",
        )
        record = _read_spans(tmp_path)[0]
        rs = _as_route_span(record)

        assert rs.is_cli is False
        assert rs.session_id == "real-platform-session-uuid"
        assert rs.has_match is False
        assert _is_miss(rs) is True

    def test_hook_miss_produces_outcome_row(self, tmp_path: Path) -> None:
        """End-to-end: an expired hook-path miss lands in route_outcomes."""
        _route_span(
            tmp_path,
            has_match=False,
            started=datetime.now(UTC) - timedelta(hours=48),
            session="real-platform-session-uuid",
            span_id="hook-miss-1",
        )
        stats = bridge_entries([], tmp_path)
        assert stats.outcomes_recorded == 1
        outcomes = _read_outcomes(tmp_path)
        assert outcomes[0]["span_id"] == "hook-miss-1"
