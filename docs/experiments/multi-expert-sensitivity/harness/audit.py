"""FIRST12_AUDIT.md: ledger vs raw usage, freeze drift, no hidden leak."""
from __future__ import annotations

import json
from pathlib import Path

from .pack import file_index, verify_pack
from .schedule import counts


def _usage_from_responses(dest: Path) -> tuple[int, int]:
    prompt = completion = 0
    for path in dest.glob("call-*-response.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        usage = data.get("usage") or {}
        prompt += int(usage.get("prompt_tokens") or 0)
        completion += int(usage.get("completion_tokens") or 0)
    return prompt, completion


def write_first12_audit(run_root: Path, live_root: Path) -> dict:
    run_root = Path(run_root)
    manifest = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
    assignments = manifest["assignments"]
    if len(assignments) != 360:
        raise RuntimeError("audit_manifest_not_360")
    verify_pack(run_root / "frozen-sources", live_root)
    batch = json.loads((run_root / "batch.json").read_text(encoding="utf-8"))
    selected = batch.get("selected") or []
    rows = []
    mismatches = []
    leaks = []
    for alloc in selected:
        dest = run_root / alloc
        result_path = dest / "result.json"
        rec = {"allocation_id": alloc, "result": result_path.is_file()}
        if result_path.is_file():
            data = json.loads(result_path.read_text(encoding="utf-8"))
            rec["status"] = data.get("status")
            led = data.get("ledger") or {}
            p, c = _usage_from_responses(dest)
            rec["ledger_i"] = led.get("used_i")
            rec["ledger_t"] = led.get("used_t")
            rec["raw_i"] = p
            rec["raw_t"] = c
            rec["ledger_match"] = p == led.get("used_i") and c == led.get("used_t")
            if not rec["ledger_match"]:
                mismatches.append(alloc)
            hidden_names = ("oracles.py", "cases.py", "evaluate.py", "qa_bank.py")
            ws = dest / "workspace"
            if ws.is_dir():
                for name in hidden_names:
                    if (ws / name).exists():
                        leaks.append(f"{alloc}/{name}")
        rows.append(rec)
    live = file_index(live_root)
    drifted = live != manifest.get("source_index")
    next_cmd = (
        "PYTHONPATH=docs/experiments/multi-expert-formal uv run python -m harness.runner "
        f"--phase formal --i-understand-formal --resume {run_root} --max-new 12"
    )
    md = [
        "# FIRST12_AUDIT",
        "",
        f"- manifest assignments: {len(assignments)} (must be 360)",
        f"- this batch: {len(selected)}",
        f"- freeze verify: ok",
        f"- live vs freeze drift: {drifted}",
        f"- ledger mismatches: {mismatches or 'none'}",
        f"- hidden evaluator leaked into workspace: {leaks or 'none'}",
        f"- counts: {counts(run_root, assignments)}",
        "",
        "## 下一条 resume 命令",
        "",
        "```bash",
        next_cmd,
        "```",
        "",
        "不重抽任务。不以胜负为停止理由。",
    ]
    (run_root / "FIRST12_AUDIT.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (live_root / "FIRST12_AUDIT.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return {"rows": rows, "mismatches": mismatches, "leaks": leaks, "drifted": drifted, "next": next_cmd}
