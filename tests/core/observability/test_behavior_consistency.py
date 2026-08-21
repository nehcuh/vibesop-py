"""M3 — behavior_consistency unit tests (tool-sequence bigram-Jaccard gate).

Covers: join path (route span → child tool spans, composite
``(project_id, task_id)`` key, parent_span_id / trace_id OR-union),
started_at ordering, consecutive-same-tool collapsing, legacy
``tool: read_file`` name shape, group-key unification for parent-attributed
spans, the three-state verdict (consistent / divergent / unavailable),
the single-tool-sequence exclusion rule, and threshold validation.
Synthetic fixtures only — no cmspark data.
"""

from __future__ import annotations

import pytest

from vibesop.core.observability.behavior_consistency import (
    assess_behavior_consistency,
    tool_sequences_for_tasks,
)


def _route(
    rid: str,
    task_id: str,
    trace: str,
    ts: str = "2026-08-01T00:00:00+00:00",
    project_id: str | None = None,
) -> dict:
    span = {
        "id": rid,
        "name": "route:some query",
        "span_kind": "task",
        "task_id": task_id,
        "trace_id": trace,
        "started_at": ts,
    }
    if project_id is not None:
        span["project_id"] = project_id
    return span


def _tool(sid: str, trace: str | None, parent: str, name: str, ts: str) -> dict:
    """Tool span; ``name`` is the bare tool name (privacy: no params ever)."""
    span = {
        "id": sid,
        "name": f"tool:{name}",
        "span_kind": "tool_call",
        "parent_span_id": parent,
        "started_at": ts,
    }
    if trace is not None:
        span["trace_id"] = trace
    return span


def _keys(*task_ids: str, project_id: str = "default") -> list[tuple[str, str]]:
    """Composite keys matching the synthetic routes above (no project_id
    on the route span → "default", same convention as clustering)."""
    return [(project_id, tid) for tid in task_ids]


def _two_trace_spans(seq_a: list[str], seq_b: list[str]) -> list[dict]:
    """Two candidate traces (taskA1/taskA2), tools wired in sequence order."""
    spans = [_route("r1", "taskA1", "tr1"), _route("r2", "taskA2", "tr2")]
    for i, name in enumerate(seq_a):
        spans.append(_tool(f"a{i}", "tr1", "r1", name, f"2026-08-01T00:{i:02d}:00+00:00"))
    for i, name in enumerate(seq_b):
        spans.append(_tool(f"b{i}", "tr2", "r2", name, f"2026-08-02T00:{i:02d}:00+00:00"))
    return spans


class TestSequenceExtraction:
    def test_join_via_parent_and_orders_by_started_at(self) -> None:
        spans = [
            _route("r1", "taskA1", "tr1"),
            # Deliberately listed newest-first; extraction must sort.
            _tool("t2", "tr1", "r1", "Grep", "2026-08-01T00:02:00+00:00"),
            _tool("t1", "tr1", "r1", "Read", "2026-08-01T00:01:00+00:00"),
        ]
        assert tool_sequences_for_tasks(_keys("taskA1"), spans) == [["Read", "Grep"]]

    def test_consecutive_same_tool_collapsed_but_revisit_kept(self) -> None:
        """连续同名折叠(set 语义下 (X,X) 自环无区分度);Read→Grep→Read
        的非连续重复是真实回看信号,保留。"""
        spans = _two_trace_spans(["Read", "Read", "Read", "Grep", "Read"], ["Read", "Grep", "Read"])
        assert tool_sequences_for_tasks(_keys("taskA1", "taskA2"), spans) == [
            ["Read", "Grep", "Read"],
            ["Read", "Grep", "Read"],
        ]

    def test_non_candidate_trace_excluded(self) -> None:
        spans = _two_trace_spans(["Read", "Grep"], ["Read", "Grep"])
        spans.append(_route("r9", "taskZ", "tr9"))
        spans.append(_tool("z0", "tr9", "r9", "Bash", "2026-08-03T00:00:00+00:00"))
        assert len(tool_sequences_for_tasks(_keys("taskA1", "taskA2"), spans)) == 2

    def test_composite_key_excludes_other_project_same_task_id(self) -> None:
        """gate24 MAJOR-B: 同 task_id 的外项目 trace 不得混入 —— join 键
        是 (project_id, task_id) 复合,与聚类键口径一致。"""
        spans = _two_trace_spans(["Read", "Grep"], ["Read", "Grep"])
        # Same task_id as a candidate, but a DIFFERENT project.
        spans.append(_route("rx", "taskA1", "trx", project_id="other-proj"))
        spans.append(_tool("x0", "trx", "rx", "Bash", "2026-08-03T00:00:00+00:00"))
        spans.append(_tool("x1", "trx", "rx", "Write", "2026-08-03T00:01:00+00:00"))
        assert tool_sequences_for_tasks(_keys("taskA1", "taskA2"), spans) == [
            ["Read", "Grep"],
            ["Read", "Grep"],
        ]

    def test_legacy_tool_name_shape_normalized(self) -> None:
        spans = [
            _route("r1", "taskA1", "tr1"),
            {
                "id": "t1",
                "name": "tool: read_file",  # older producer shape (space + snake)
                "span_kind": "tool_call",
                "trace_id": "tr1",
                "parent_span_id": "r1",
                "started_at": "2026-08-01T00:01:00+00:00",
            },
            _tool("t2", "tr1", "r1", "Grep", "2026-08-01T00:02:00+00:00"),
        ]
        assert tool_sequences_for_tasks(_keys("taskA1"), spans) == [["read_file", "Grep"]]

    def test_orphan_tool_span_falls_back_to_trace_id(self) -> None:
        """parent_span_id 不指向任何候选 route 时,trace_id 匹配仍归属
        (OR-union, gate24 双路复审决定保留)。"""
        spans = [
            _route("r1", "taskA1", "tr1"),
            _tool("t1", "tr1", "missing-parent", "Read", "2026-08-01T00:01:00+00:00"),
            _tool("t2", "tr1", "missing-parent", "Grep", "2026-08-01T00:02:00+00:00"),
        ]
        assert tool_sequences_for_tasks(_keys("taskA1"), spans) == [["Read", "Grep"]]

    def test_parent_attributed_span_groups_by_parent_trace(self) -> None:
        """gate24 pi#4 + pi#9a: 经 parent 归属的 tool span 按 parent 链的
        trace 分组 —— 自身 trace_id 指向别处(嵌套子任务)或缺失,都
        不另立序列;parent route 自己也无 trace_id 时退回 parent span
        id 作分组键。"""
        spans = [
            _route("r1", "taskA1", "tr-parent"),
            # tool span's own trace is a nested sub-task trace — must still
            # group under the parent route's trace.
            _tool("t1", "tr-nested", "r1", "Read", "2026-08-01T00:01:00+00:00"),
            _tool("t2", "tr-nested", "r1", "Grep", "2026-08-01T00:02:00+00:00"),
            # trace_id missing entirely — still parent-attributed → same group.
            _tool("t3", None, "r1", "Bash", "2026-08-01T00:03:00+00:00"),
        ]
        # A candidate route with NO trace_id of its own: the group key
        # falls back to the parent span id.
        no_trace_route = _route("r9", "taskA9", "ignored")
        del no_trace_route["trace_id"]
        spans.append(no_trace_route)
        spans.append(_tool("t9", None, "r9", "Write", "2026-08-01T00:04:00+00:00"))

        from vibesop.core.observability.behavior_consistency import (
            tool_sequence_items_for_tasks,
        )

        items = tool_sequence_items_for_tasks(_keys("taskA1", "taskA9"), spans)
        assert sorted(items) == [
            ("r9", ["Write"]),
            ("tr-parent", ["Read", "Grep", "Bash"]),
        ]


class TestThreeStateVerdict:
    def test_consistent_when_identical_workflows(self) -> None:
        spans = _two_trace_spans(["Read", "Grep", "Read"], ["Read", "Grep", "Read"])
        state, score, n = assess_behavior_consistency(_keys("taskA1", "taskA2"), spans)
        assert state == "consistent"
        assert score == 1.0
        assert n == 2

    def test_divergent_when_data_sufficient_but_below_threshold(self) -> None:
        """第三态: 有数据且不达标 —— 不能诚实归入 unavailable。"""
        spans = _two_trace_spans(["Read", "Grep"], ["Bash", "Write"])
        state, score, n = assess_behavior_consistency(_keys("taskA1", "taskA2"), spans)
        assert state == "divergent"
        assert score == 0.0
        assert n == 2

    def test_unavailable_when_fewer_than_two_sequences(self) -> None:
        spans = [_route("r1", "taskA1", "tr1")]
        spans.append(_tool("t1", "tr1", "r1", "Read", "2026-08-01T00:01:00+00:00"))
        spans.append(_tool("t2", "tr1", "r1", "Grep", "2026-08-01T00:02:00+00:00"))
        state, score, n = assess_behavior_consistency(_keys("taskA1"), spans)
        assert (state, score, n) == ("unavailable", None, 1)

    def test_unavailable_when_no_tool_spans_at_all(self) -> None:
        spans = [_route("r1", "taskA1", "tr1"), _route("r2", "taskA2", "tr2")]
        state, score, n = assess_behavior_consistency(_keys("taskA1", "taskA2"), spans)
        assert (state, score, n) == ("unavailable", None, 0)

    def test_single_tool_sequences_carry_no_ordering_evidence(self) -> None:
        """单工具 trace 的 bigram 集为空,不参与成对计数 —— 两条单工具
        trace 仍是 unavailable,不是 consistent。"""
        spans = [
            _route("r1", "taskA1", "tr1"),
            _route("r2", "taskA2", "tr2"),
            _tool("t1", "tr1", "r1", "Read", "2026-08-01T00:01:00+00:00"),
            _tool("t2", "tr2", "r2", "Read", "2026-08-02T00:01:00+00:00"),
        ]
        state, score, n = assess_behavior_consistency(_keys("taskA1", "taskA2"), spans)
        assert (state, score, n) == ("unavailable", None, 0)

    def test_threshold_knob_flips_verdict(self) -> None:
        spans = _two_trace_spans(["Read", "Grep", "Bash"], ["Read", "Grep", "Write"])
        # bigrams {Read→Grep, Grep→Bash} vs {Read→Grep, Grep→Write} → 1/3
        state, score, _ = assess_behavior_consistency(_keys("taskA1", "taskA2"), spans)
        assert state == "divergent"
        assert score is not None and abs(score - 1 / 3) < 1e-9
        state_lo, _, _ = assess_behavior_consistency(
            _keys("taskA1", "taskA2"), spans, threshold=0.3
        )
        assert state_lo == "consistent"

    def test_threshold_out_of_range_rejected(self) -> None:
        """gate24 pi#6: 裸接受越界阈值会让 CLI 之外的调用静默错判。"""
        spans = _two_trace_spans(["Read", "Grep"], ["Read", "Grep"])
        with pytest.raises(ValueError, match="threshold"):
            assess_behavior_consistency(_keys("taskA1", "taskA2"), spans, threshold=1.5)
        with pytest.raises(ValueError, match="threshold"):
            assess_behavior_consistency(_keys("taskA1", "taskA2"), spans, threshold=-0.1)
