"""Synthetic span pairing for scripts/measure_gate43_echo.py (no cmspark)."""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "measure_gate43_echo.py"
spec = importlib.util.spec_from_file_location("measure_gate43_echo", SCRIPT)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def _span(
    *,
    ts: datetime,
    task_id: str,
    is_cli: bool,
    has_match: bool,
    name: str = "route:x",
) -> dict[str, object]:
    meta: dict[str, object] = {"has_match": has_match}
    if is_cli:
        meta["platform"] = "vibe-cli"
        meta["source"] = "cli"
    else:
        meta["platform"] = "grok-build"
    return {
        "span_kind": "task",
        "name": name,
        "task_id": task_id,
        "started_at": ts.isoformat(),
        "metadata": meta,
        "session_id": "cli-s" if is_cli else "hook-s",
    }


def test_echo_pair_from_jsonl(tmp_path: Path) -> None:
    t0 = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
    rows = [
        _span(ts=t0, task_id="t1", is_cli=False, has_match=True),
        _span(ts=t0 + timedelta(seconds=20), task_id="t1", is_cli=True, has_match=False),
        _span(ts=t0, task_id="t2", is_cli=False, has_match=False),
        _span(ts=t0 + timedelta(seconds=20), task_id="t2", is_cli=True, has_match=False),
        {"span_kind": "tool", "name": "ignored"},
    ]
    path = tmp_path / "spans.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    spans = mod.load_route_spans(path)
    assert len(spans) == 4
    found = mod.pairs(spans)
    assert len(found) == 2
    echoes = [p for p in found if p["echo"]]
    assert len(echoes) == 1
    assert echoes[0]["cross_session"] is True


def test_windows_constants_match_t7_report() -> None:
    assert mod.T0.isoformat() == "2026-08-24T10:42:00+00:00"
    assert (mod.T21 - mod.T0).days == 21
    assert mod.ECHO_DT.total_seconds() == 90
    assert mod.BASELINE_DAYS == 30.05
