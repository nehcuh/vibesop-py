"""Derive usage lower bounds for controller-interrupted allocations.

Does not rewrite raw result.json / request / response files.
Interrupted result.json has no final ledger; treating that as 0 usage is wrong.
Missing in-flight HTTP responses may have been billed; their tokens are unknown
and are not fabricated as 0.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRICE = {
    "miss": 0.15,
    "hit": 0.003,
    "out": 0.6,
    "source": "https://api-docs.deepseek.com/quick_start/pricing/",
}
AUDIT = ROOT / "report" / "interruption-audit"


def usd(miss: float, hit: float, out: float) -> float:
    return (miss * PRICE["miss"] + hit * PRICE["hit"] + out * PRICE["out"]) / 1e6


def _call_id(path: Path) -> int | None:
    m = re.search(r"call-(\d+)-(request|response|error)", path.name)
    return int(m.group(1)) if m else None


def _usage_from_response(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    u = data.get("usage") or {}
    details = u.get("completion_tokens_details") or {}
    prompt = int(u.get("prompt_tokens") or 0)
    completion = int(u.get("completion_tokens") or 0)
    cache = int(u.get("prompt_cache_hit_tokens") or 0)
    reasoning = int(details.get("reasoning_tokens") or 0)
    return {
        "file": path.name,
        "call_id": _call_id(path),
        "model": data.get("model"),
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "prompt_cache_hit_tokens": cache,
        "prompt_cache_miss_tokens": prompt - cache,
        "reasoning_tokens": reasoning,
        "has_usage": bool(u),
    }


def _open_request_meta(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "file": path.name,
        "call_id": data.get("call_id"),
        "stage": data.get("stage"),
        "member": data.get("member"),
        "model": data.get("model"),
        "max_tokens": data.get("max_tokens"),
        "started_at": data.get("started_at"),
        "http_response": "missing_may_have_been_billed",
        "usage": "unknown_not_zero",
    }


def derive_one(dest: Path) -> dict:
    dest = Path(dest)
    result = json.loads((dest / "result.json").read_text(encoding="utf-8"))
    requests = sorted(dest.glob("call-*-request.json"), key=lambda p: _call_id(p) or -1)
    responses = { _call_id(p): p for p in dest.glob("call-*-response.json") }
    errors = { _call_id(p): p for p in dest.glob("call-*-error.json") }
    tools_path = dest / "tools.jsonl"
    tool_events = []
    if tools_path.is_file():
        for line in tools_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            ev = json.loads(line)
            tool_events.append({
                "seq": ev.get("seq"),
                "call_id": ev.get("call_id"),
                "tool": ev.get("tool"),
                "stage": ev.get("stage"),
                "ok": ev.get("ok"),
            })
    usage_rows = []
    open_requests = []
    for req in requests:
        cid = _call_id(req)
        if cid in responses:
            usage_rows.append(_usage_from_response(responses[cid]))
        elif cid in errors:
            open_requests.append({
                **_open_request_meta(req),
                "http_response": "error_file_present",
                "error_file": errors[cid].name,
            })
        else:
            open_requests.append(_open_request_meta(req))
    prompt = sum(r["prompt_tokens"] for r in usage_rows)
    completion = sum(r["completion_tokens"] for r in usage_rows)
    cache = sum(r["prompt_cache_hit_tokens"] for r in usage_rows)
    reasoning = sum(r["reasoning_tokens"] for r in usage_rows)
    miss = prompt - cache
    return {
        "allocation_id": dest.name,
        "status": result.get("status"),
        "error": result.get("error"),
        "arm": result.get("arm"),
        "task_id": result.get("task_id"),
        "spec_variant": result.get("spec_variant"),
        "repeat": result.get("repeat"),
        "rerun": result.get("rerun"),
        "started_at": result.get("started_at"),
        "interrupted_at": result.get("interrupted_at"),
        "has_ledger": result.get("ledger") not in (None, {}),
        "ledger": result.get("ledger"),
        "n_request_files": len(requests),
        "n_response_files": len(responses),
        "n_error_files": len(errors),
        "n_tools_jsonl_events": len(tool_events),
        "n_open_http_requests": len(open_requests),
        "open_http_requests": open_requests,
        "persisted_response_usage": usage_rows,
        "derived_known": {
            "source": "sum_of_persisted_call_star_response_json_usage_plus_tools_jsonl_event_count",
            "bound": "lower_bound_not_invoice",
            "T_completion": completion,
            "I_prompt": prompt,
            "cache_hit": cache,
            "cache_miss": miss,
            "reasoning": reasoning,
            "K_tools_jsonl": len(tool_events),
            "est_usd": usd(miss, cache, completion),
        },
        "unknown": {
            "in_flight_http": len(open_requests),
            "tokens_for_open_requests": "unknown_may_have_been_charged_do_not_record_as_0",
            "unpersisted_subsequent_requests": "possible_if_killed_before_request_json",
        },
        "models": sorted({r["model"] for r in usage_rows if r.get("model")}),
        "cause": "grok_headless_background_wait_timeout_600s_killed_runner_not_deepseek_api_or_model_failure",
    }


def derive_run(run_root: Path) -> dict:
    run_root = Path(run_root)
    interrupted_path = run_root / "interrupted.json"
    ids = json.loads(interrupted_path.read_text(encoding="utf-8"))["ids"]
    rows = [derive_one(run_root / aid) for aid in ids]
    known_t = sum(r["derived_known"]["T_completion"] for r in rows)
    known_i = sum(r["derived_known"]["I_prompt"] for r in rows)
    known_c = sum(r["derived_known"]["cache_hit"] for r in rows)
    known_k = sum(r["derived_known"]["K_tools_jsonl"] for r in rows)
    n_open = sum(r["n_open_http_requests"] for r in rows)
    n_paired = sum(1 for r in rows if r["n_open_http_requests"] == 0)
    return {
        "at": datetime.now(timezone.utc).isoformat(),
        "run_root": str(run_root),
        "label": "controller_interruption_usage_lower_bound",
        "not_a_substitute_for_preregistered_stats": True,
        "do_not_treat_missing_ledger_as_zero_usage": True,
        "do_not_claim_all_calls_have_responses": True,
        "n_interrupted": len(rows),
        "n_dsoft": sum(1 for r in rows if r.get("arm") == "D_soft"),
        "n_A": sum(1 for r in rows if r.get("arm") == "A"),
        "n_with_open_http": sum(1 for r in rows if r["n_open_http_requests"] > 0),
        "n_all_persisted_calls_have_response": n_paired,
        "n_open_http_requests": n_open,
        "derived_known_sum": {
            "T_completion": known_t,
            "I_prompt": known_i,
            "cache_hit": known_c,
            "cache_miss": known_i - known_c,
            "K_tools_jsonl": known_k,
            "est_usd": usd(known_i - known_c, known_c, known_t),
            "bound": "lower_bound",
        },
        "unknown_billable": {
            "n_open_http_requests": n_open,
            "usage": "unknown",
            "note": "Request JSON was persisted; HTTP may have completed and been charged without a saved response. Do not record as 0.",
        },
        "price": PRICE,
        "scope": "participant_model_inference_only",
        "excludes": ["grok_implementation", "codex_supervision", "docker_host", "human_time"],
        "rows": rows,
        "snapshots": str(AUDIT / "running-snapshots-before-resume"),
        "snapshot_index": str(AUDIT / "running-snapshot-index.json"),
    }


def write_outputs(report: dict) -> None:
    AUDIT.mkdir(parents=True, exist_ok=True)
    (AUDIT / "derived-usage.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    lines = [
        "# 控制器中断用量派生（已知下界）",
        "",
        "原始 `result.json` / request / response **未改写**。本文件从已持久化 `call-*-response.json` 的 `usage` 与 `tools.jsonl` 另行派生。",
        "",
        "- 8 个 interrupted 分配的 `result.json` **没有最终 ledger**，不能在报告里当成用量 0。",
        f"- {report['n_with_open_http']} 个分配缺最后一次 HTTP 响应；这些请求**可能已计费，token 未知，不能编造为 0**。",
        f"- {report['n_all_persisted_calls_have_response']} 个分配的已落盘 request 均有 response（`route-priority-table-v1-brief-D_soft-r0`），但仍无 ledger、跑程未终裁，派生值仍标下界。",
        "- 中断原因：Grok headless 后台等待 600s 超时杀进程。不是 DeepSeek API 失败，不是模型能力失败，不把 7 个 D_soft / 1 个 A 记成编排缺陷。",
        "",
        f"已知下界合计：T={report['derived_known_sum']['T_completion']}，"
        f"I={report['derived_known_sum']['I_prompt']}，"
        f"cache_hit={report['derived_known_sum']['cache_hit']}，"
        f"K_tools.jsonl={report['derived_known_sum']['K_tools_jsonl']}，"
        f"估算 USD={report['derived_known_sum']['est_usd']:.4f}（非发票）。",
        "",
        f"未知：{report['n_open_http_requests']} 次已写 request、无 response 的 HTTP。",
        "",
        "| 分配 | 组 | req | resp | 开放HTTP | 已知T | 已知I | cache | K | 估算USD |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in report["rows"]:
        k = r["derived_known"]
        lines.append(
            f"| `{r['allocation_id']}` | {r['arm']} | {r['n_request_files']} | "
            f"{r['n_response_files']} | {r['n_open_http_requests']} | {k['T_completion']} | "
            f"{k['I_prompt']} | {k['cache_hit']} | {k['K_tools_jsonl']} | {k['est_usd']:.4f} |"
        )
    lines.append("")
    (AUDIT / "derived-usage.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def latest_run() -> Path:
    runs = sorted((ROOT / "runs").glob("*/manifest.json"))
    if not runs:
        raise RuntimeError("no_sensitivity_run")
    return runs[-1].parent


if __name__ == "__main__":
    run = latest_run()
    report = derive_run(run)
    write_outputs(report)
    slim = {k: report[k] for k in report if k != "rows"}
    slim["row_ids"] = [r["allocation_id"] for r in report["rows"]]
    print(json.dumps(slim, indent=2, default=str))
