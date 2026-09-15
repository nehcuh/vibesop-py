"""Focused tests for the 8.5 routing observer.

Covers the ``vibesop.observe.routing`` v1 contract: no-match scoring reuse,
scoring-coverage and min-sample gates (false-green protection), decision-source
layer classification, optional near-miss provenance, window/project filters,
fail-closed payload handling, exit codes, deterministic JSON, and the
``scripts/aggregate_nomatch.py`` compatibility facade.

Fixtures are tmp JSONL trees built from real ``Span.to_dict()`` payloads (and
the SpanWriter JSON-string ``metadata`` form) wherever possible.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from typer.testing import CliRunner

from vibesop.cli.commands import observe_cmd
from vibesop.core.observability.models import Span
from vibesop.core.observability.route_observe import (
    CRITICAL,
    HEALTHY,
    INSUFFICIENT,
    NOT_REQUESTED,
    WARN,
    ObserveThresholds,
    aggregate,
    observe_routing,
    render_human,
    wilson_interval,
)

ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = ROOT / "scripts" / "aggregate_nomatch.py"

#: Fixed observer clock for eval-provenance tests. Payloads default to one
#: hour before it so they are fresh under the 24h default max age.
_NOW = datetime(2026, 9, 15, 9, 0, tzinfo=UTC)
_EVAL_GENERATED_AT = "2026-09-15T08:00:00+00:00"


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _route_span(
    query: str = "q",
    *,
    metadata: dict[str, Any] | None = None,
    started_at: datetime | None = None,
    project_id: str = "vibesop-py",
    name: str | None = None,
) -> dict[str, Any]:
    """A real production payload via ``Span.to_dict()``."""
    span = Span(
        id=f"span-{query}",
        trace_id="trace-1",
        name=name if name is not None else f"route:{query}",
        span_kind="task",
        started_at=started_at or datetime(2026, 9, 5, 12, 0, tzinfo=UTC),
        project_id=project_id,
        metadata=metadata if metadata is not None else {"has_match": True, "layer": "keyword"},
    )
    return span.to_dict()


def _writer_span(record: dict[str, Any]) -> dict[str, Any]:
    """SpanWriter form: ``metadata`` serialised to a JSON string."""
    out = dict(record)
    out["metadata"] = json.dumps(out["metadata"], ensure_ascii=False)
    return out


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> Path:
    lines = [json.dumps(r, ensure_ascii=False) for r in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return path


def _scored_run(
    n_hit: int, n_nomatch: int, *, layer: str = "keyword", n_unscored: int = 0
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for i in range(n_hit):
        records.append(_route_span(f"hit{i}", metadata={"has_match": True, "layer": layer}))
    for i in range(n_nomatch):
        records.append(
            _route_span(f"miss{i}", metadata={"has_match": False, "layer": "fallback_llm"})
        )
    for i in range(n_unscored):
        records.append(_route_span(f"un{i}", metadata={"mode": "not_intercepted"}))
    return records


def _eval_payload(
    *,
    n_near_miss: int = 20,
    over_inject: int = 3,
    n_neg: int = 50,
    dataset: str = "tests/benchmark/routing_eval.yaml",
    hermetic: bool = True,
    generated_at: str = _EVAL_GENERATED_AT,
) -> dict[str, Any]:
    return {
        "n_near_miss": n_near_miss,
        "near_miss_over_inject": over_inject,
        "n_neg": n_neg,
        "dataset": dataset,
        "hermetic": hermetic,
        "generated_at": generated_at,
    }


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("aggregate_nomatch", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["aggregate_nomatch"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


# ---------------------------------------------------------------------------
# Compat facade
# ---------------------------------------------------------------------------


def test_compat_script_delegates_to_library(tmp_path: Path) -> None:
    """The 8.4.0 script is a thin shim: same JSON as the library aggregate."""
    path = _write_jsonl(tmp_path / "spans.jsonl", _scored_run(6, 4))
    module = _load_script()
    assert module.wilson_interval is wilson_interval
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        code = module.main(["--spans", str(path), "--json"])
    assert code == 0
    assert json.loads(buf.getvalue()) == aggregate(path)


def test_compat_script_missing_and_directory_fail_soft(tmp_path: Path) -> None:
    module = _load_script()
    assert module.aggregate(tmp_path / "nope.jsonl") == {"error": "missing_spans", "n_route": 0}
    assert module.aggregate(tmp_path) == {"error": "unreadable_spans", "n_route": 0}


def test_writer_string_metadata_form_scores(tmp_path: Path) -> None:
    """SpanWriter serialises metadata to a JSON string; both forms score."""
    records = [
        _writer_span(_route_span("hit", metadata={"has_match": True, "layer": "keyword"})),
        _writer_span(_route_span("miss", metadata={"has_match": False, "layer": "fallback_llm"})),
    ]
    path = _write_jsonl(tmp_path / "spans.jsonl", records)
    result = observe_routing(path)
    counts = result.report["counts"]
    assert counts["n_hit"] == 1
    assert counts["n_nomatch"] == 1
    assert counts["n_unparsed_metadata"] == 0


def test_until_uses_legacy_timestamp_fallback(tmp_path: Path) -> None:
    record = _route_span("legacy")
    del record["started_at"]
    record["timestamp"] = "2026-09-05T12:00:00+00:00"
    path = _write_jsonl(tmp_path / "spans.jsonl", [record])
    result = observe_routing(path, until="2026-09-06T00:00:00")
    assert result.report["counts"]["n_route"] == 1


# ---------------------------------------------------------------------------
# Golden schema
# ---------------------------------------------------------------------------


def test_golden_schema_keys_and_types(tmp_path: Path) -> None:
    path = _write_jsonl(tmp_path / "spans.jsonl", _scored_run(60, 40))
    result = observe_routing(path, now=datetime(2026, 9, 15, 9, 0, tzinfo=UTC))
    report = result.report
    assert report["schema"] == "vibesop.observe.routing"
    assert report["schema_version"] == 1
    assert report["generated_at"] == "2026-09-15T09:00:00+00:00"
    assert set(report) == {
        "schema",
        "schema_version",
        "generated_at",
        "overall_state",
        "exit_code",
        "outcome",
        "window",
        "filters",
        "inputs",
        "counts",
        "coverage",
        "metrics",
        "registry",
        "thresholds",
        "recommendations",
    }
    assert set(report["metrics"]) == {"no_match", "near_miss", "decision_source"}
    assert set(report["counts"]) == {
        "n_route",
        "n_hit",
        "n_nomatch",
        "n_scored",
        "n_unscored",
        "n_no_ts",
        "n_corrupt",
        "n_unparsed_metadata",
    }
    assert report["registry"] is None
    assert report["metrics"]["near_miss"]["state"] == NOT_REQUESTED
    assert list(report["metrics"]["decision_source"]["by_layer"]) == sorted(
        report["metrics"]["decision_source"]["by_layer"]
    )
    assert all(isinstance(rec, str) for rec in report["recommendations"])
    # Forbidden span-metadata keys must never leak to the report top level.
    for forbidden in ("has_match", "mode", "query", "confidence", "category"):
        assert forbidden not in report
        assert forbidden not in report["metrics"]


# ---------------------------------------------------------------------------
# Missing / required / unreadable
# ---------------------------------------------------------------------------


def test_missing_spans_is_insufficient_exit_4(tmp_path: Path) -> None:
    result = observe_routing(tmp_path / "nope.jsonl")
    assert result.exit_code == 4
    assert result.report["overall_state"] == INSUFFICIENT
    assert result.report["error"]["kind"] == "missing_input"
    assert result.report["metrics"]["no_match"]["reason"] == "missing_input"
    assert result.report["metrics"]["no_match"]["rate"] is None


def test_require_inputs_escalates_missing_to_fault_exit_3(tmp_path: Path) -> None:
    result = observe_routing(tmp_path / "nope.jsonl", require_inputs=True)
    assert result.exit_code == 3
    assert result.fault is True
    assert result.report["error"]["kind"] == "missing_input"


def test_directory_spans_is_fault_exit_3(tmp_path: Path) -> None:
    result = observe_routing(tmp_path)
    assert result.exit_code == 3
    assert result.fault is True
    assert result.report["error"]["kind"] == "unreadable_input"


# ---------------------------------------------------------------------------
# Corrupt / strict payloads
# ---------------------------------------------------------------------------


def test_corrupt_line_floors_healthy_to_warn(tmp_path: Path) -> None:
    path = tmp_path / "spans.jsonl"
    body = "\n".join(json.dumps(r, ensure_ascii=False) for r in _scored_run(60, 40))
    path.write_bytes(body.encode("utf-8") + b"\n{not json\n")
    result = observe_routing(path)
    assert result.report["counts"]["n_corrupt"] == 1
    assert result.report["overall_state"] == WARN
    assert result.exit_code == 1


def test_corrupt_upgrades_insufficient_to_warn(tmp_path: Path) -> None:
    """Corrupt lines floor the rollup at warn even when the sample is thin."""
    line = json.dumps(_route_span("hit", metadata={"has_match": True, "layer": "keyword"}))
    path = tmp_path / "spans.jsonl"
    path.write_bytes(line.encode("utf-8") + b"\n{not json\n")
    result = observe_routing(path)
    assert result.report["metrics"]["no_match"]["state"] == INSUFFICIENT
    assert result.report["overall_state"] == WARN
    assert result.exit_code == 1


def test_strict_payloads_turns_corrupt_into_fault(tmp_path: Path) -> None:
    path = tmp_path / "spans.jsonl"
    body = "\n".join(json.dumps(r, ensure_ascii=False) for r in _scored_run(60, 40))
    path.write_bytes(body.encode("utf-8") + b"\n{not json\n")
    result = observe_routing(path, strict_payloads=True)
    assert result.exit_code == 3
    assert result.report["error"]["kind"] == "payload_rejected"


def test_invalid_utf8_and_bom_and_crlf_are_handled(tmp_path: Path) -> None:
    good = json.dumps(_route_span("hit", metadata={"has_match": True, "layer": "keyword"}))
    good2 = json.dumps(_route_span("miss", metadata={"has_match": False, "layer": "fallback_llm"}))
    path = tmp_path / "spans.jsonl"
    path.write_bytes(
        b"\xef\xbb\xbf"
        + good.encode("utf-8")
        + b"\r\n\xff\xfe truncated\r\n"
        + good2.encode("utf-8")
        + b"\r\n"
    )
    result = observe_routing(path)
    counts = result.report["counts"]
    assert counts["n_route"] == 2
    assert counts["n_hit"] == 1
    assert counts["n_nomatch"] == 1
    assert counts["n_corrupt"] == 1


def test_unparsed_metadata_prevents_green(tmp_path: Path) -> None:
    records = _scored_run(60, 40)
    bad = _route_span("bad", metadata={"has_match": True})
    bad["metadata"] = "not valid json"
    records.append(bad)
    path = _write_jsonl(tmp_path / "spans.jsonl", records)
    result = observe_routing(path)
    assert result.report["counts"]["n_unparsed_metadata"] == 1
    assert result.report["metrics"]["no_match"]["state"] == INSUFFICIENT
    assert result.report["metrics"]["no_match"]["reason"] == "unparsed_metadata"
    assert result.exit_code == 4


# ---------------------------------------------------------------------------
# Coverage false-green / min boundaries
# ---------------------------------------------------------------------------


def test_coverage_gate_blocks_5000_30_false_green(tmp_path: Path) -> None:
    records = _scored_run(25, 5, n_unscored=4970)
    path = _write_jsonl(tmp_path / "spans.jsonl", records)
    result = observe_routing(path)
    counts = result.report["counts"]
    assert counts["n_route"] == 5000
    assert counts["n_scored"] == 30
    assert result.report["coverage"]["scoring_coverage"] == round(30 / 5000, 4)
    assert result.report["metrics"]["no_match"]["state"] == INSUFFICIENT
    assert result.report["metrics"]["no_match"]["reason"] == "below_min_coverage"
    assert result.exit_code == 4


def test_min_samples_boundary(tmp_path: Path) -> None:
    ok = _write_jsonl(tmp_path / "ok.jsonl", _scored_run(70, 30))
    thresholds = ObserveThresholds(min_samples=100, min_coverage=0.0)
    assert (
        observe_routing(ok, thresholds=thresholds).report["metrics"]["no_match"]["state"] == HEALTHY
    )

    low = _write_jsonl(tmp_path / "low.jsonl", _scored_run(60, 39))
    result = observe_routing(low, thresholds=thresholds)
    assert result.report["metrics"]["no_match"]["state"] == INSUFFICIENT
    assert result.report["metrics"]["no_match"]["reason"] == "below_min_samples"


def test_min_coverage_boundary_inclusive(tmp_path: Path) -> None:
    exact = _write_jsonl(tmp_path / "exact.jsonl", _scored_run(60, 20, n_unscored=20))
    thresholds = ObserveThresholds(min_samples=10, min_coverage=0.8)
    result = observe_routing(exact, thresholds=thresholds)
    assert result.report["coverage"]["scoring_coverage"] == 0.8
    assert result.report["coverage"]["state"] == HEALTHY
    assert result.report["metrics"]["no_match"]["state"] == HEALTHY

    below = _write_jsonl(tmp_path / "below.jsonl", _scored_run(60, 19, n_unscored=21))
    result2 = observe_routing(below, thresholds=thresholds)
    assert result2.report["coverage"]["scoring_coverage"] == 0.79
    assert result2.report["metrics"]["no_match"]["state"] == INSUFFICIENT
    assert result2.report["metrics"]["no_match"]["reason"] == "below_min_coverage"


# ---------------------------------------------------------------------------
# Threshold boundaries (raw, inclusive)
# ---------------------------------------------------------------------------


def test_no_match_threshold_boundaries(tmp_path: Path) -> None:
    thresholds = ObserveThresholds(min_samples=100, min_coverage=0.0)
    warn_path = _write_jsonl(tmp_path / "warn.jsonl", _scored_run(60, 40))
    assert (
        observe_routing(warn_path, thresholds=thresholds).report["metrics"]["no_match"]["state"]
        == WARN
    )
    crit_path = _write_jsonl(tmp_path / "crit.jsonl", _scored_run(40, 60))
    assert (
        observe_routing(crit_path, thresholds=thresholds).report["metrics"]["no_match"]["state"]
        == CRITICAL
    )
    assert observe_routing(crit_path, thresholds=thresholds).exit_code == 3


def test_unknown_layer_threshold_boundaries(tmp_path: Path) -> None:
    thresholds = ObserveThresholds(
        min_samples=100, min_coverage=0.0, unknown_warn=0.05, unknown_crit=0.10
    )
    records: list[dict[str, Any]] = []
    for i in range(95):
        records.append(_route_span(f"hit{i}", metadata={"has_match": True, "layer": "keyword"}))
    for i in range(5):
        records.append(_route_span(f"old{i}", metadata={"has_match": True, "layer": "semantic"}))
    path = _write_jsonl(tmp_path / "spans.jsonl", records)
    result = observe_routing(path, thresholds=thresholds)
    ds = result.report["metrics"]["decision_source"]
    assert ds["unknown_share"] == 0.05
    assert ds["state"] == WARN
    assert ds["by_layer"]["unknown"] == 5
    assert ds["non_enum_layers"] == {"semantic": 5}
    assert ds["layer_coverage"] == 0.95

    records2 = (
        records[:90]
        + records[95:]
        + [
            _route_span(f"old2-{i}", metadata={"has_match": True, "layer": "builtin"})
            for i in range(5)
        ]
    )
    path2 = _write_jsonl(tmp_path / "spans2.jsonl", records2)
    result2 = observe_routing(path2, thresholds=thresholds)
    ds2 = result2.report["metrics"]["decision_source"]
    assert ds2["unknown_share"] == 0.10
    assert ds2["state"] == CRITICAL


def test_decision_source_not_gated_without_evidence(tmp_path: Path) -> None:
    """Unknown layers below min_samples stay insufficient, not warn/critical."""
    records = [
        _route_span(f"old{i}", metadata={"has_match": True, "layer": "semantic"}) for i in range(5)
    ]
    path = _write_jsonl(tmp_path / "spans.jsonl", records)
    result = observe_routing(path, thresholds=ObserveThresholds(min_samples=100, min_coverage=0.0))
    ds = result.report["metrics"]["decision_source"]
    assert ds["state"] == INSUFFICIENT
    assert ds["reason"] == "below_min_samples"
    assert ds["unknown_share"] == 1.0


# ---------------------------------------------------------------------------
# Near-miss eval JSON + provenance
# ---------------------------------------------------------------------------


def test_near_miss_not_requested_when_omitted(tmp_path: Path) -> None:
    path = _write_jsonl(tmp_path / "spans.jsonl", _scored_run(60, 40))
    result = observe_routing(path)
    near = result.report["metrics"]["near_miss"]
    assert near["state"] == NOT_REQUESTED
    assert near["reason"] == "not_supplied"
    assert near["rate"] is None
    assert near["source"] is None


def test_near_miss_valid_payload_and_provenance(tmp_path: Path) -> None:
    path = _write_jsonl(tmp_path / "spans.jsonl", _scored_run(60, 40))
    eval_path = tmp_path / "eval.json"
    eval_path.write_text(json.dumps(_eval_payload()), encoding="utf-8")
    result = observe_routing(path, eval_json=eval_path, now=_NOW)
    near = result.report["metrics"]["near_miss"]
    assert near["rate"] == 0.15
    assert near["state"] == WARN
    assert near["source"] == "eval_json"
    assert near["provenance"]["dataset"] == "tests/benchmark/routing_eval.yaml"
    assert near["provenance"]["expected_dataset"] == "tests/benchmark/routing_eval.yaml"
    assert near["provenance"]["dataset_matches"] is True
    assert near["provenance"]["hermetic"] is True
    assert near["provenance"]["age_seconds"] == 3600.0
    assert near["provenance"]["future_skew_seconds"] == 0.0
    assert near["provenance"]["max_age_hours"] == 24.0
    assert result.report["inputs"]["expected_eval_dataset"] == "tests/benchmark/routing_eval.yaml"
    assert result.report["thresholds"]["max_eval_age_hours"] == 24.0
    assert result.report["overall_state"] == WARN
    assert result.exit_code == 1


def test_near_miss_healthy_golden(tmp_path: Path) -> None:
    """A matching, fresh, hermetic eval below the warn rate is healthy."""
    path = _write_jsonl(tmp_path / "spans.jsonl", _scored_run(70, 30))
    eval_path = tmp_path / "eval.json"
    eval_path.write_text(
        json.dumps(_eval_payload(n_near_miss=20, over_inject=2, n_neg=50)),
        encoding="utf-8",
    )
    result = observe_routing(path, eval_json=eval_path, now=_NOW)
    near = result.report["metrics"]["near_miss"]
    assert near["state"] == HEALTHY
    assert near["rate"] == 0.1
    assert result.report["overall_state"] == HEALTHY
    assert result.exit_code == 0


def test_dataset_identity_normalizes_separators_and_leading_dot(tmp_path: Path) -> None:
    path = _write_jsonl(tmp_path / "spans.jsonl", _scored_run(70, 30))
    eval_path = tmp_path / "eval.json"
    eval_path.write_text(
        json.dumps(_eval_payload(dataset="./tests\\benchmark\\routing_eval.yaml")),
        encoding="utf-8",
    )
    result = observe_routing(path, eval_json=eval_path, now=_NOW)
    assert result.fault is False
    assert result.report["metrics"]["near_miss"]["provenance"]["dataset_matches"] is True


def test_near_miss_non_hermetic_is_provenance_fault(tmp_path: Path) -> None:
    """Non-hermetic evidence is rejected outright, not merely recommended against."""
    path = _write_jsonl(tmp_path / "spans.jsonl", _scored_run(60, 40))
    eval_path = tmp_path / "eval.json"
    eval_path.write_text(json.dumps(_eval_payload(hermetic=False)), encoding="utf-8")
    result = observe_routing(path, eval_json=eval_path, now=_NOW)
    assert result.fault is True
    assert result.exit_code == 3
    assert result.report["overall_state"] == "fault"
    assert result.report["outcome"] == {"kind": "fault", "reason": "invalid_eval_provenance"}
    assert result.report["error"]["kind"] == "invalid_eval_provenance"
    assert result.report["metrics"]["near_miss"]["provenance"]["hermetic"] is False


def test_dataset_mismatch_is_provenance_fault(tmp_path: Path) -> None:
    path = _write_jsonl(tmp_path / "spans.jsonl", _scored_run(60, 40))
    eval_path = tmp_path / "eval.json"
    eval_path.write_text(json.dumps(_eval_payload(dataset="other/eval.yaml")), encoding="utf-8")
    result = observe_routing(path, eval_json=eval_path, now=_NOW)
    assert result.exit_code == 3
    assert result.report["error"]["kind"] == "invalid_eval_provenance"
    assert result.report["metrics"]["near_miss"]["provenance"]["dataset_matches"] is False


def test_expected_dataset_can_be_overridden(tmp_path: Path) -> None:
    path = _write_jsonl(tmp_path / "spans.jsonl", _scored_run(70, 30))
    eval_path = tmp_path / "eval.json"
    eval_path.write_text(json.dumps(_eval_payload(dataset="custom/eval.yaml")), encoding="utf-8")
    result = observe_routing(
        path, eval_json=eval_path, expected_eval_dataset="custom/eval.yaml", now=_NOW
    )
    assert result.fault is False
    assert result.report["metrics"]["near_miss"]["provenance"]["dataset_matches"] is True
    assert result.report["inputs"]["expected_eval_dataset"] == "custom/eval.yaml"


def test_basename_match_is_rejected(tmp_path: Path) -> None:
    """Matching only the basename must never satisfy the dataset identity."""
    path = _write_jsonl(tmp_path / "spans.jsonl", _scored_run(60, 40))
    eval_path = tmp_path / "eval.json"
    eval_path.write_text(
        json.dumps(_eval_payload(dataset="elsewhere/routing_eval.yaml")), encoding="utf-8"
    )
    result = observe_routing(path, eval_json=eval_path, now=_NOW)
    assert result.exit_code == 3
    assert result.report["error"]["kind"] == "invalid_eval_provenance"


def test_eval_stale_over_boundary_is_provenance_fault(tmp_path: Path) -> None:
    path = _write_jsonl(tmp_path / "spans.jsonl", _scored_run(70, 30))
    eval_path = tmp_path / "eval.json"
    stale = (_NOW - timedelta(hours=24, seconds=1)).isoformat()
    eval_path.write_text(json.dumps(_eval_payload(generated_at=stale)), encoding="utf-8")
    result = observe_routing(path, eval_json=eval_path, now=_NOW)
    assert result.exit_code == 3
    assert result.report["error"]["kind"] == "invalid_eval_provenance"
    assert result.report["metrics"]["near_miss"]["provenance"]["age_seconds"] == 86401.0


def test_eval_accepted_exactly_at_max_age_boundary(tmp_path: Path) -> None:
    path = _write_jsonl(tmp_path / "spans.jsonl", _scored_run(70, 30))
    eval_path = tmp_path / "eval.json"
    boundary = (_NOW - timedelta(hours=24)).isoformat()
    eval_path.write_text(json.dumps(_eval_payload(generated_at=boundary)), encoding="utf-8")
    result = observe_routing(path, eval_json=eval_path, now=_NOW)
    assert result.fault is False
    assert result.report["metrics"]["near_miss"]["provenance"]["age_seconds"] == 86400.0


def test_eval_future_beyond_skew_is_provenance_fault(tmp_path: Path) -> None:
    path = _write_jsonl(tmp_path / "spans.jsonl", _scored_run(70, 30))
    eval_path = tmp_path / "eval.json"
    future = (_NOW + timedelta(minutes=5, seconds=1)).isoformat()
    eval_path.write_text(json.dumps(_eval_payload(generated_at=future)), encoding="utf-8")
    result = observe_routing(path, eval_json=eval_path, now=_NOW)
    assert result.exit_code == 3
    assert result.report["error"]["kind"] == "invalid_eval_provenance"
    assert result.report["metrics"]["near_miss"]["provenance"]["future_skew_seconds"] == 301.0


def test_eval_accepted_exactly_at_future_skew_boundary(tmp_path: Path) -> None:
    path = _write_jsonl(tmp_path / "spans.jsonl", _scored_run(70, 30))
    eval_path = tmp_path / "eval.json"
    future = (_NOW + timedelta(minutes=5)).isoformat()
    eval_path.write_text(json.dumps(_eval_payload(generated_at=future)), encoding="utf-8")
    result = observe_routing(path, eval_json=eval_path, now=_NOW)
    assert result.fault is False
    assert result.report["metrics"]["near_miss"]["provenance"]["future_skew_seconds"] == 300.0


def test_naive_generated_at_is_provenance_fault(tmp_path: Path) -> None:
    path = _write_jsonl(tmp_path / "spans.jsonl", _scored_run(70, 30))
    eval_path = tmp_path / "eval.json"
    eval_path.write_text(
        json.dumps(_eval_payload(generated_at="2026-09-15T08:00:00")), encoding="utf-8"
    )
    result = observe_routing(path, eval_json=eval_path, now=_NOW)
    assert result.exit_code == 3
    assert result.report["error"]["kind"] == "invalid_eval_provenance"


def test_provenance_freshness_independent_of_span_window(tmp_path: Path) -> None:
    """--since/--until filter spans only; eval freshness uses the injected now."""
    path = _write_jsonl(tmp_path / "spans.jsonl", _scored_run(70, 30))
    eval_path = tmp_path / "eval.json"
    eval_path.write_text(json.dumps(_eval_payload()), encoding="utf-8")
    result = observe_routing(
        path,
        eval_json=eval_path,
        since="2027-01-01T00:00:00",  # excludes every span; eval is still fresh
        now=_NOW,
    )
    assert result.fault is False
    assert result.report["metrics"]["near_miss"]["provenance"]["age_seconds"] == 3600.0


def test_provenance_fault_not_suppressed_by_report_only(tmp_path: Path) -> None:
    path = _write_jsonl(tmp_path / "spans.jsonl", _scored_run(60, 40))
    eval_path = tmp_path / "eval.json"
    eval_path.write_text(json.dumps(_eval_payload(hermetic=False)), encoding="utf-8")
    result = observe_routing(path, eval_json=eval_path, report_only=True, now=_NOW)
    assert result.fault is True
    assert result.exit_code == 3
    assert result.report["overall_state"] == "fault"


def test_near_miss_below_min_rows_is_insufficient(tmp_path: Path) -> None:
    path = _write_jsonl(tmp_path / "spans.jsonl", _scored_run(60, 40))
    eval_path = tmp_path / "eval.json"
    eval_path.write_text(
        json.dumps(_eval_payload(n_near_miss=4, over_inject=1, n_neg=5)), encoding="utf-8"
    )
    result = observe_routing(path, eval_json=eval_path, now=_NOW)
    near = result.report["metrics"]["near_miss"]
    assert near["state"] == INSUFFICIENT
    assert near["reason"] == "eval_rows_below_min"
    assert near["rate"] == 0.25


def test_near_miss_missing_file_is_insufficient(tmp_path: Path) -> None:
    path = _write_jsonl(tmp_path / "spans.jsonl", _scored_run(70, 30))
    result = observe_routing(path, eval_json=tmp_path / "nope.json")
    assert result.report["metrics"]["near_miss"]["state"] == INSUFFICIENT
    assert result.exit_code == 4


def test_require_inputs_escalates_missing_eval_to_fault(tmp_path: Path) -> None:
    path = _write_jsonl(tmp_path / "spans.jsonl", _scored_run(70, 30))
    result = observe_routing(path, eval_json=tmp_path / "nope.json", require_inputs=True)
    assert result.exit_code == 3
    assert result.report["error"]["kind"] == "missing_input"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.pop("dataset"),
        lambda p: p.pop("hermetic"),
        lambda p: p.pop("generated_at"),
        lambda p: p.update({"dataset": ""}),
        lambda p: p.update({"hermetic": "yes"}),
        lambda p: p.update({"generated_at": "not-a-date"}),
        lambda p: p.update({"generated_at": None}),
    ],
)
def test_invalid_eval_provenance_is_fault(tmp_path: Path, mutate: Any) -> None:
    path = _write_jsonl(tmp_path / "spans.jsonl", _scored_run(60, 40))
    payload = _eval_payload()
    mutate(payload)
    eval_path = tmp_path / "eval.json"
    eval_path.write_text(json.dumps(payload), encoding="utf-8")
    result = observe_routing(path, eval_json=eval_path, now=_NOW)
    assert result.exit_code == 3
    assert result.fault is True
    assert result.report["error"]["kind"] == "invalid_eval_provenance"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.update({"n_near_miss": "20"}),
        lambda p: p.update({"near_miss_over_inject": 999}),
        lambda p: p.update({"n_neg": 1}),
    ],
)
def test_invalid_eval_counts_is_fault(tmp_path: Path, mutate: Any) -> None:
    path = _write_jsonl(tmp_path / "spans.jsonl", _scored_run(60, 40))
    payload = _eval_payload()
    mutate(payload)
    eval_path = tmp_path / "eval.json"
    eval_path.write_text(json.dumps(payload), encoding="utf-8")
    result = observe_routing(path, eval_json=eval_path, now=_NOW)
    assert result.exit_code == 3
    assert result.fault is True
    assert result.report["error"]["kind"] == "invalid_eval_payload"


def test_invalid_eval_json_is_fault(tmp_path: Path) -> None:
    path = _write_jsonl(tmp_path / "spans.jsonl", _scored_run(60, 40))
    eval_path = tmp_path / "eval.json"
    eval_path.write_text("{not json", encoding="utf-8")
    result = observe_routing(path, eval_json=eval_path)
    assert result.exit_code == 3
    assert result.report["error"]["kind"] == "invalid_eval_payload"


# ---------------------------------------------------------------------------
# Window / project filters
# ---------------------------------------------------------------------------


def test_window_half_open_and_naive_utc(tmp_path: Path) -> None:
    since = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
    until = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
    records = [
        _route_span("before", started_at=since - timedelta(seconds=1)),
        _route_span("at-since", started_at=since),
        _route_span("inside", started_at=since + timedelta(hours=1)),
        _route_span("at-until", started_at=until),
        _route_span("after", started_at=until + timedelta(seconds=1)),
    ]
    path = _write_jsonl(tmp_path / "spans.jsonl", records)
    result = observe_routing(path, since="2026-09-05T12:00:00", until="2026-09-06T12:00:00")
    assert result.report["counts"]["n_route"] == 2  # at-since inclusive; at-until excluded
    assert result.report["window"]["since"] == "2026-09-05T12:00:00+00:00"
    assert result.report["window"]["until"] == "2026-09-06T12:00:00+00:00"


def test_window_drops_no_timestamp_span(tmp_path: Path) -> None:
    record = _route_span("no-ts")
    del record["started_at"]
    records = [_route_span("inside"), record]
    path = _write_jsonl(tmp_path / "spans.jsonl", records)
    result = observe_routing(path, since="2026-09-01T00:00:00")
    assert result.report["counts"]["n_route"] == 1
    assert result.report["counts"]["n_no_ts"] == 1


def test_invalid_window_is_usage_error(tmp_path: Path) -> None:
    path = _write_jsonl(tmp_path / "spans.jsonl", _scored_run(1, 1))
    with pytest.raises(ValueError):
        observe_routing(path, since="not-a-date")
    with pytest.raises(ValueError):
        observe_routing(path, since="2026-09-05", until="2026-09-04")


def test_project_filter(tmp_path: Path) -> None:
    records = [
        _route_span("a", project_id="vibesop-py"),
        _route_span("b", project_id="other"),
        _route_span("c", project_id="default"),
    ]
    path = _write_jsonl(tmp_path / "spans.jsonl", records)
    result = observe_routing(path, project_id="vibesop-py")
    assert result.report["counts"]["n_route"] == 1
    assert result.report["filters"]["project_id"] == "vibesop-py"


# ---------------------------------------------------------------------------
# Determinism / exits / report-only
# ---------------------------------------------------------------------------


def test_deterministic_normalized_json(tmp_path: Path) -> None:
    path = _write_jsonl(tmp_path / "spans.jsonl", _scored_run(60, 40))
    now = datetime(2026, 9, 15, 9, 0, tzinfo=UTC)
    first = observe_routing(path, now=now).report
    second = observe_routing(path, now=now).report
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_report_only_suppresses_critical_but_not_fault(tmp_path: Path) -> None:
    crit_path = _write_jsonl(tmp_path / "crit.jsonl", _scored_run(40, 60))
    result = observe_routing(crit_path, report_only=True)
    assert result.report["overall_state"] == CRITICAL
    assert result.exit_code == 0

    fault = observe_routing(tmp_path / "nope.jsonl", report_only=True)
    assert fault.fault is False
    assert fault.report["overall_state"] == INSUFFICIENT
    assert fault.exit_code == 0  # insufficient is a verdict, so report-only suppresses it

    dir_fault = observe_routing(tmp_path, report_only=True)
    assert dir_fault.fault is True
    assert dir_fault.exit_code == 3


def test_states_map_to_exits(tmp_path: Path) -> None:
    healthy = _write_jsonl(tmp_path / "healthy.jsonl", _scored_run(70, 30))
    assert observe_routing(healthy).exit_code == 0
    assert observe_routing(healthy).report["overall_state"] == HEALTHY

    warn = _write_jsonl(tmp_path / "warn.jsonl", _scored_run(55, 45))
    assert observe_routing(warn).exit_code == 1

    crit = _write_jsonl(tmp_path / "crit.jsonl", _scored_run(40, 60))
    assert observe_routing(crit).exit_code == 3

    assert observe_routing(tmp_path / "none.jsonl").exit_code == 4


def test_threshold_validation_raises(tmp_path: Path) -> None:
    path = _write_jsonl(tmp_path / "spans.jsonl", _scored_run(1, 1))
    with pytest.raises(ValueError):
        observe_routing(path, thresholds=ObserveThresholds(nomatch_warn=0.8, nomatch_crit=0.2))
    with pytest.raises(ValueError):
        observe_routing(path, thresholds=ObserveThresholds(min_coverage=1.5))
    with pytest.raises(ValueError):
        observe_routing(path, thresholds=ObserveThresholds(min_samples=0))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_missing_spans_exit_4_json(tmp_path: Path, runner: CliRunner) -> None:
    result = runner.invoke(
        observe_cmd.app, ["routing", "--spans", str(tmp_path / "nope.jsonl"), "--json"]
    )
    assert result.exit_code == 4
    payload = json.loads(result.stdout)
    assert payload["schema"] == "vibesop.observe.routing"
    assert payload["error"]["kind"] == "missing_input"


def test_cli_critical_report_only_exit_0(tmp_path: Path, runner: CliRunner) -> None:
    path = _write_jsonl(tmp_path / "crit.jsonl", _scored_run(40, 60))
    result = runner.invoke(
        observe_cmd.app, ["routing", "--spans", str(path), "--json", "--report-only"]
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["overall_state"] == "critical"


def test_cli_bad_since_exit_2(tmp_path: Path, runner: CliRunner) -> None:
    path = _write_jsonl(tmp_path / "spans.jsonl", _scored_run(1, 1))
    result = runner.invoke(
        observe_cmd.app, ["routing", "--spans", str(path), "--since", "not-a-date"]
    )
    assert result.exit_code == 2


def test_cli_human_block_is_not_json(tmp_path: Path, runner: CliRunner) -> None:
    path = _write_jsonl(tmp_path / "spans.jsonl", _scored_run(70, 30))
    result = runner.invoke(observe_cmd.app, ["routing", "--spans", str(path)])
    assert result.exit_code == 0
    assert "routing observation" in result.stdout
    assert "overall_state: healthy" in result.stdout


def test_cli_registered_under_main_app() -> None:
    from vibesop.cli.main import app

    result = CliRunner().invoke(app, ["observe", "routing", "--help"])
    assert result.exit_code == 0
    assert "--spans" in result.stdout
    assert "--eval-json" in result.stdout
    assert "--expected-eval-dataset" in result.stdout
    assert "--max-eval-age-hours" in result.stdout


def test_cli_provenance_fault_exit_3_even_report_only(tmp_path: Path, runner: CliRunner) -> None:
    spans = _write_jsonl(tmp_path / "spans.jsonl", _scored_run(60, 40))
    eval_path = tmp_path / "eval.json"
    eval_path.write_text(json.dumps(_eval_payload(hermetic=False)), encoding="utf-8")
    result = runner.invoke(
        observe_cmd.app,
        [
            "routing",
            "--spans",
            str(spans),
            "--eval-json",
            str(eval_path),
            "--expected-eval-dataset",
            "tests/benchmark/routing_eval.yaml",
            "--report-only",
            "--json",
        ],
    )
    assert result.exit_code == 3
    payload = json.loads(result.stdout)
    assert payload["overall_state"] == "fault"
    assert payload["error"]["kind"] == "invalid_eval_provenance"
    assert payload["inputs"]["expected_eval_dataset"] == "tests/benchmark/routing_eval.yaml"


def test_cli_matching_fresh_eval_is_healthy(tmp_path: Path, runner: CliRunner) -> None:
    from datetime import datetime

    spans = _write_jsonl(tmp_path / "spans.jsonl", _scored_run(70, 30))
    fresh = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    eval_path = tmp_path / "eval.json"
    eval_path.write_text(
        json.dumps(_eval_payload(n_near_miss=20, over_inject=2, n_neg=50, generated_at=fresh)),
        encoding="utf-8",
    )
    result = runner.invoke(
        observe_cmd.app,
        [
            "routing",
            "--spans",
            str(spans),
            "--eval-json",
            str(eval_path),
            "--expected-eval-dataset",
            "tests/benchmark/routing_eval.yaml",
            "--json",
        ],
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["metrics"]["near_miss"]["state"] == "healthy"


@pytest.mark.parametrize("bad", ["0", "-1", "nan", "inf"])
def test_cli_invalid_max_eval_age_hours_exit_2(tmp_path: Path, runner: CliRunner, bad: str) -> None:
    spans = _write_jsonl(tmp_path / "spans.jsonl", _scored_run(1, 1))
    result = runner.invoke(
        observe_cmd.app,
        ["routing", "--spans", str(spans), "--max-eval-age-hours", bad],
    )
    assert result.exit_code == 2


# ---------------------------------------------------------------------------
# No writes
# ---------------------------------------------------------------------------


def test_observe_never_writes_policy_or_inputs(tmp_path: Path) -> None:
    path = _write_jsonl(tmp_path / "spans.jsonl", _scored_run(60, 40))
    eval_path = tmp_path / "eval.json"
    eval_path.write_text(json.dumps(_eval_payload()), encoding="utf-8")
    registry = tmp_path / "decision-source.yaml"
    registry.write_text("schema_version: 1\n", encoding="utf-8")
    before = {
        name: (tmp_path / name).read_bytes()
        for name in ("spans.jsonl", "eval.json", "decision-source.yaml")
    }
    observe_routing(path, eval_json=eval_path, now=_NOW)
    after = {
        name: (tmp_path / name).read_bytes()
        for name in ("spans.jsonl", "eval.json", "decision-source.yaml")
    }
    assert before == after
    assert registry.read_text(encoding="utf-8") == "schema_version: 1\n"


# ---------------------------------------------------------------------------
# Human render
# ---------------------------------------------------------------------------


def test_render_human_deterministic(tmp_path: Path) -> None:
    path = _write_jsonl(tmp_path / "spans.jsonl", _scored_run(60, 40))
    report = observe_routing(path, now=datetime(2026, 9, 15, 9, 0, tzinfo=UTC)).report
    assert render_human(report) == render_human(report)
    assert "scoring_coverage" in render_human(report)
