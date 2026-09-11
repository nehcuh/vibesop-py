"""Unit tests for scripts/aggregate_nomatch.py (evo lane D2b).

All fixtures are tmp JSONL files — the real project spans file is never
touched. Span shapes mirror production spans.jsonl: metadata is a JSON
string written by SpanWriter, timestamps are aware ISO8601 strings.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "aggregate_nomatch.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("aggregate_nomatch", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["aggregate_nomatch"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def agg() -> ModuleType:
    return _load_module()


def _route_span(
    query: str = "q",
    *,
    started_at: str = "2026-09-01T10:00:00+00:00",
    metadata: dict[str, Any] | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    return {
        "id": f"span-{query}",
        "name": name if name is not None else f"route:{query}",
        "span_kind": "task",
        "started_at": started_at,
        "metadata": json.dumps(metadata if metadata is not None else {"query": query}),
    }


def _write_spans(
    tmp_path: Path, spans: list[dict[str, Any]], extra_lines: list[str] | None = None
) -> Path:
    path = tmp_path / "spans.jsonl"
    lines = [json.dumps(s, ensure_ascii=False) for s in spans]
    if extra_lines:
        lines.extend(extra_lines)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _run_json(agg: ModuleType, spans: Path, *extra: str) -> tuple[int, dict[str, Any], str]:
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        code = agg.main(["--spans", str(spans), "--json", *extra])
    return code, json.loads(buf.getvalue()), buf.getvalue()


def test_missing_file_fail_soft(
    agg: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = agg.main(["--spans", str(tmp_path / "nope.jsonl"), "--json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out == {"error": "missing_spans", "n_route": 0}


def test_missing_file_human_line_exits_zero(
    agg: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = agg.main(["--spans", str(tmp_path / "nope.jsonl")])
    out = capsys.readouterr().out
    assert code == 0
    assert "missing_spans" in out
    assert "n_route=0" in out


def test_counts_rate_and_ci(agg: ModuleType, tmp_path: Path) -> None:
    spans = [
        _route_span(
            "hit1", metadata={"has_match": True, "skill_id": "builtin/x", "layer": "builtin"}
        ),
        _route_span(
            "hit2", metadata={"has_match": True, "skill_id": "builtin/y", "layer": "ai_triage"}
        ),
        _route_span("miss1", metadata={"has_match": False, "skill_id": "", "layer": "keyword"}),
        _route_span("miss2", metadata={"has_match": False, "skill_id": ""}),
        _route_span("unknown", metadata={"mode": "slash_command"}),
        {"id": "tool", "name": "tool_call:Read", "span_kind": "tool"},
    ]
    path = _write_spans(tmp_path, spans)
    code, report, _ = _run_json(agg, path)
    assert code == 0
    assert report["n_route"] == 5  # tool span excluded
    assert report["n_hit"] == 2
    assert report["n_nomatch"] == 2
    assert report["n_unscored"] == 1
    assert report["n_scored"] == 4
    assert report["rate"] == round(2 / 5, 4)
    assert report["rate_scored"] == 0.5
    # Wilson interval brackets the reported rate over n_route
    assert report["wilson95_low"] <= report["rate"] <= report["wilson95_high"]
    assert report["wilson95_low"] >= 0.0 and report["wilson95_high"] <= 1.0
    # miss1 carries layer=keyword; miss2 has no layer -> unknown bucket
    assert report["nomatch_by_layer"] == {"keyword": 1, "unknown": 1}


def test_metadata_accepts_dict_and_string_forms(agg: ModuleType, tmp_path: Path) -> None:
    dict_span = _route_span("dictmeta", metadata={"has_match": True, "skill_id": "s"})
    dict_span["metadata"] = {"has_match": True, "skill_id": "s"}
    str_span = _route_span("strmeta", metadata={"has_match": False, "skill_id": ""})
    path = _write_spans(tmp_path, [dict_span, str_span])
    _, report, _ = _run_json(agg, path)
    assert (report["n_hit"], report["n_nomatch"]) == (1, 1)


def test_corrupt_lines_skipped(agg: ModuleType, tmp_path: Path) -> None:
    spans = [_route_span("hit", metadata={"has_match": True})]
    path = _write_spans(
        tmp_path,
        spans,
        extra_lines=["{not json", "", json.dumps(["a", "list"])],
    )
    _, report, _ = _run_json(agg, path)
    assert report["n_route"] == 1
    assert report["n_corrupt"] == 2


def test_field_precedence(agg: ModuleType, tmp_path: Path) -> None:
    """has_match > skill_id/primary > layer fallback_llm; nothing -> unscored."""
    spans = [
        # has_match wins even when skill_id disagrees (producer contract)
        _route_span("a", metadata={"has_match": True, "skill_id": ""}),
        _route_span("b", metadata={"has_match": False, "skill_id": "builtin/x"}),
        # no has_match: empty primary -> no-match (legacy key "primary" too)
        _route_span("c", metadata={"skill_id": ""}),
        _route_span("d", metadata={"primary": ""}),
        # no has_match: non-empty primary -> hit
        _route_span("e", metadata={"skill_id": "builtin/y"}),
        # no has_match/primary: fallback_llm layer -> no-match; other layer -> hit
        _route_span("f", metadata={"layer": "fallback_llm"}),
        _route_span("g", metadata={"layer": "semantic"}),
        # nothing readable -> unscored
        _route_span("h", metadata={"mode": "not_intercepted"}),
    ]
    path = _write_spans(tmp_path, spans)
    _, report, _ = _run_json(agg, path)
    assert report["n_nomatch"] == 4  # b, c, d, f
    assert report["n_hit"] == 3  # a, e, g
    assert report["n_unscored"] == 1  # h
    assert report["n_route"] == 8
    assert report["nomatch_by_layer"] == {"fallback_llm": 1, "unknown": 3}


def test_since_window_filters_and_drops_no_ts(agg: ModuleType, tmp_path: Path) -> None:
    spans = [
        _route_span("old", started_at="2026-08-01T00:00:00+00:00", metadata={"has_match": True}),
        _route_span("new", started_at="2026-09-10T00:00:00+00:00", metadata={"has_match": False}),
        _route_span("legacy-ts", started_at=""),
        _route_span("legacy-ts2"),
    ]
    # legacy timestamp fallback: inside the window via the legacy field
    spans[2]["timestamp"] = "2026-09-11T00:00:00+00:00"
    # no timestamp at all: cannot be proven inside the window -> n_no_ts
    del spans[3]["started_at"]
    path = _write_spans(tmp_path, spans)
    code, report, _ = _run_json(agg, path, "--since", "2026-09-01T00:00:00")
    assert code == 0
    assert report["n_route"] == 2  # new + legacy-ts; old filtered, no-ts dropped
    assert report["n_no_ts"] == 1
    assert report["n_nomatch"] == 1  # "new"
    assert report["n_hit"] == 0
    assert report["n_unscored"] == 1  # "legacy-ts" carries no scoring fields


def test_since_naive_treated_as_utc(agg: ModuleType, tmp_path: Path) -> None:
    # span at 2026-09-01T02:00+00:00 vs naive --since 2026-09-01T00:00 (=UTC)
    spans = [
        _route_span("in", started_at="2026-09-01T02:00:00+00:00", metadata={"has_match": True}),
        _route_span("out", started_at="2026-08-31T22:00:00+00:00", metadata={"has_match": True}),
    ]
    path = _write_spans(tmp_path, spans)
    code, report, _ = _run_json(agg, path, "--since", "2026-09-01T00:00:00")
    assert code == 0
    assert report["n_route"] == 1


def test_invalid_since_is_arg_error(agg: ModuleType, tmp_path: Path) -> None:
    path = _write_spans(tmp_path, [_route_span("x")])
    with pytest.raises(SystemExit) as excinfo:
        agg.main(["--spans", str(path), "--json", "--since", "not-a-date"])
    assert excinfo.value.code == 2


def test_all_unscored_no_division_error(agg: ModuleType, tmp_path: Path) -> None:
    path = _write_spans(tmp_path, [_route_span("u1"), _route_span("u2")])
    code, report, _ = _run_json(agg, path)
    assert code == 0
    assert report["n_route"] == 2
    assert report["n_unscored"] == 2
    assert report["rate"] == 0.0
    # k=0 with n>0: lower bound is exactly 0, upper stays positive
    assert report["wilson95_low"] == 0.0
    assert report["wilson95_high"] > 0.0


def test_empty_file(agg: ModuleType, tmp_path: Path) -> None:
    path = tmp_path / "spans.jsonl"
    path.write_text("", encoding="utf-8")
    _, report, _ = _run_json(agg, path)
    assert report["n_route"] == 0
    assert report["rate"] == 0.0


def test_human_default_one_line(
    agg: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    spans = [
        _route_span("hit", metadata={"has_match": True}),
        _route_span("miss", metadata={"has_match": False, "layer": "fallback_llm"}),
    ]
    path = _write_spans(tmp_path, spans)
    code = agg.main(["--spans", str(path)])
    lines = capsys.readouterr().out.strip().splitlines()
    assert code == 0
    assert len(lines) == 1
    assert "n_route=2" in lines[0]
    assert "n_nomatch=1" in lines[0]
    assert "rate=0.5" in lines[0]


def test_wilson_interval_known_values(agg: ModuleType) -> None:
    # k=0: interval starts at 0; k=n: interval ends at 1
    lo, hi = agg.wilson_interval(0, 10)
    assert lo == 0.0 and hi > 0.0
    lo, hi = agg.wilson_interval(10, 10)
    assert lo < 1.0 and hi == 1.0
    lo, hi = agg.wilson_interval(7, 10)
    # Reference values for the Wilson 95% interval of 0.7 with n=10
    # (z=1.95996, hand-checked against the closed-form formula):
    assert lo == pytest.approx(0.3968, abs=1e-3)
    assert hi == pytest.approx(0.8922, abs=1e-3)
    assert agg.wilson_interval(0, 0) == (0.0, 0.0)


def test_directory_instead_of_file_is_fail_soft(agg: ModuleType, tmp_path: Path) -> None:
    """A directory path is an OSError on open, not a missing file — stays exit 0."""
    code, report, _ = _run_json(agg, tmp_path)
    assert code == 0
    assert report == {"error": "unreadable_spans", "n_route": 0}
