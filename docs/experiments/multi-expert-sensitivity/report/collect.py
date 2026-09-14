"""Load sensitivity results. Remap D_soft→D only when calling frozen analysis."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_rows(run_root: Path) -> list[dict]:
    run_root = Path(run_root)
    manifest = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
    rows = []
    for item in manifest["assignments"]:
        dest = run_root / item["allocation_id"]
        path = dest / "result.json"
        if not path.is_file():
            rows.append({**item, "status": "pending", "ledger": {}, "evaluation": None, "error": None, "notes": {}})
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        data.setdefault("task_id", item["task_id"])
        data.setdefault("arm", item["arm"])
        data.setdefault("spec_variant", item["spec_variant"])
        data.setdefault("repeat", item["repeat"])
        data["allocation_id"] = item["allocation_id"]
        rows.append(data)
    return rows


def remap_dsoft_for_frozen_analysis(rows: list[dict]) -> list[dict]:
    """Copy rows so frozen da_from_results sees arm D. Original labels stay on source rows."""
    out = []
    for row in rows:
        copied = dict(row)
        if copied.get("arm") == "D_soft":
            copied["arm_label"] = "D_soft"
            copied["arm"] = "D"
        out.append(copied)
    return out


def classify(row: dict) -> str:
    err = str(row.get("error") or "")
    status = row.get("status")
    if status == "passed":
        return "passed"
    if status in {"pending", "running"}:
        return status
    if status == "interrupted":
        return "interrupted"
    if "stage_budget_exhausted" in err:
        return "stage_cap"
    if "I_precheck" in err:
        return "i_precheck"
    if "budget_exhausted" in err or "reported_budget_exceeded" in err:
        return "global_budget"
    if "ownership_conflict" in err or "invalid_decomposition" in err:
        return "protocol"
    notes = row.get("notes") or {}
    if notes.get("violations") or notes.get("conflicts"):
        return "ownership_or_path"
    ev = row.get("evaluation")
    if ev is None:
        if status == "error":
            return "api_or_harness_error"
        return "failed_without_hidden_eval"
    if status == "error":
        return "api_or_harness_error"
    return "hidden_implementation_failure"


def reached_hidden(row: dict) -> bool:
    ev = row.get("evaluation")
    return isinstance(ev, dict) and bool(ev.get("checks"))


def reached_integrate(row: dict) -> bool:
    rec = row.get("recorder") or {}
    stages = rec.get("partial_stages") or []
    led = row.get("ledger") or {}
    used = led.get("stage_used") or {}
    if row.get("arm") in {"C", "D", "D_soft", "E"}:
        return (used.get("integrate") or 0) > 0 or any("integrate" in str(s) for s in stages)
    return True
