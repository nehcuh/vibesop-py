"""Participant-model inference cost estimates. Not an invoice.

Excludes Grok implementation, Codex supervision, Docker, and human time.
"""
from __future__ import annotations

import json
from pathlib import Path

PRICE = {"miss": 0.15, "hit": 0.003, "out": 0.6, "source": "https://api-docs.deepseek.com/quick_start/pricing/"}
ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT.parent


def usd(miss: float, hit: float, out: float) -> float:
    return (miss * PRICE["miss"] + hit * PRICE["hit"] + out * PRICE["out"]) / 1e6


def _from_result(path: Path) -> dict | None:
    data = json.loads(path.read_text(encoding="utf-8"))
    led = data.get("ledger") or {}
    t, i, c = led.get("used_t"), led.get("used_i"), led.get("cache_hit")
    if t is None and i is None:
        return None
    return {"T": int(t or 0), "I": int(i or 0), "cache": int(c or 0), "src": "ledger"}


def _from_responses(dest: Path) -> dict:
    t = i = c = 0
    for path in dest.glob("call-*-response.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        usage = data.get("usage") or {}
        i += int(usage.get("prompt_tokens") or 0)
        t += int(usage.get("completion_tokens") or 0)
        c += int(usage.get("prompt_cache_hit_tokens") or 0)
    return {"T": t, "I": i, "cache": c, "src": "responses"}


def sum_run(run_root: Path) -> dict:
    run_root = Path(run_root)
    rows = []
    for path in sorted(run_root.glob("*/result.json")):
        if path.parent.name == "frozen-sources":
            continue
        got = _from_result(path)
        if got is None or (got["T"] == 0 and got["I"] == 0):
            got = _from_responses(path.parent)
        rows.append(got)
    t = sum(r["T"] for r in rows)
    i = sum(r["I"] for r in rows)
    c = sum(r["cache"] for r in rows)
    miss = i - c
    return {
        "n": len(rows),
        "T": t,
        "I": i,
        "cache": c,
        "miss": miss,
        "usd": usd(miss, c, t),
        "run_root": str(run_root),
        "scope": "participant_model_inference_only",
        "excludes": ["grok_implementation", "codex_supervision", "docker_host", "human_time"],
        "price": PRICE,
    }


def cohort_costs() -> dict:
    cal = WORK / "multi-expert-calibration" / "runs"
    formal = ROOT / "runs"
    old = [sum_run(p) for p in sorted(cal.iterdir()) if p.is_dir() and (p / "manifest.json").is_file()]
    informal = [
        sum_run(formal / "20260913T015759Z"),
        sum_run(formal / "20260913T020657Z"),
    ]
    primary = sum_run(formal / "20260913T023645Z")
    old_usd = sum(x["usd"] for x in old)
    inf_usd = sum(x["usd"] for x in informal)
    return {
        "calibration_old_45": {"parts": old, "n": sum(x["n"] for x in old), "usd": old_usd},
        "calibration_informal_30": {"parts": informal, "n": sum(x["n"] for x in informal), "usd": inf_usd},
        "calibration_75": {"n": sum(x["n"] for x in old) + sum(x["n"] for x in informal), "usd": old_usd + inf_usd},
        "primary_360": primary,
        "note": "75 = 45 old executor + 30 new-executor informal. None are 360 samples.",
    }


if __name__ == "__main__":
    print(json.dumps(cohort_costs(), indent=2, default=str))
