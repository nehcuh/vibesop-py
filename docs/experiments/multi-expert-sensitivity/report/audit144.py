"""144-cohort audit. Presentation layer; does not change frozen analysis."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness.pack import docker_image_id, file_index, task_hashes, verify_pack
from harness.schedule import counts, dest_for

LEAK_CANDIDATE_PHRASES = ("hidden acceptance", "hidden eval", "hidden tests")
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
    rec["n_soft_closes"] = len(result.get("soft_closes") or (result.get("recorder") or {}).get("soft_closes") or [])
    rec["flow_arm"] = result.get("flow_arm")
    requests = sorted(dest.glob("call-*-request.json"))
    responses = {p.name.replace("response", "request"): p for p in dest.glob("call-*-response.json")}
    errors = {p.name.replace("error", "request"): p for p in dest.glob("call-*-error.json")}
    rec["n_request"] = len(requests)
    rec["n_response"] = len(responses)
    rec["n_error"] = len(errors)
    ids = []
    prompt = completion = cache = reasoning = 0
    leak = False
    rec["leak_candidates"] = []
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
        for msg in data.get("messages") or []:
            if not isinstance(msg, dict) or msg.get("role") != "assistant":
                continue
            text = json.dumps(msg, ensure_ascii=False).lower()
            hits = [p for p in LEAK_CANDIDATE_PHRASES if p in text]
            if hits:
                rec["leak_candidates"].append({"request": req.name, "phrases": hits, "role": "assistant"})
        key = req.name
        has_resp = key in responses
        has_err = key in errors
        if has_resp == has_err:
            if rec.get("status") == "interrupted" and not has_resp and not has_err:
                rec["issues"].append("expected_interrupt_open_request:" + req.name)
            else:
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
    if rec.get("status") == "interrupted" and not led:
        rec["usage_match"] = None
        rec["issues"].append("expected_interrupt_no_ledger")
        rec["raw_usage_is_lower_bound"] = True
    else:
        rec["usage_match"] = prompt == led.get("used_i") and completion == led.get("used_t")
        if not rec["usage_match"]:
            rec["issues"].append("usage_mismatch")
    rec["hidden_leak_in_requests"] = leak
    if leak:
        rec["issues"].append("hidden_leak")
    rec["cache_in_ledger_events"] = led.get("cache_hit")
    if rec.get("status") == "interrupted" and not led:
        rec["cache_match"] = None
    elif led.get("cache_hit") not in (None, cache):
        rec["issues"].append("cache_mismatch")
        rec["cache_match"] = False
    else:
        rec["cache_match"] = True
    if rec.get("arm") == "D_soft":
        caps = led.get("stage_cap") or {}
        if rec.get("status") == "interrupted" and not led:
            rec["issues"].append("expected_interrupt_no_stage_caps_in_result")
        elif not caps.get("independent-0"):
            rec["issues"].append("dsoft_missing_D_stage_caps")
        if rec.get("flow_arm") not in (None, "D"):
            rec["issues"].append("dsoft_flow_arm_not_D")
    if rec.get("arm") == "A":
        if led.get("stage_cap"):
            rec["issues"].append("A_unexpected_stage_caps")
        if rec["n_soft_closes"]:
            rec["issues"].append("A_unexpected_soft_close")
    ws = dest / "workspace"
    if ws.is_dir():
        for name in ("oracles.py", "cases.py", "evaluate.py"):
            if (ws / name).exists():
                rec["issues"].append("workspace_hidden_file:" + name)
    rec["expected_interrupt_issues"] = [
        x for x in rec["issues"] if x.startswith("expected_interrupt_")
    ]
    rec["unexpected_issues"] = [
        x for x in rec["issues"] if not x.startswith("expected_interrupt_")
    ]
    rec["ok"] = not rec["unexpected_issues"]
    rec["models"] = list(rec["models"])
    return rec


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
    manifest_sha = hashlib.sha256((run_root / "manifest.json").read_bytes()).hexdigest()
    candidates = [r["allocation_id"] for r in rows if r.get("leak_candidates")]
    return {
        "at": datetime.now(timezone.utc).isoformat(),
        "run_root": str(run_root),
        "phase": manifest.get("phase"),
        "label": manifest.get("label"),
        "exploratory": True,
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
        "leak_candidates": candidates,
        "leak_adjudication": {
            "method": "candidates are assistant-role text only; user/system protocol mentions of Hidden acceptance are not leaks",
        },
        "docker_image_id_manifest": manifest.get("docker_image_id"),
        "docker_image_id_now": image_now,
        "docker_image_id_matches": image_now == manifest.get("docker_image_id"),
        "image_runtime_caveat": "common.py launches with tag python:3.12-slim; runner checks digest at batch boundary only",
        "usage_mismatches": [r["allocation_id"] for r in rows if "usage_mismatch" in r.get("issues", [])],
        "cache_mismatches": [r["allocation_id"] for r in rows if "cache_mismatch" in r.get("issues", [])],
        "leaks": [r["allocation_id"] for r in rows if r.get("hidden_leak_in_requests")],
        "issue_rows": [{k: r[k] for k in ("allocation_id", "status", "issues")} for r in issues],
        "n_ok": sum(1 for r in rows if r.get("ok")),
        "n_soft_close_rows": sum(1 for r in rows if r.get("n_soft_closes")),
        "n_interrupted": sum(1 for r in rows if r.get("status") == "interrupted"),
        "n_expected_interrupt_issue_rows": sum(1 for r in rows if r.get("expected_interrupt_issues")),
        "n_open_http_requests": sum(
            1
            for r in rows
            for x in r.get("issues") or []
            if x.startswith("expected_interrupt_open_request:")
        ),
        "n_unexpected_issue_rows": sum(1 for r in rows if r.get("unexpected_issues")),
        "log_completeness": "not_144_of_144; interrupted rows lack ledger and 7 lack final HTTP response",
        "rows": rows,
    }


if __name__ == "__main__":
    runs = sorted((ROOT / "runs").glob("*/manifest.json"))
    if not runs:
        raise SystemExit("no_sensitivity_run")
    run = runs[-1].parent
    report = run_audit(run)
    out = ROOT / "report" / "audit144.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: report[k] for k in report if k != "rows"}, indent=2, default=str))
