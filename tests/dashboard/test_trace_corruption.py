"""The dashboard must tolerate the same damaged records as plan queries."""

import json

import pytest

from vibesop.core.models import ExecutionPlan
from vibesop.dashboard import server


@pytest.mark.parametrize("bad", [b"\xff\n", b"[]\n", b"null\n", b'{"metadata": []}\n'])
def test_trace_lookup_skips_bad_rows_and_retains_exact_match(tmp_path, monkeypatch, bad):
    plan = ExecutionPlan(plan_id="trace-plan", metadata={"trace_id": "T-1"})
    line = json.dumps(plan.to_dict()).encode() + b"\n"
    (tmp_path / "execution_plans.jsonl").write_bytes(bad + line + bad)
    monkeypatch.setattr(server, "_spans_path", lambda root: root / "spans.jsonl")
    (tmp_path / "spans.jsonl").write_bytes(bad)
    assert server._trace_exists("T-1", tmp_path) is True
    assert server._trace_exists("T", tmp_path) is False
    assert server._trace_exists("missing", tmp_path) is False
