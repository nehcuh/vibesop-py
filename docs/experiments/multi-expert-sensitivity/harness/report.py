"""Chinese REPORT.md plus machine-readable tables. Not a live judge."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from .analysis import da_from_results, success_bit, task_mean_diffs


def _svg_bars(title: str, labels: list[str], values: list[float], path: Path) -> None:
    width = 720
    height = 40 + 28 * max(len(labels), 1)
    bars = []
    for i, (lab, val) in enumerate(zip(labels, values)):
        y = 30 + i * 28
        w = max(0, min(400, val * 400))
        bars.append(
            f'<text x="8" y="{y + 12}" font-size="12">{lab}</text>'
            f'<rect x="200" y="{y}" width="{w:.1f}" height="16" fill="#4c78a8"/>'
            f'<text x="{208 + w:.1f}" y="{y + 12}" font-size="11">{val:.2f}</text>'
        )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">'
        f'<text x="8" y="18" font-size="14">{title}</text>'
        + "".join(bars)
        + "</svg>"
    )
    path.write_text(svg, encoding="utf-8")


def classify_failure(row: dict) -> str:
    if row.get("status") == "passed":
        return "passed"
    err = str(row.get("error") or "")
    if row.get("status") == "interrupted":
        return "interrupted"
    if "budget_exhausted" in err or "stage_budget_exhausted" in err:
        return "resource"
    if "ownership_conflict" in err or "invalid_decomposition" in err:
        return "protocol"
    if row.get("status") == "error":
        return "error"
    if row.get("evaluation") is None:
        return "no_hidden_eval"
    return "hidden_failed"


def collect(run_root: Path) -> list[dict]:
    rows = []
    manifest = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
    for item in manifest["assignments"]:
        dest = run_root / item["allocation_id"]
        result_path = dest / "result.json"
        if not result_path.is_file():
            rows.append({**item, "status": "pending", "ledger": {}, "evaluation": None})
            continue
        data = json.loads(result_path.read_text(encoding="utf-8"))
        data.update({k: item[k] for k in ("task_id", "arm", "spec_variant", "repeat", "allocation_id") if k in item})
        rows.append(data)
    return rows


def write_report(run_root: Path) -> dict:
    run_root = Path(run_root)
    rows = collect(run_root)
    figures = run_root / "figures"
    figures.mkdir(exist_ok=True)
    by_arm = defaultdict(list)
    for row in rows:
        by_arm[row.get("arm", "?")].append(success_bit(row))
    labels = sorted(by_arm)
    rates = [sum(by_arm[a]) / len(by_arm[a]) if by_arm[a] else 0 for a in labels]
    _svg_bars("通过率（按组，非独立样本）", labels, rates, figures / "pass_by_arm.svg")
    costs = []
    for a in labels:
        toks = [((r.get("ledger") or {}).get("used_t") or 0) for r in rows if r.get("arm") == a]
        costs.append((sum(toks) / len(toks) / 1000) if toks else 0)
    _svg_bars("平均输出 token（千，按组）", labels, costs, figures / "t_by_arm.svg")
    da = None
    try:
        da = da_from_results(rows)
    except ValueError:
        da = {"point": None, "ci95": None, "interpretation": "insufficient_pairs"}
    tables = {
        "by_arm": {a: {"n": len(by_arm[a]), "pass": sum(by_arm[a]), "rate": rates[i]} for i, a in enumerate(labels)},
        "failures": defaultdict(int),
        "da": da,
    }
    for row in rows:
        tables["failures"][classify_failure(row)] += 1
    tables["failures"] = dict(tables["failures"])
    (run_root / "results.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False, default=str) + "\n" for r in rows),
        encoding="utf-8",
    )
    (run_root / "analysis.json").write_text(json.dumps(tables, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    n_done = sum(1 for r in rows if r.get("status") in {"passed", "failed", "error", "interrupted"})
    md = [
        "# 多专家组织对照：正式报告",
        "",
        "这是受控小型 CLI 基准，不是异质专家团队、也不是整库工程的结论。",
        "主比较是 **D−A**；规格与重复不是独立任务。失败/error/interrupted 记 0。",
        "",
        f"- 分配 {len(rows)}，已结束 {n_done}。",
        f"- 主差值点估计：{da.get('point')}；95% 区间：{da.get('ci95')}；判定：{da.get('interpretation')}。",
        f"- 失败分类：{tables['failures']}。",
        "",
        "没有 hidden evaluation 的失败，不称为实现 bug。",
        "图见 `figures/`。机器可读结果见 `results.jsonl` 与 `analysis.json`。",
    ]
    (run_root / "REPORT.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return tables
