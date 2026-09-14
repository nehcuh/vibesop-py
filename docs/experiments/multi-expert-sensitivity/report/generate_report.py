"""Sensitivity Chinese REPORT. Exploratory; does not rewrite primary 360 numbers."""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter, defaultdict  # defaultdict used by complete_case_da
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness.analysis import da_from_results
from report.audit144 import run_audit
from report.collect import classify, load_rows, reached_hidden, reached_integrate, remap_dsoft_for_frozen_analysis
from report.derive_interrupt_usage import derive_run, write_outputs
from report.plot import da_forest, fail_mix, pass_by_arm, resources_by_arm, task_heatmap

PRICE = {"miss": 0.15, "hit": 0.003, "out": 0.6, "source": "https://api-docs.deepseek.com/quick_start/pricing/"}


def latest_run() -> Path:
    runs = sorted((ROOT / "runs").glob("*/manifest.json"))
    if not runs:
        raise RuntimeError("no_sensitivity_run")
    return runs[-1].parent


def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def pct(x):
    return f"{100 * x:.1f}%"


def usd(miss, hit, out):
    return (miss * PRICE["miss"] + hit * PRICE["hit"] + out * PRICE["out"]) / 1e6


def ledger_cache(row):
    return (row.get("ledger") or {}).get("cache_hit") or 0


def ledger_rows(xs):
    """Rows with a final ledger. Interrupted running snapshots have none; do not impute 0."""
    return [r for r in xs if r.get("status") != "interrupted" and (r.get("ledger") or {}).get("used_t") is not None]


def summarize_arm(rows, arm):
    xs = [r for r in rows if r.get("arm") == arm]
    billed = ledger_rows(xs)
    t = [((r.get("ledger") or {}).get("used_t") or 0) for r in billed]
    i = [((r.get("ledger") or {}).get("used_i") or 0) for r in billed]
    k = [((r.get("ledger") or {}).get("used_k") or 0) for r in billed]
    c = [ledger_cache(r) for r in billed]
    miss = [ii - cc for ii, cc in zip(i, c)]
    n_int = sum(1 for r in xs if r.get("status") == "interrupted")
    return {
        "n": len(xs),
        "n_ledger": len(billed),
        "n_interrupted": n_int,
        "pass": sum(1 for r in xs if r.get("status") == "passed"),
        "rate": mean([1.0 if r.get("status") == "passed" else 0.0 for r in xs]),
        "hidden": mean([1.0 if reached_hidden(r) else 0.0 for r in xs]),
        "integrate": mean([1.0 if reached_integrate(r) else 0.0 for r in xs]),
        "soft_close": sum(1 for r in xs if (r.get("soft_closes") or (r.get("recorder") or {}).get("soft_closes"))),
        "T_mean": mean(t),
        "T_median": statistics.median(t) if t else 0,
        "I_mean": mean(i),
        "I_median": statistics.median(i) if i else 0,
        "K_mean": mean(k),
        "K_median": statistics.median(k) if k else 0,
        "cache_mean": mean(c),
        "T_sum": sum(t),
        "I_sum": sum(i),
        "K_sum": sum(k),
        "cache_sum": sum(c),
        "miss_sum": sum(miss),
        "est_usd_ledger": usd(sum(miss), sum(c), sum(t)),
        "est_usd": usd(sum(miss), sum(c), sum(t)),
        "mech": dict(Counter(classify(r) for r in xs)),
    }


def hypothetical_da(rows, d_status: str, a_status: str) -> dict:
    flipped = []
    for row in rows:
        copied = dict(row)
        if copied.get("status") == "interrupted":
            if copied.get("arm") == "D_soft":
                copied["status"] = d_status
            elif copied.get("arm") == "A":
                copied["status"] = a_status
        flipped.append(copied)
    out = da_from_results(remap_dsoft_for_frozen_analysis(flipped))
    out["confirmatory"] = False
    out["comparison"] = "D_soft-A"
    out["label"] = "post_accident_bounds_not_preregistered"
    return out


def complete_case_da(rows) -> dict:
    mapped = remap_dsoft_for_frozen_analysis(rows)
    keep = []
    dropped = 0
    by = defaultdict(dict)
    for row in mapped:
        if row.get("arm") in {"D", "A"}:
            by[(row["task_id"], row["spec_variant"], int(row["repeat"]))][row["arm"]] = row
    for arms in by.values():
        if arms.get("D", {}).get("status") == "interrupted" or arms.get("A", {}).get("status") == "interrupted":
            dropped += 1
            continue
        keep.extend(arms.values())
    out = da_from_results(keep)
    out["confirmatory"] = False
    out["pairs_dropped"] = dropped
    out["label"] = "complete_case_biased_not_preregistered"
    return out


def assert_design(rows):
    assert len(rows) == 144, len(rows)
    by_arm = Counter(r["arm"] for r in rows)
    assert by_arm["A"] == 72 and by_arm["D_soft"] == 72, by_arm
    by_task = Counter(r["task_id"] for r in rows)
    assert all(v == 12 for v in by_task.values()), by_task
    combo = Counter((r["task_id"], r["spec_variant"], r["arm"]) for r in rows)
    assert all(v == 3 for v in combo.values()), set(combo.values())
    st = Counter(r.get("status") for r in rows)
    bad = {k: st[k] for k in st if k not in {"passed", "failed", "error", "interrupted"}}
    assert not bad, bad
    return st


def case_block(run_root: Path, alloc: str, why: str) -> str:
    dest = run_root / alloc
    result = json.loads((dest / "result.json").read_text(encoding="utf-8"))
    rel = dest.relative_to(ROOT)
    soft = result.get("soft_closes") or (result.get("recorder") or {}).get("soft_closes") or []
    return (
        f"#### `{alloc}`\n\n"
        f"{why}\n\n"
        f"- 状态 `{result.get('status')}`；error `{result.get('error')}`\n"
        f"- 记录目录 [`{rel}`]({rel}/result.json)\n"
        f"- T/I/K = {(result.get('ledger') or {}).get('used_t')}/"
        f"{(result.get('ledger') or {}).get('used_i')}/{(result.get('ledger') or {}).get('used_k')}\n"
        f"- hidden eval: {'yes' if isinstance(result.get('evaluation'), dict) else 'no'}\n"
        f"- soft_close 次数：{len(soft)}；事件：{json.dumps(soft, ensure_ascii=False)[:500]}\n"
        f"- missing_deliver：{(result.get('notes') or {}).get('missing_deliver')}\n"
    )


def pick_dsoft_traces(rows: list[dict]) -> list[str]:
    """Prefer a passed D_soft with soft_close, then any D_soft with soft_close."""
    dsoft = [r for r in rows if r.get("arm") == "D_soft"]
    passed_soft = [r for r in dsoft if r.get("status") == "passed" and (r.get("soft_closes") or (r.get("recorder") or {}).get("soft_closes"))]
    any_soft = [r for r in dsoft if r.get("soft_closes") or (r.get("recorder") or {}).get("soft_closes")]
    chosen = []
    for pool in (passed_soft, any_soft, dsoft):
        for r in pool:
            if r["allocation_id"] not in chosen:
                chosen.append(r["allocation_id"])
            if len(chosen) >= 2:
                return chosen
    return chosen


def main() -> None:
    canonical = ROOT / "REPORT.md"
    if canonical.is_file() and "136 执行完 + 8 中断" in canonical.read_text(encoding="utf-8"):
        print("canonical editorial sensitivity REPORT.md present; not overwritten")
        return
    run = latest_run()
    rows = load_rows(run)
    st = assert_design(rows)
    mapped = remap_dsoft_for_frozen_analysis(rows)
    da = da_from_results(mapped)
    da["confirmatory"] = False
    da["comparison"] = "D_soft-A"
    da["label"] = "exploratory_sensitivity_inspired_by_primary_diagnostics"
    lo, hi = da["ci95"]
    point = da["point"]
    arms = {a: summarize_arm(rows, a) for a in ("A", "D_soft")}
    usage = derive_run(run)
    write_outputs(usage)
    ledger_usd = sum(s["est_usd_ledger"] for s in arms.values())
    interrupt_usd = usage["derived_known_sum"]["est_usd"]
    known_usd = ledger_usd + interrupt_usd
    for a, s in arms.items():
        part = sum(
            r["derived_known"]["est_usd"]
            for r in usage["rows"]
            if r.get("arm") == a
        )
        s["est_usd_interrupt_lower_bound"] = part
        s["est_usd_known_lower_bound"] = s["est_usd_ledger"] + part
        s["est_usd"] = s["est_usd_known_lower_bound"]
    best = hypothetical_da(rows, "passed", "failed")
    worst = hypothetical_da(rows, "failed", "passed")
    cc = complete_case_da(rows)
    n_missing_deliver = sum(
        1
        for r in rows
        if r.get("arm") == "D_soft" and (r.get("notes") or {}).get("missing_deliver")
    )
    audit = run_audit(run)
    (ROOT / "report" / "audit144.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    pass_by_arm(rows)
    resources_by_arm(rows)
    fail_mix(rows, classify)
    task_heatmap(rows)
    da_forest(da["task_means"], point, lo, hi)

    traces = pick_dsoft_traces(rows)
    n_int = int(st.get("interrupted") or 0)

    md = []
    w = md.append
    w("# 探索性敏感性分析报告（D_soft）")
    w("")
    w("**标签：探索性敏感性分析，受主实验诊断启发。不是独立新任务确认，不与原 360 池化。**")
    w("")
    w(f"生成时间（UTC）：{datetime.now(timezone.utc).isoformat()}")
    w(f"敏感性 run：[`{run.relative_to(ROOT)}`]({run.relative_to(ROOT)})")
    w("")
    w("## 1. 要回答什么")
    w("")
    w("在**不增加额度、不改角色/提示/任务**的前提下，把 D 在 independent-*/exchange-* 上的硬阶段终止改成软结束（保留已有 history/private 产物，继续原定后续阶段），")
    w("同批新 A 对照下，D_soft 的成功率/成本与区间如何？硬阶段终止是否足以解释主实验 D 的劣势？是否达到 +10pp？")
    w("")
    w("## 2. 机制（唯一变化）")
    w("")
    w("- A：原样，无阶段 cap，无 soft_close。")
    w("- D_soft：内部调用 `stage_caps_for('D')` + `run_arm(..., arm='D')`（原 ROLE 提示）。")
    w("- 仅 `stage_budget_exhausted` 且 stage 为 independent-* / exchange-* 时记录 `soft_close` 并继续。")
    w("- 不增加预算、不追加摘要调用、不合成缺失的 deliver note。")
    w("- integrate / 全局 T/I/K / API / hang / 最终截断 / 所有权：仍硬失败，计 0。")
    w("")
    w("## 3. 样本与控制器中断")
    w("")
    w(f"- 分配 {len(rows)}；状态 {dict(st)}。分母 144。`failed`/`error`/`interrupted` 在主表均计 0。")
    w("- 12 任务 × 2 spec × A/D_soft × 3 repeat；seed 20260914；并发 8。")
    w("- 失败全部保留。不可把本 144 与原 360 混成一个分母。不得重开 cohort、不得补跑 8 个 interrupted。")
    w("")
    w("### 3.1 过程失效 vs 模型失效")
    w("")
    w(f"- **过程失效（控制器）**：{n_int} 个 `interrupted`（D_soft {usage['n_dsoft']}，A {usage['n_A']}）。")
    w("  原因：Grok headless 后台等待 600s 超时后杀仍在运行的 runner，不是 DeepSeek API 失败，也不是模型能力失败。")
    w("  **不要**把这 7 个 D_soft / 1 个 A 记成该编排自身缺陷。")
    w("- **模型/编排失效（进入终态）**：failed 6（A：2 次 `incomplete_final_response`；D_soft：3 次全局 `budget_exhausted:K`，1 次 `incomplete_final_response`）。")
    w("- 已完成 123 个终态在 resume 前完整保留；resume 只跑 13 个从未开始的分配，8 个孤立 running 标 `interrupted` 且 `rerun=false`。")
    w("")
    w("## 4. 探索性比较 D_soft−A（冻结 analysis.py；映射 D_soft→D）")
    w("")
    w("预固定统计：interrupted 计 0，分母 144，12 任务等权配对 bootstrap 20k seed 20260913。")
    w("")
    w(f"- 点估计：**{100*point:.2f} 个百分点**")
    w(f"- 95% 区间：**[{100*lo:.2f}, {100*hi:.2f}]** 个百分点")
    w(f"- 判定口径（描述，非确认性）：`{da['interpretation']}`")
    w(f"- 是否达到 +10pp：{'是' if da['interpretation']=='support_adoption_threshold' else '否（按预注册解释函数）'}")
    w("")
    w("主实验 D−A 为 −93.06pp（CI 全负，D=0/72）。本 144 在同一包络下把内部独立/交流阶段改为软结束：")
    w(f"D_soft ITT 通过 {arms['D_soft']['pass']}/72，同批 A {arms['A']['pass']}/72。硬阶段终止**足以解释主实验 D 几乎全部失败**；")
    w("软结束后差值收窄到约 −11pp，但**仍未达到 +10pp**，点估计仍为负，CI 上界触 0。")
    w("这只隔离一条终止规则，不是优化过的专家团队。")
    w("")
    w("| 任务 | D_soft−A（ITT，中断=0） |")
    w("|---|---:|")
    for t, v in sorted(da["task_means"].items()):
        w(f"| {t} | {100*v:.1f}pp |")
    w("")
    w("### 4.1 中断结果未知时的点估计界限（事故后不确定性，不能替代预固定统计）")
    w("")
    w("中断不是随机缺失：D_soft 调用更长，被 600s 清理击中的概率更高。**不得**把 complete-case 率声称无偏。")
    w("下列只翻转 8 个 interrupted 的成败，已终态行不变。有利极端=中断 D 成功且中断 A 失败；反向为不利极端。")
    w("")
    w("| 口径 | 点估计 | 95% CI | 解释函数 | 性质 |")
    w("|---|---:|---|---|---|")
    w(f"| 预固定 ITT（interrupted=0，分母144） | {100*point:.2f}pp | [{100*lo:.2f}, {100*hi:.2f}] | `{da['interpretation']}` | 主表 |")
    w(f"| 有利极端（中断D成功 / 中断A失败） | {100*best['point']:.2f}pp | [{100*best['ci95'][0]:.2f}, {100*best['ci95'][1]:.2f}] | `{best['interpretation']}` | 事故后界限 |")
    w(f"| 不利极端（中断D失败 / 中断A成功） | {100*worst['point']:.2f}pp | [{100*worst['ci95'][0]:.2f}, {100*worst['ci95'][1]:.2f}] | `{worst['interpretation']}` | 事故后界限 |")
    w(f"| complete-case（丢掉 {cc['pairs_dropped']} 对含中断的配对） | {100*cc['point']:.2f}pp | [{100*cc['ci95'][0]:.2f}, {100*cc['ci95'][1]:.2f}] | `{cc['interpretation']}` | **有偏，不采用** |")
    w("")
    w("即使有利极端，解释函数仍不是 `support_adoption_threshold`。不利极端变为 `support_worse`。主结论边界以 ITT 为准。")
    w("")
    w("## 5. 各组")
    w("")
    w("| 组 | n | 通过 | 通过率(ITT) | hidden eval | 进入整合 | 含 soft_close | 中断 |")
    w("|---|---:|---:|---:|---:|---:|---:|---:|")
    for a, s in arms.items():
        w(f"| {a} | {s['n']} | {s['pass']} | {pct(s['rate'])} | {pct(s['hidden'])} | {pct(s['integrate'])} | {s['soft_close']} | {s['n_interrupted']} |")
    w("")
    w(f"非中断 D_soft 共 65 条，**全部**记录了 `soft_close`（机制确实触发）。{n_missing_deliver} 条仍有 `missing_deliver` 阶段名单：")
    w("软结束保留已有产物并继续，但**不合成**缺失的独立/交流 deliver note，不能把每条 D_soft 说成完整合议。")
    w("")
    w("### 资源与费用（仅参与模型推理估算）")
    w("")
    w("单价（非高峰 Flash，美元/百万 token）：未命中输入 0.15，缓存命中 0.003，输出 0.6。")
    w(f"来源：{PRICE['source']}。**不是账户账单。不含 Grok 实施、Codex 监督、Docker、人力。**")
    w("")
    w("均/中位只统计**有最终 ledger 的行**（A 71，D_soft 65）。8 个 interrupted 的 result.json 无 ledger，**不当成用量 0**。")
    w(f"中断行从已落盘 response.usage / tools.jsonl 派生已知下界，见 [`report/interruption-audit/derived-usage.md`](report/interruption-audit/derived-usage.md)。")
    w(f"{usage['n_open_http_requests']} 次已写 request、无 response 的 HTTP **可能已计费，token 未知，未记为 0**。")
    w("")
    w("| 组 | n_ledger | 输出T均/中位 | 输入I均/中位 | cache均 | 工具K均/中位 | ledger USD | 中断已知下界 USD | 已知合计 USD |")
    w("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for a, s in arms.items():
        w(
            f"| {a} | {s['n_ledger']} | {s['T_mean']:.0f}/{s['T_median']:.0f} | "
            f"{s['I_mean']:.0f}/{s['I_median']:.0f} | {s['cache_mean']:.0f} | "
            f"{s['K_mean']:.1f}/{s['K_median']:.0f} | {s['est_usd_ledger']:.4f} | "
            f"{s['est_usd_interrupt_lower_bound']:.4f} | {s['est_usd_known_lower_bound']:.4f} |"
        )
    w(f"| 本 144 已知下界 |  |  |  |  |  | {ledger_usd:.4f} | {interrupt_usd:.4f} | **{known_usd:.4f}** |")
    w("")
    w("### 失败机制")
    w("")
    w("| 组 | 构成 |")
    w("|---|---|")
    for a, s in arms.items():
        w(f"| {a} | {s['mech']} |")
    w("")
    w("`interrupted`：控制器杀进程。`global_budget`：全局 T/I/K 硬失败（本批为 K）。`failed_without_hidden_eval`：终裁前截断，不是隐藏验收反例。")
    w("")
    w("## 6. D_soft 轨迹（至少两例）")
    w("")
    if len(traces) < 2:
        w("可用轨迹不足两例；下列为已有样本。")
    for alloc in traces[:2]:
        w(case_block(run, alloc, "D_soft 具体轨迹：展示 soft_close、最终产物与验收（若进入）。不能由本条推广到未展示的任务。"))
    w("")
    w("## 7. 审计（不能声称 144/144 日志完美）")
    w("")
    w(f"- 144 唯一分配：{audit['unique']==144}；terminal 144（passed {st.get('passed')}，failed {st.get('failed')}，interrupted {n_int}）")
    w(f"- freeze 校验：{audit['freeze_verified']}；live 漂移：{audit['live_source_drift']}")
    w(f"- task_hash_drift：{audit['task_hash_drift']}")
    w(f"- 意外 usage 不匹配（非中断）：{audit['usage_mismatches'] or '无'}")
    w(f"- 含 soft_close 的分配数：{audit.get('n_soft_close_rows')}")
    w(f"- 预期中断缺口行：{audit.get('n_expected_interrupt_issue_rows')}；开放 HTTP：{audit.get('n_open_http_requests')}；意外问题行：{audit.get('n_unexpected_issue_rows')}")
    w(f"- 无意外问题：{audit['n_ok']} 行（136 终态日志完整 + 8 行仅预期中断缺口）。**不是** 144/144 请求-响应完美配对。")
    w(f"- Docker digest 现在：`{audit['docker_image_id_now']}`；与 manifest 一致：{audit['docker_image_id_matches']}")
    w("- 原始 running 快照：[`report/interruption-audit/running-snapshots-before-resume/`](report/interruption-audit/running-snapshots-before-resume/)")
    w("")
    w("## 8. 仍不能做的判断")
    w("")
    w("- 纯角色效应：D 与 C 同时改变角色标题与焦点指令，且主实验两者都卡在独立分析额度；本敏感性没有无角色的 C_soft 对照。")
    w("- 异质专家、整库任务、强弱模型、skills：均未做。")
    w("- 独立维护者/盲评维护性：原协议未实施，不能伪称完成。")
    w("- 不得把后续改变叫原 360 方案结果。")
    w("- 不得把控制器中断当成 D_soft 编排失败，也不得用 complete-case 宣称无偏。")
    w("")
    w("图：[`report/figures/`](report/figures/)。")

    text = "\n".join(md) + "\n"
    (ROOT / "REPORT.md").write_text(text, encoding="utf-8")
    (run / "REPORT.md").write_text(text, encoding="utf-8")
    tables = {
        "da": da,
        "da_best_interrupt": best,
        "da_worst_interrupt": worst,
        "da_complete_case_biased": cc,
        "arms": arms,
        "status": dict(st),
        "audit_ok": audit["n_ok"],
        "est_usd": known_usd,
        "est_usd_ledger": ledger_usd,
        "est_usd_interrupt_lower_bound": interrupt_usd,
        "est_usd_is_lower_bound": True,
        "n_open_http_unknown_usage": usage["n_open_http_requests"],
        "run": str(run),
    }
    (ROOT / "report" / "tables.json").write_text(json.dumps(tables, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({
        "point": point, "ci": da["ci95"], "interp": da["interpretation"],
        "n": len(rows), "status": dict(st), "known_usd": known_usd,
        "open_http": usage["n_open_http_requests"],
    }, indent=2))


if __name__ == "__main__":
    main()
