"""Frozen D−A cluster bootstrap. Do not change after formal results exist."""
from __future__ import annotations

import json
import math
import random
from collections import defaultdict

BOOTSTRAP_N = 20000
BOOTSTRAP_SEED = 20260913
THRESHOLD = 0.10
ARMS_MAIN = ("D", "A")


def percentile(sorted_xs: list[float], p: float) -> float:
    """Linear interpolation between adjacent order statistics. p in [0, 1]."""
    if not sorted_xs:
        raise ValueError("empty")
    if p <= 0:
        return sorted_xs[0]
    if p >= 1:
        return sorted_xs[-1]
    k = (len(sorted_xs) - 1) * p
    lo = int(math.floor(k))
    hi = int(math.ceil(k))
    if lo == hi:
        return sorted_xs[lo]
    w = k - lo
    return sorted_xs[lo] * (1 - w) + sorted_xs[hi] * w


def success_bit(row: dict) -> float:
    return 1.0 if row.get("status") == "passed" else 0.0


def pair_key(row: dict) -> tuple:
    return (row["task_id"], row["spec_variant"], int(row["repeat"]))


def task_mean_diffs(rows: list[dict], high: str = "D", low: str = "A") -> dict[str, float]:
    """Per-task mean of up to 6 (spec × repeat) paired differences high-low.

    Missing pairs are skipped; a task with no pair is omitted. Failures count 0.
    """
    by = defaultdict(dict)
    for row in rows:
        if row.get("arm") not in {high, low}:
            continue
        by[pair_key(row)][row["arm"]] = success_bit(row)
    acc: dict[str, list[float]] = defaultdict(list)
    for (task_id, _spec, _repeat), arms in by.items():
        if high in arms and low in arms:
            acc[task_id].append(arms[high] - arms[low])
    return {task: sum(vals) / len(vals) for task, vals in acc.items() if vals}


def grand_mean(task_means: dict[str, float]) -> float:
    if not task_means:
        raise ValueError("no_task_means")
    return sum(task_means.values()) / len(task_means)


def cluster_bootstrap(
    task_means: dict[str, float],
    *,
    n: int = BOOTSTRAP_N,
    seed: int = BOOTSTRAP_SEED,
) -> dict:
    tasks = sorted(task_means)
    k = len(tasks)
    if k == 0:
        raise ValueError("no_tasks")
    rng = random.Random(seed)
    samples = []
    values = [task_means[t] for t in tasks]
    for _ in range(n):
        draw = [values[rng.randrange(k)] for _ in range(k)]
        samples.append(sum(draw) / k)
    samples.sort()
    lo = percentile(samples, 0.025)
    hi = percentile(samples, 0.975)
    point = grand_mean(task_means)
    return {
        "n_tasks": k,
        "n_bootstrap": n,
        "seed": seed,
        "point": point,
        "ci95": [lo, hi],
        "task_means": {t: task_means[t] for t in tasks},
        "interpretation": interpret(lo, hi),
        "threshold": THRESHOLD,
        "method": "cluster_bootstrap_percentile_resample_tasks_with_replacement_keep_all_spec_repeat",
    }


def interpret(lo: float, hi: float, threshold: float = THRESHOLD) -> str:
    if lo > threshold:
        return "support_adoption_threshold"
    if hi < 0:
        return "support_worse"
    if lo > 0 and hi < threshold:
        return "small_positive_below_threshold"
    if hi < threshold:
        return "rules_out_minimum_gain"
    return "unresolved"


def da_from_results(rows: list[dict]) -> dict:
    means = task_mean_diffs(rows, "D", "A")
    result = cluster_bootstrap(means)
    result["comparison"] = "D-A"
    result["confirmatory"] = True
    return result


def toy_self_check() -> dict:
    checks = []

    def row(task, spec, repeat, arm, status):
        return {"task_id": task, "spec_variant": spec, "repeat": repeat, "arm": arm, "status": status}

    tasks = [f"t{i}" for i in range(12)]
    specs = ("full", "brief")

    def battery(d_status, a_status):
        rows = []
        for t in tasks:
            for spec in specs:
                for r in range(3):
                    rows.append(row(t, spec, r, "D", d_status))
                    rows.append(row(t, spec, r, "A", a_status))
        return rows

    all_d = da_from_results(battery("passed", "failed"))
    checks.append({
        "name": "all_d_win_mean_1",
        "passed": abs(all_d["point"] - 1) < 1e-12 and all_d["ci95"][0] > 0.10,
        "detail": all_d,
    })
    all_tie = da_from_results(battery("passed", "passed"))
    checks.append({
        "name": "all_tie_mean_0",
        "passed": abs(all_tie["point"]) < 1e-12 and all_tie["interpretation"] in {"rules_out_minimum_gain", "unresolved"},
        "detail": {"point": all_tie["point"], "ci": all_tie["ci95"], "interp": all_tie["interpretation"]},
    })
    all_a = da_from_results(battery("failed", "passed"))
    checks.append({
        "name": "all_a_win_negative",
        "passed": abs(all_a["point"] + 1) < 1e-12 and all_a["interpretation"] == "support_worse",
        "detail": all_a["interpretation"],
    })
    mixed = []
    for t in tasks:
        for spec in specs:
            for r in range(3):
                mixed.append(row(t, spec, r, "D", "error" if t != "t0" else "passed"))
                mixed.append(row(t, spec, r, "A", "failed"))
    one_task = da_from_results(mixed)
    checks.append({
        "name": "cluster_one_task_mean_1_over_12",
        "passed": abs(one_task["point"] - (1 / 12)) < 1e-12 and one_task["n_tasks"] == 12,
        "detail": one_task["point"],
    })
    checks.append({
        "name": "error_counts_as_zero",
        "passed": abs(one_task["task_means"]["t1"]) < 1e-12 and abs(one_task["task_means"]["t0"] - 1) < 1e-12,
        "detail": one_task["task_means"],
    })
    small = cluster_bootstrap({f"t{i}": 0.05 for i in range(12)})
    checks.append({
        "name": "interval_in_0_10_small_positive",
        "passed": small["interpretation"] == "small_positive_below_threshold"
        and small["ci95"][0] > 0 and small["ci95"][1] < 0.10,
        "detail": small,
    })
    checks.append({
        "name": "seed_reproducible",
        "passed": cluster_bootstrap({f"t{i}": 0.05 for i in range(12)})["ci95"] == small["ci95"],
        "detail": small["ci95"],
    })
    checks.append({
        "name": "interrupted_is_zero",
        "passed": success_bit({"status": "interrupted"}) == 0 and success_bit({"status": "error"}) == 0,
        "detail": "ok",
    })
    return {"passed": all(c["passed"] for c in checks), "checks": checks}


if __name__ == "__main__":
    report = toy_self_check()
    print(json.dumps({"passed": report["passed"],
                      "failed": [c["name"] for c in report["checks"] if not c["passed"]]}, indent=2))
    raise SystemExit(0 if report["passed"] else 1)
