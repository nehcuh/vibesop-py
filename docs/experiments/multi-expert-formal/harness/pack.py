"""Path-preserving freeze pack. Growing run artifacts are never sources."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Explicit allowlist. Do not rglob logs/runs/STATUS/READY.
FREEZE_RELATIVE = [
    "harness/__init__.py",
    "harness/analysis.py",
    "harness/audit.py",
    "harness/arms.py",
    "harness/budget.py",
    "harness/engine.py",
    "harness/llm.py",
    "harness/offline_check.py",
    "harness/pack.py",
    "harness/recorder.py",
    "harness/report.py",
    "harness/runner.py",
    "harness/schedule.py",
    "harness/tools.py",
    "tasks/__init__.py",
    "tasks/cases.py",
    "tasks/catalog.py",
    "tasks/common.py",
    "tasks/evaluate.py",
    "tasks/oracles.py",
    "tasks/qa_bank.py",
    "resources.yaml",
    "preregistration.md",
    "independence.md",
    "verify_experiment.py",
]

EXCLUDE_PREFIXES = (
    "runs/",
    "logs/",
    "__pycache__/",
)
EXCLUDE_NAMES = {
    "STATUS.md",
    "READY_FOR_REVIEW.md",
    "FIRST12_AUDIT.md",
    "REPORT.md",
    "verify-latest.json",
    "freeze.json",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def list_freeze_files(root: Path | None = None) -> list[Path]:
    root = Path(root or ROOT)
    missing = []
    files = []
    for rel in FREEZE_RELATIVE:
        path = root / rel
        if not path.is_file():
            missing.append(rel)
        else:
            files.append(path)
    if missing:
        raise RuntimeError("missing_freeze_source:" + ",".join(missing))
    return files


def file_index(root: Path | None = None) -> dict[str, dict]:
    root = Path(root or ROOT)
    out = {}
    for path in list_freeze_files(root):
        rel = path.relative_to(root).as_posix()
        data = path.read_bytes()
        out[rel] = {"sha256": sha256_bytes(data), "bytes": len(data)}
    return out


def write_pack(dest: Path, root: Path | None = None) -> dict:
    root = Path(root or ROOT)
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    index = file_index(root)
    for rel in index:
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, target)
        copied = sha256_bytes(target.read_bytes())
        if copied != index[rel]["sha256"]:
            raise RuntimeError("freeze_copy_mismatch:" + rel)
    pack_hash = sha256_bytes(json.dumps(index, sort_keys=True).encode("utf-8"))
    meta = {"relative_paths": index, "pack_sha256": pack_hash, "count": len(index)}
    (dest / "PACK.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def verify_pack(dest: Path, live_root: Path | None = None) -> None:
    dest = Path(dest)
    live_root = Path(live_root or ROOT)
    meta = json.loads((dest / "PACK.json").read_text(encoding="utf-8"))
    index = meta["relative_paths"]
    live = file_index(live_root)
    if set(live) != set(index):
        raise RuntimeError("freeze_path_set_drift")
    for rel, info in index.items():
        frozen = sha256_bytes((dest / rel).read_bytes())
        if frozen != info["sha256"]:
            raise RuntimeError("freeze_copy_drift:" + rel)
        if live[rel]["sha256"] != info["sha256"]:
            raise RuntimeError("live_source_drift:" + rel)
    if sha256_bytes(json.dumps(index, sort_keys=True).encode("utf-8")) != meta["pack_sha256"]:
        raise RuntimeError("freeze_pack_hash_drift")


def docker_image_id(name: str = "python:3.12-slim") -> str:
    ident = subprocess.check_output(
        ["docker", "image", "inspect", name, "--format", "{{.Id}}"],
        text=True,
    ).strip()
    if not ident.startswith("sha256:"):
        raise RuntimeError("docker_image_id_not_digest:" + ident)
    return ident


def task_hashes() -> dict[str, str]:
    from tasks.catalog import FORMAL_TASKS, TASKS

    out = {}
    for task_id in FORMAL_TASKS:
        task = TASKS[task_id]
        blob = json.dumps(
            {
                "id": task_id,
                "category": task["category"],
                "spec_full": task["spec_full"],
                "spec_brief": task["spec_brief"],
                "qa_ids": task["qa_ids"],
                "files": task["files"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        out[task_id] = sha256_bytes(blob.encode("utf-8"))
    return out
