"""Full-cohort audit. Presentation/ops layer; not frozen stats."""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))

from harness.pack import docker_image_id, file_index, task_hashes, verify_pack
from harness.schedule import counts, dest_for

LEAK_CANDIDATE_PHRASES = ("hidden acceptance", "hidden eval", "hidden tests")
FIRST12_MANIFEST_SHA256 = "0b9b5f8ea460e4d496302f559f7e3900835dafc1e7f95b637435aa49ceb0d2f4"

# Protocol text may mention that hidden tests exist. Leak means evaluator
# modules, reference sources, or mutant labels in the model request.
HIDDEN_MARKERS = (
    "oracles.py",
    "tasks/cases.py",
    "tasks/evaluate.py",
    "_REFERENCE_ROUTE",
    "_REFERENCE_CONFIG",
    "domain_mutant",
    "self_check()",
)


def _usage(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    u = data.get("usage") or {}
    details = u.get("completion_tokens_details") or {}
    return {
        "prompt": int(u.get("prompt_tokens") or 0),
        "completion": int(u.get("completion_tokens") or 0),
        "cache": int(u.get("prompt_cache_hit_tokens") or 0),
        "reasoning": int(details.get("reasoning_tokens") or 0),
        "model": data.get("model"),
    }


def audit_one(dest: Path, row: dict) -> dict:
    rec = {
        "allocation_id": row["allocation_id"],
        "task_id": row["task_id"],
        "arm": row["arm"],
        "spec_variant": row["spec_variant"],
        "repeat": row["repeat"],
        "issues": [],
    }
    result_path = dest / "result.json"
    if not result_path.is_file():
        rec["status"] = "missing"
        rec["issues"].append("missing_result")
        return rec
    result = json.loads(result_path.read_text(encoding="utf-8"))
    rec["status"] = result.get("status")
    rec["error"] = result.get("error")
    rec["has_evaluation"] = isinstance(result.get("evaluation"), dict)
    rec["eval_n"] = len((result.get("evaluation") or {}).get("checks") or [])
    rec["task_hash_result"] = result.get("task_hash")
    rec["violations"] = (result.get("notes") or {}).get("violations")
    rec["conflicts"] = (result.get("notes") or {}).get("conflicts")
    requests = sorted(dest.glob("call-*-request.json"))
    responses = {p.name.replace("response", "request"): p for p in dest.glob("call-*-response.json")}
    errors = {p.name.replace("error", "request"): p for p in dest.glob("call-*-error.json")}
    rec["n_request"] = len(requests)
    rec["n_response"] = len(responses)
    rec["n_error"] = len(errors)
    ids = []
    prompt = completion = cache = reasoning = 0
    leak = False
    for req in requests:
        m = re.search(r"call-(\d+)-request", req.name)
        if not m:
            rec["issues"].append("bad_request_name:" + req.name)
            continue
        n = int(m.group(1))
        ids.append(n)
        data = json.loads(req.read_text(encoding="utf-8"))
        blob = json.dumps(data.get("messages") or [])
        if any(marker in blob for marker in HIDDEN_MARKERS):
            leak = True
        key = req.name
        has_resp = key in responses
        has_err = key in errors
        if has_resp == has_err:
            rec["issues"].append("request_not_xor_response_error:" + req.name)
        if has_resp:
            u = _usage(responses[key])
            prompt += u["prompt"]
            completion += u["completion"]
            cache += u["cache"]
            reasoning += u["reasoning"]
            rec.setdefault("models", set()).add(u["model"])
        if data.get("call_id") not in (None, n):
            rec["issues"].append("call_id_mismatch:" + req.name)
    rec["models"] = sorted(rec.get("models") or [])
    rec["monotonic"] = ids == list(range(len(ids)))
    if not rec["monotonic"]:
        rec["issues"].append("nonmonotonic_ids")
    led = result.get("ledger") or {}
    rec["ledger_i"] = led.get("used_i")
    rec["ledger_t"] = led.get("used_t")
    rec["ledger_k"] = led.get("used_k")
    rec["raw_i"] = prompt
    rec["raw_t"] = completion
    rec["raw_cache"] = cache
    rec["raw_reasoning"] = reasoning
    rec["usage_match"] = prompt == led.get("used_i") and completion == led.get("used_t")
    if not rec["usage_match"]:
        rec["issues"].append("usage_mismatch")
    rec["hidden_leak_in_requests"] = leak
    if leak:
        rec["issues"].append("hidden_leak")
    rec["leak_candidates"] = []
    for req in requests:
        try:
            payload = json.loads(req.read_text(encoding="utf-8", errors="replace"))
        except json.JSONDecodeError:
            continue
        for msg in payload.get("messages") or []:
            if not isinstance(msg, dict) or msg.get("role") != "assistant":
                continue
            blob = json.dumps(msg, ensure_ascii=False).lower()
            hits = [p for p in LEAK_CANDIDATE_PHRASES if p in blob]
            if hits:
                rec["leak_candidates"].append(
                    {"request": req.name, "phrases": hits, "role": "assistant"}
                )
    rec["cache_in_ledger_events"] = led.get("cache_hit")
    if led.get("cache_hit") not in (None, cache):
        rec["issues"].append("cache_mismatch")
        rec["cache_match"] = False
    else:
        rec["cache_match"] = True
    ws = dest / "workspace"
    if ws.is_dir():
        for name in ("oracles.py", "cases.py", "evaluate.py"):
            if (ws / name).exists():
                rec["issues"].append("workspace_hidden_file:" + name)
    rec["ok"] = not rec["issues"]
    rec["models"] = list(rec["models"])
    return rec


def classify_mech(row: dict) -> str:
    err = str(row.get("error") or "")
    status = row.get("status")
    if status == "passed":
        return "passed"
    if status == "interrupted":
        return "interrupted"
    if "stage_budget_exhausted" in err:
        return "stage_cap"
    if "I_precheck" in err:
        return "i_precheck"
    if err.startswith("budget_exhausted") or "reported_budget_exceeded" in err:
        return "global_budget"
    if "ownership_conflict" in err or "invalid_decomposition" in err:
        return "protocol"
    notes = row.get("notes") or {}
    viol = notes.get("violations") or notes.get("conflicts") or []
    if viol:
        return "ownership_or_path"
    if row.get("evaluation") is None and not row.get("has_evaluation"):
        if status == "error":
            return "api_or_harness_error"
        return "failed_without_hidden_eval"
    if status == "error":
        return "api_or_harness_error"
    return "hidden_implementation_failure"


def run_audit(run_root: Path) -> dict:
    run_root = Path(run_root)
    manifest = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
    assignments = manifest["assignments"]
    verify_pack(run_root / "frozen-sources", ROOT)
    live_index = file_index(ROOT)
    drift = live_index != manifest.get("source_index")
    image_now = docker_image_id(manifest.get("docker_image_name") or "python:3.12-slim")
    computed_hashes = task_hashes()
    manifest_hashes = manifest.get("task_hashes") or {}
    rows = []
    for item in assignments:
        rows.append(audit_one(dest_for(run_root, item), item))
    hash_mismatches = []
    for rec in rows:
        tid = rec.get("task_id")
        got = rec.get("task_hash_result")
        want = computed_hashes.get(tid)
        if got and want and got != want:
            hash_mismatches.append(rec["allocation_id"])
    issues = [r for r in rows if r.get("issues")]
    statuses = Counter(r.get("status") for r in rows)
    import hashlib
    manifest_sha = hashlib.sha256((run_root / "manifest.json").read_bytes()).hexdigest()
    candidates = [r["allocation_id"] for r in rows if r.get("leak_candidates")]
    adjudication = {
        "method": "candidates are assistant-role text only; user/system protocol mentions of Hidden acceptance are not leaks. Hits that do not contain evaluator module names or mutant labels are generic participant reasoning.",
    }
    for rec in rows:
        if rec.get("leak_candidates") and rec["allocation_id"] not in (r["allocation_id"] for r in rows if r.get("hidden_leak_in_requests")):
            adjudication[rec["allocation_id"]] = "false_positive: assistant discussed hidden tests generically; evaluator sources not present"
    report = {
        "at": datetime.now(timezone.utc).isoformat(),
        "run_root": str(run_root),
        "assignments": len(assignments),
        "unique": len({a["allocation_id"] for a in assignments}),
        "counts": counts(run_root, assignments),
        "statuses": dict(statuses),
        "freeze_verified": True,
        "live_source_drift": drift,
        "task_hash_catalog_vs_manifest": computed_hashes != manifest_hashes,
        "task_hash_result_mismatches": hash_mismatches,
        "task_hash_drift": computed_hashes != manifest_hashes or bool(hash_mismatches),
        "manifest_sha256": manifest_sha,
        "manifest_sha256_matches_first12": manifest_sha == FIRST12_MANIFEST_SHA256,
        "leak_candidates": candidates,
        "leak_adjudication": adjudication,
        "docker_image_id_manifest": manifest.get("docker_image_id"),
        "docker_image_id_now": image_now,
        "docker_image_id_matches": image_now == manifest.get("docker_image_id"),
        "image_runtime_caveat": "common.py launches with tag python:3.12-slim; runner checks digest at batch boundary only",
        "usage_mismatches": [r["allocation_id"] for r in rows if "usage_mismatch" in r.get("issues", [])],
        "cache_mismatches": [r["allocation_id"] for r in rows if "cache_mismatch" in r.get("issues", [])],
        "leaks": [r["allocation_id"] for r in rows if r.get("hidden_leak_in_requests")],
        "issue_rows": [{k: r[k] for k in ("allocation_id", "status", "issues")} for r in issues],
        "n_ok": sum(1 for r in rows if r.get("ok")),
        "rows": rows,
    }
    return report


if __name__ == "__main__":
    run = ROOT / "runs" / "20260913T023645Z"
    report = run_audit(run)
    out = ROOT / "report" / "audit360.json"
    slim = dict(report)
    # keep full rows; file is the audit record
    out.write_text(json.dumps(slim, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: slim[k] for k in slim if k != "rows"}, indent=2, default=str))
