"""Allocate 360 once. Resume without rerunning terminal or interrupted rows."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tasks.catalog import CALIBRATION_TASKS  # noqa: E402
from tasks.evaluate import evaluate  # noqa: E402

from .arms import run_arm  # noqa: E402
from .budget import Ledger, stage_caps_for  # noqa: E402
from .llm import MODEL, TEMPERATURE, THINKING, make_client  # noqa: E402
from .pack import docker_image_id, file_index, task_hashes, verify_pack, write_pack  # noqa: E402
from .recorder import RunRecorder  # noqa: E402
from .schedule import (  # noqa: E402
    CONCURRENCY,
    SEED,
    TERMINAL,
    allocation_id,
    build_assignments,
    counts,
    dest_for,
    scan_and_interrupt,
    select_new,
)

PARTICIPANT_FAIL = (
    "ownership_conflict",
    "invalid_decomposition",
    "not_delivered",
    "incomplete_final_response",
    "budget_exhausted",
    "stage_budget_exhausted",
    "reported_budget_exceeded",
    "hang_timeout",
    "turn_limit_reached",
)
RESOURCES = ROOT / "resources.yaml"
REQUIRED_BUDGET = ("T_completion_tokens", "I_prompt_tokens", "K_tool_calls", "hang_timeout_s")


def _save(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def load_resources(path: Path = RESOURCES) -> dict:
    if not path.is_file():
        raise RuntimeError("missing_resources:" + str(path))
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("missing_yaml") from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("budget"), dict):
        raise RuntimeError("invalid_resources:budget")
    budget = data["budget"]
    for key in REQUIRED_BUDGET:
        value = budget.get(key)
        if type(value) is not int or value <= 0:
            raise RuntimeError("invalid_resources:" + key)
    if budget.get("identical_for_all_arms") is not True:
        raise RuntimeError("invalid_resources:identical_for_all_arms")
    execu = data.get("execution") or {}
    if execu.get("concurrency") != CONCURRENCY:
        raise RuntimeError("invalid_resources:concurrency")
    if execu.get("seed") != SEED:
        raise RuntimeError("invalid_resources:seed")
    docker = data.get("docker") or {}
    if not docker.get("image_id"):
        raise RuntimeError("invalid_resources:docker_image_id")
    live = docker_image_id(docker.get("image_name") or "python:3.12-slim")
    if live != docker["image_id"]:
        raise RuntimeError("docker_image_id_drift:" + live)
    return data


def run_one(client, task_id: str, arm: str, spec_variant: str, dest: Path, resources: dict,
            repeat: int = 0) -> dict:
    if dest.exists():
        raise RuntimeError("duplicate_allocation:" + dest.name)
    dest.mkdir(parents=True, exist_ok=False)
    budget = resources["budget"]
    hang = int(budget["hang_timeout_s"])
    ledger = Ledger(T=int(budget["T_completion_tokens"]), I=int(budget["I_prompt_tokens"]),
                    K=int(budget["K_tool_calls"]))
    caps = stage_caps_for(arm, ledger.T)
    if caps:
        ledger.set_stage_caps(caps)
    recorder = RunRecorder(dest, hang_timeout_s=hang)
    result = {
        "task_id": task_id,
        "arm": arm,
        "spec_variant": spec_variant,
        "repeat": repeat,
        "allocation_id": dest.name,
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "task_hash": task_hashes().get(task_id) or "",
        "model_request": MODEL,
        "temperature": TEMPERATURE,
        "thinking": THINKING,
        "limits": ledger.limits,
    }
    _save(dest / "result.json", result)
    try:
        notes = run_arm(client, ledger, recorder, dest, task_id, arm, spec_variant)
        evaluation = evaluate(task_id, dest / "workspace")
        slim = {k: notes[k] for k in notes if k not in {"all_tool_traces"}}
        result["notes"] = slim
        result["tool_trace_count"] = len(notes.get("all_tool_traces") or [])
        _save(dest / "tools.json", notes.get("all_tool_traces") or [])
        result["evaluation"] = evaluation
        result["status"] = "passed" if evaluation["passed"] else "failed"
        if not notes.get("delivered"):
            result["status"] = "failed"
            result["error"] = "not_delivered"
        if notes.get("conflicts"):
            result["status"] = "failed"
            result["error"] = "ownership_or_conflict"
    except Exception as exc:
        msg = str(exc)
        kind = "error"
        for prefix in PARTICIPANT_FAIL:
            if msg.startswith(prefix) or prefix in msg:
                kind = "failed"
                break
        result.update(
            status=kind,
            error_type=type(exc).__name__,
            error=msg[:1500],
            traceback=traceback.format_exc()[-2000:],
        )
    result["ledger"] = ledger.snapshot()
    result["recorder"] = recorder.snapshot()
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    _save(dest / "result.json", result)
    print(json.dumps({k: result.get(k) for k in ("task_id", "arm", "spec_variant", "repeat", "status")},
                     ensure_ascii=False), flush=True)
    return result


def _worker(row: dict, run_root: Path, resources: dict) -> dict:
    client = make_client()
    dest = dest_for(run_root, row)
    return run_one(client, row["task_id"], row["arm"], row["spec_variant"], dest, resources,
                   repeat=int(row.get("repeat") or 0))


def write_formal_manifest(run_root: Path, resources: dict, seed: int) -> dict:
    assignments = build_assignments("formal", seed)
    if len(assignments) != 360:
        raise RuntimeError("formal_assignment_count")
    pack = write_pack(run_root / "frozen-sources")
    live_id = docker_image_id(resources["docker"]["image_name"])
    if live_id != resources["docker"]["image_id"]:
        raise RuntimeError("docker_image_id_drift")
    manifest = {
        "phase": "formal",
        "n_assignments": 360,
        "seed": seed,
        "concurrency": CONCURRENCY,
        "execution": "threadpool_independent_client_ledger_workspace_recorder",
        "model": MODEL,
        "thinking": THINKING,
        "temperature": TEMPERATURE,
        "resources": resources["budget"],
        "docker_image_id": live_id,
        "sdk_retries": 0,
        "base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "assignments": assignments,
        "task_hashes": task_hashes(),
        "source_index": pack["relative_paths"],
        "pack_sha256": pack["pack_sha256"],
        "calibration_tasks_excluded_from_360": list(CALIBRATION_TASKS),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "immutable": True,
    }
    _save(run_root / "manifest.json", manifest)
    return manifest


def load_manifest(run_root: Path) -> dict:
    data = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
    if data.get("phase") == "formal" and len(data.get("assignments") or []) != 360:
        raise RuntimeError("manifest_not_360")
    return data


def assert_freeze(run_root: Path, resources: dict) -> None:
    verify_pack(run_root / "frozen-sources", ROOT)
    manifest = load_manifest(run_root)
    if manifest.get("task_hashes") != task_hashes():
        raise RuntimeError("task_hash_drift")
    if manifest.get("source_index") != file_index(ROOT):
        raise RuntimeError("source_index_drift")
    if manifest.get("docker_image_id") != docker_image_id(resources["docker"]["image_name"]):
        raise RuntimeError("docker_image_id_drift")
    if manifest.get("resources") != resources["budget"]:
        raise RuntimeError("resource_drift")
    if manifest.get("concurrency") != CONCURRENCY:
        raise RuntimeError("concurrency_drift")


def execute_rows(run_root: Path, rows: list[dict], resources: dict, workers: int) -> list[dict]:
    if not rows:
        return []
    results: list[dict] = []
    lock = threading.Lock()
    progress = run_root / "progress.jsonl"

    def job(row):
        result = _worker(row, run_root, resources)
        with lock:
            with progress.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"allocation_id": row["allocation_id"], "status": result.get("status")},
                                    ensure_ascii=False) + "\n")
        return result

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(job, row) for row in rows]
        for fut in as_completed(futures):
            results.append(fut.result())
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", default="informal-calibration",
                        choices=["informal-calibration", "formal", "offline"])
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--i-understand-formal", action="store_true")
    parser.add_argument("--max-new", type=int, default=0,
                        help="Execute at most this many never-started allocations. Formal default 12.")
    parser.add_argument("--resume", type=str, default="",
                        help="Continue an existing run_root. Manifest stays 360.")
    parser.add_argument("--workers", type=int, default=CONCURRENCY)
    parser.add_argument("--offline-client", action="store_true", help="Used by tests.")
    args = parser.parse_args(argv)
    if args.workers != CONCURRENCY and args.phase == "formal":
        raise RuntimeError("formal_workers_must_be_frozen_concurrency")
    resources = load_resources()
    if args.phase == "formal":
        if not args.i_understand_formal:
            print("Formal 360 requires --i-understand-formal.", file=sys.stderr)
            return 2
        max_new = args.max_new or 12
        if args.resume:
            run_root = Path(args.resume)
            if not (run_root / "manifest.json").is_file():
                raise RuntimeError("resume_missing_manifest")
            manifest = load_manifest(run_root)
            if len(manifest["assignments"]) != 360:
                raise RuntimeError("resume_manifest_not_360")
            assert_freeze(run_root, resources)
        else:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            run_root = ROOT / "runs" / stamp
            run_root.mkdir(parents=True, exist_ok=False)
            manifest = write_formal_manifest(run_root, resources, args.seed)
            if len(manifest["assignments"]) != 360:
                raise RuntimeError("manifest_not_360")
        interrupted = scan_and_interrupt(run_root, manifest["assignments"])
        _save(run_root / "interrupted.json", {"ids": interrupted, "at": datetime.now(timezone.utc).isoformat()})
        todo = select_new(run_root, manifest["assignments"], max_new)
        _save(run_root / "batch.json", {
            "max_new": max_new,
            "selected": [r["allocation_id"] for r in todo],
            "counts": counts(run_root, manifest["assignments"]),
        })
        print("RUN_ROOT=" + str(run_root), flush=True)
        print("MANIFEST_N=" + str(len(manifest["assignments"])), flush=True)
        print("BATCH_N=" + str(len(todo)), flush=True)
        if args.phase == "offline" or args.offline_client:
            return 0
        execute_rows(run_root, todo, resources, args.workers)
        _save(run_root / "counts.json", counts(run_root, manifest["assignments"]))
        print("COMPLETE " + str(run_root), flush=True)
        return 0
    # Informal / offline helper path (does not write a 360 manifest).
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_root = ROOT / "runs" / stamp
    run_root.mkdir(parents=True)
    assignments = build_assignments(args.phase if args.phase != "offline" else "informal-calibration", args.seed)
    _save(run_root / "manifest.json", {
        "phase": args.phase,
        "assignments": assignments,
        "n_assignments": len(assignments),
        "seed": args.seed,
    })
    print("RUN_ROOT=" + str(run_root), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
