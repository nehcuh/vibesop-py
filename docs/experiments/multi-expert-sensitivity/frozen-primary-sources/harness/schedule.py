"""Immutable 360 assignments and resume selection. Never slices the manifest."""
from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from pathlib import Path

from tasks.catalog import CALIBRATION_TASKS, FORMAL_TASKS

TERMINAL = {"passed", "failed", "error", "interrupted"}
SEED = 20260913
CONCURRENCY = 8


def allocation_id(row: dict) -> str:
    return f"{row['task_id']}-{row['spec_variant']}-{row['arm']}-r{row['repeat']}"


def dest_for(run_root: Path, row: dict) -> Path:
    return Path(run_root) / allocation_id(row)


def build_assignments(phase: str, seed: int = SEED) -> list[dict]:
    rng = random.Random(seed)
    rows: list[dict] = []
    if phase == "informal-calibration":
        for task_id in CALIBRATION_TASKS:
            for arm in "ABCDE":
                rows.append({"task_id": task_id, "arm": arm, "spec_variant": "full", "repeat": 0})
    elif phase == "formal":
        for task_id in FORMAL_TASKS:
            for spec in ("full", "brief"):
                for arm in "ABCDE":
                    for repeat in range(3):
                        rows.append({"task_id": task_id, "arm": arm, "spec_variant": spec, "repeat": repeat})
        if len(rows) != 360:
            raise RuntimeError("formal_assignment_count:" + str(len(rows)))
    else:
        raise ValueError(phase)
    rng.shuffle(rows)
    for i, row in enumerate(rows):
        row["allocation_id"] = allocation_id(row)
        row["order"] = i
    if phase == "formal" and len({r["allocation_id"] for r in rows}) != 360:
        raise RuntimeError("duplicate_allocation_id")
    return rows


def read_status(dest: Path) -> str | None:
    path = dest / "result.json"
    if not path.is_file():
        if dest.exists():
            return "orphaned"
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "orphaned"
    status = data.get("status")
    if status in TERMINAL or status == "running":
        return status
    return "orphaned"


def mark_interrupted(dest: Path) -> dict:
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / "result.json"
    now = datetime.now(timezone.utc).isoformat()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {"status": "running", "error": "corrupt_result_json"}
    else:
        data = {"status": "running", "error": "interrupted_before_result"}
    data["status"] = "interrupted"
    data["error"] = data.get("error") or "interrupted"
    data["interrupted_at"] = now
    data["rerun"] = False
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return data


def scan_and_interrupt(run_root: Path, assignments: list[dict]) -> list[str]:
    marked = []
    for row in assignments:
        dest = dest_for(run_root, row)
        status = read_status(dest)
        if status in {"running", "orphaned"}:
            mark_interrupted(dest)
            marked.append(row["allocation_id"])
    return marked


def select_new(run_root: Path, assignments: list[dict], max_new: int) -> list[dict]:
    if max_new < 0:
        raise ValueError("max_new")
    chosen = []
    for row in assignments:
        dest = dest_for(run_root, row)
        status = read_status(dest)
        if status in TERMINAL:
            continue
        if status in {"running", "orphaned"}:
            continue
        if dest.exists():
            # Directory present without a terminal result: do not start a duplicate.
            continue
        chosen.append(row)
        if len(chosen) >= max_new:
            break
    return chosen


def counts(run_root: Path, assignments: list[dict]) -> dict[str, int]:
    tallies = {"pending": 0, "passed": 0, "failed": 0, "error": 0, "interrupted": 0, "running": 0, "orphaned": 0}
    for row in assignments:
        status = read_status(dest_for(run_root, row))
        if status is None:
            tallies["pending"] += 1
        elif status in tallies:
            tallies[status] += 1
        else:
            tallies["orphaned"] += 1
    tallies["terminal"] = sum(tallies[k] for k in ("passed", "failed", "error", "interrupted"))
    tallies["total"] = len(assignments)
    return tallies
