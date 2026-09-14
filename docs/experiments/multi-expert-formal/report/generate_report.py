"""Build the full Chinese REPORT.md. Presentation layer only."""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness.analysis import cluster_bootstrap, da_from_results, task_mean_diffs  # frozen
from report.audit360 import classify_mech, run_audit
from report.collect import classify, load_rows, reached_hidden, reached_integrate
from report.plot import da_forest, fail_mix, pass_by_arm, resources_by_arm, task_heatmap

RUN = ROOT / "runs" / "20260913T023645Z"
PRICE = {"miss": 0.15, "hit": 0.003, "out": 0.6, "source": "https://api-docs.deepseek.com/quick_start/pricing/"}


def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def pct(x):
    return f"{100 * x:.1f}%"


def usd(miss, hit, out):
    return (miss * PRICE["miss"] + hit * PRICE["hit"] + out * PRICE["out"]) / 1e6


def ledger_cache(row):
    return (row.get("ledger") or {}).get("cache_hit") or 0


def summarize_arm(rows, arm):
    xs = [r for r in rows if r.get("arm") == arm]
    t = [((r.get("ledger") or {}).get("used_t") or 0) for r in xs]
    i = [((r.get("ledger") or {}).get("used_i") or 0) for r in xs]
    k = [((r.get("ledger") or {}).get("used_k") or 0) for r in xs]
    c = [ledger_cache(r) for r in xs]
    miss = [ii - cc for ii, cc in zip(i, c)]
    return {
        "n": len(xs),
        "pass": sum(1 for r in xs if r.get("status") == "passed"),
        "rate": mean([1.0 if r.get("status") == "passed" else 0.0 for r in xs]),
        "hidden": mean([1.0 if reached_hidden(r) else 0.0 for r in xs]),
        "integrate": mean([1.0 if reached_integrate(r) else 0.0 for r in xs]),
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
        "est_usd": usd(sum(miss), sum(c), sum(t)),
        "mech": dict(Counter(classify(r) for r in xs)),
    }


def assert_design(rows):
    assert len(rows) == 360, len(rows)
    by_arm = Counter(r["arm"] for r in rows)
    assert all(by_arm[a] == 72 for a in "ABCDE"), by_arm
    by_task = Counter(r["task_id"] for r in rows)
    assert all(v == 30 for v in by_task.values()), by_task
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
    return (
        f"#### `{alloc}`\n\n"
        f"{why}\n\n"
        f"- 状态 `{result.get('status')}`；error `{result.get('error')}`\n"
        f"- 记录目录 [`{rel}`]({rel}/result.json)\n"
        f"- T/I/K = {(result.get('ledger') or {}).get('used_t')}/"
        f"{(result.get('ledger') or {}).get('used_i')}/{(result.get('ledger') or {}).get('used_k')}\n"
        f"- hidden eval: {'yes' if isinstance(result.get('evaluation'), dict) else 'no'}\n"
    )


def main() -> None:
    rows = load_rows(RUN)
    st = assert_design(rows)
    da = da_from_results(rows)
    lo, hi = da["ci95"]
    point = da["point"]
    explor = {
        "B-A": cluster_bootstrap(task_mean_diffs(rows, "B", "A")),
        "E-A": cluster_bootstrap(task_mean_diffs(rows, "E", "A")),
        "D-C": cluster_bootstrap(task_mean_diffs(rows, "D", "C")),
        "C-A": cluster_bootstrap(task_mean_diffs(rows, "C", "A")),
    }
    for k, v in explor.items():
        v["confirmatory"] = False
        v["comparison"] = k
    arms = {a: summarize_arm(rows, a) for a in "ABCDE"}
    by_spec = {}
    for spec in ("full", "brief"):
        xs = [r for r in rows if r.get("spec_variant") == spec]
        by_spec[spec] = mean([1.0 if r.get("status") == "passed" else 0.0 for r in xs])
    by_task_arm = defaultdict(dict)
    for t in sorted({r["task_id"] for r in rows}):
        for a in "ABCDE":
            xs = [r for r in rows if r["task_id"] == t and r["arm"] == a]
            by_task_arm[t][a] = mean([1.0 if r.get("status") == "passed" else 0.0 for r in xs])
    audit = run_audit(RUN)
    (ROOT / "report" / "audit360.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    pass_by_arm(rows)
    resources_by_arm(rows)
    fail_mix(rows, classify)
    task_heatmap(rows)
    da_forest(da["task_means"], point, lo, hi)

    total_usd = sum(s["est_usd"] for s in arms.values())
    image_end = audit["docker_image_id_now"]

    md = []
    w = md.append
    w("# 多专家组织对照：正式报告")
    w("")
    w("面向实际做 AI 开发方法选择的读者。这是一份**受控小型 CLI 基准**的结果，不是异质专家团队、也不是整库工程的结论。")
    w("主比较在冻结的流程与资源包络下进行。失败样本全部保留。")
    w("")
    w(f"生成时间（UTC）：{datetime.now(timezone.utc).isoformat()}")
    w(f"正式 run：[`runs/20260913T023645Z`](runs/20260913T023645Z)")
    w("")
    w("## 1. 要回答什么")
    w("")
    w("在**同一模型**（请求 `deepseek-v4-flash`，服务 DeepSeek-V4.1-Flash，响应 `deepseek-flash`）、")
    w("同一工具、同一总资源上限 T=24000 / I=400000 / K=120 下，带专家角色的委员会（D）是否比单体（A）")
    w("在隐藏 CLI 验收上交付更多成功产物？")
    w("")
    w("次要（探索）：B−A 分阶段流程；C−B 多上下文；D−C 角色标签；E 明确分工。")
    w("")
    w("## 2. 五组（固定流程）")
    w("")
    w("| 组 | 流程 |")
    w("|---|---|")
    w("| A 单体 | 一个上下文完成实现与交付，可用满 T/I/K |")
    w("| B 单体分阶段 | 同一上下文：规划 → 实现 → 检查 |")
    w("| C 无角色委员会 | 三独立分析 + 一轮同步交流 + 成员0整合 |")
    w("| D 专家委员会 | 与 C 相同，唯一差别是架构/实现/质量角色 |")
    w("| E 明确分工 | 模型拆成两名工人（文件不重叠）+ 整合；拆解计入成本 |")
    w("")
    w("C/D 独立分析每人最多 10% T（2400）。该硬阶段上限是本包络的一部分，不是事后补丁。")
    w("")
    w("## 3. 任务与范围")
    w("")
    w("12 个合成 CLI 任务：路由 4、跨层配置入口 4、可拆分数据/量化 4。完整/简略 spec 共享可查询合同（`contract` 问答）。")
    w("**不是**整库工程；不能推广为真实多专家团队。历史校准 45（旧执行器）+ 30（新执行器非正式）**不是**本 360 的样本。")
    w("")
    w("## 4. 方法")
    w("")
    w("- 成功：总预算内交付 + 全部隐藏验收通过 + 无所有权/路径违规。`failed`/`error`/`interrupted` 记 0。")
    w("- 无隐藏验收的失败**不**称为实现 bug。")
    w("- 主估计：每任务 6 个配对（2 spec × 3 repeat）的 D−A 差的均值，再对 12 任务等权平均。")
    w("- 95% cluster bootstrap，20000 次，seed=20260913，有放回抽任务；被抽中任务保留全部 spec/repeat。实现：冻结的 `harness/analysis.py`。")
    w("- +10pp 工程阈值解释见 `preregistration.md`。")
    w("- 并发 8；分配 seed 20260913；360 行一次性写入同一 manifest。")
    w("- Docker：批次边界核对 image **digest** 与 manifest 一致；**启动 argv 仍是 tag** `python:3.12-slim`（`tasks/common.py`）。运行期间未 pull。")
    w("- 输入预检用 UTF-8 字节作保守上限，不是 tokenizer；`I_precheck` 与真实 input 耗尽分开记账。")
    w("")
    w("## 5. 样本完整性")
    w("")
    w(f"- 分配 {len(rows)}；状态 {dict(st)}")
    w("- 每组 72，每任务 30，每任务×规格×组 重复 3：已核对。")
    w("- 无 pending/running/missing 后才计算下列推断。")
    w("")
    w("## 6. 主比较 D−A（确认性）")
    w("")
    w(f"- 点估计：**{100*point:.2f} 个百分点**")
    w(f"- 95% 区间：**[{100*lo:.2f}, {100*hi:.2f}]** 个百分点")
    w(f"- 判定（预注册）：`{da['interpretation']}`")
    w("")
    interp = da["interpretation"]
    if interp == "support_adoption_threshold":
        w("区间下界超过 +10pp，支持在本电池、本流程+预算包络上达到预定采用阈值。")
    elif interp == "support_worse":
        w("区间上界小于 0，支持 D 整体更差（仍只覆盖本包络）。")
    elif interp == "small_positive_below_threshold":
        w("整段落在 (0, +10)pp：有小的正向差，但达不到预定采用阈值。")
    elif interp == "rules_out_minimum_gain":
        w("区间上界小于 +10pp：排除本电池上达到 +10pp 最低工程收益；**不**证明等价。")
    else:
        w("区间跨越决策阈值，结论**未定**。不得宣称多专家有效或无效。")
    w("")
    w("**不能**把本结果说成「专家更笨」「多智能体普遍无效」或「委员会代码更差」。")
    w("硬阶段终止（尤其 C/D 的 independent-0 = 2400 输出 token）可能主导差值。这是该特定流程+预算的端到端效果。")
    w("")
    w("任务均值（D−A）：")
    w("")
    w("| 任务 | D−A |")
    w("|---|---:|")
    for t, v in sorted(da["task_means"].items()):
        w(f"| {t} | {100*v:.1f}pp |")
    w("")
    w("### 探索比较（同一方法，不作确认性宣称）")
    w("")
    w("| 对比 | 点估计 | 95% CI | 预注册口径（仅作描述） |")
    w("|---|---:|---|---|")
    for name, ev in explor.items():
        w(f"| {name} | {100*ev['point']:.1f}pp | [{100*ev['ci95'][0]:.1f}, {100*ev['ci95'][1]:.1f}] | `{ev['interpretation']}` |")
    w("")
    w("D−C 接近 0 且都极低：角色标签几乎没有机会表现，因为两边都卡在独立分析额度。")
    w("")
    w("## 7. 各组与规格")
    w("")
    w("| 组 | n | 通过 | 通过率 | 进入 hidden eval | 进入整合阶段 |")
    w("|---|---:|---:|---:|---:|---:|")
    for a, s in arms.items():
        w(f"| {a} | {s['n']} | {s['pass']} | {pct(s['rate'])} | {pct(s['hidden'])} | {pct(s['integrate'])} |")
    w("")
    w(f"完整 spec 通过率 {pct(by_spec['full'])}；简略 spec {pct(by_spec['brief'])}（探索）。")
    w("")
    w("### 资源与费用（非发票）")
    w("")
    w("单价（非高峰 Flash，美元/百万 token）：未命中输入 0.15，缓存命中 0.003，输出 0.6。")
    w(f"来源：{PRICE['source']}。周日实验窗口按非高峰估算。**不是账户账单。**")
    w("")
    w("| 组 | 输出T均/中位 | 输入I均/中位 | cache均 | 工具K均/中位 | 估算USD |")
    w("|---|---:|---:|---:|---:|---:|")
    for a, s in arms.items():
        w(f"| {a} | {s['T_mean']:.0f}/{s['T_median']:.0f} | {s['I_mean']:.0f}/{s['I_median']:.0f} | {s['cache_mean']:.0f} | {s['K_mean']:.1f}/{s['K_median']:.0f} | {s['est_usd']:.4f} |")
    w(f"| 合计 |  |  |  |  | **{total_usd:.4f}** |")
    w("")
    w("### 失败机制")
    w("")
    w("| 组 | 构成 |")
    w("|---|---|")
    for a, s in arms.items():
        w(f"| {a} | {s['mech']} |")
    w("")
    w("stage_cap：C/D 独立分析 10%T 硬终止。i_precheck：UTF-8 字节预检。hidden_implementation_failure：进入隐藏验收且未通过。")
    w("failed_without_hidden_eval：流程在验收前结束，**不是**代码契约反例。")
    w("")
    w("任务×组通过率热力图与 D−A 任务图见 [`report/figures/`](report/figures/)。")
    w("")
    w("## 8. 可回查案例")
    w("")
    w(case_block(RUN, "route-priority-table-v1-full-A-r0",
                 "单体在完整 spec 上通过隐藏验收。能证明：A 在该任务上可以走完工具回路并满足 CLI 契约。不能证明：委员会做不到（本条没有配对的 D）。"))
    w(case_block(RUN, "route-plan-dag-v1-full-C-r0",
                 "无角色委员会在 independent-0 用尽 2400 输出 token，未进入 hidden eval。能证明：硬阶段上限可以在整合之前结束一次运行。不能证明：分析质量差或任务不可做。"))
    w(case_block(RUN, "match-lot-calendar-v1-full-E-r1",
                 "明确分工组通过隐藏验收。能证明：E 协议在本任务上可以完成拆解、落盘与验收。不能证明：分工普遍优于单体。"))
    w(case_block(RUN, "config-home-isolation-v1-full-E-r1",
                 "E 在输入预检处失败（I_precheck），无 hidden eval。能证明：整合上下文变长时，字节预检会先于 tokenizer 耗尽触发。不能证明：HOME 隔离实现写错。"))
    w(case_block(RUN, "route-lifecycle-v1-full-E-r2",
                 "E 在完整 spec 上通过 17 项隐藏检查。与上一条对照：同组不同任务，结果由任务与包络共同决定。"))
    w(case_block(RUN, "window-dedup-late-v1-brief-E-r2",
                 "E 因工人写了所有权之外的 `_check.py`，runner 记 `ownership_or_conflict` 失败。能证明：成功定义包含路径/所有权，不只看隐藏测试。不能证明：隐藏测试本身会失败（本条未进入或未作为放行依据）。"))
    w(case_block(RUN, "route-nomatch-contract-v1-full-A-r0",
                 "单体最终阶段截断（`incomplete_final_response`），无 hidden eval。能证明：A 也会在包络内失败。不能证明：该任务的隐藏契约被实现写错。"))
    w("")
    w("## 9. 审计")
    w("")
    w(f"- 360 唯一分配：{audit['unique']==360}")
    w(f"- freeze 校验：{audit['freeze_verified']}；live 漂移：{audit['live_source_drift']}")
    w(f"- usage 不匹配：{audit['usage_mismatches'] or '无'}")
    w(f"- cache 不匹配：{audit['cache_mismatches'] or '无'}")
    w(f"- 请求中隐藏泄漏：{audit['leaks'] or '无'}")
    w(f"- Docker digest 现在：`{image_end}`；与 manifest 一致：{audit['docker_image_id_matches']}")
    w(f"- 启动 argv 仍为 tag `python:3.12-slim`（文档/实现偏差，未在本 cohort 修改冻结源）")
    w(f"- 审计 JSON：[`report/audit360.json`](report/audit360.json)")
    w("")
    w("若 runner 的 `passed` 与预注册（含所有权违规）不一致，原始 status 保留，列为协议偏差交监督仲裁。本报告不静默改结果。")
    w("")
    w("## 10. 校准与轨迹（与 360 分开）")
    w("")
    w("- 旧校准 45 次：`docs/experiments/multi-expert-calibration/runs/`（只读）")
    w("- 新执行器非正式 30 次：`runs/20260913T015759Z`（K=40）与 `runs/20260913T020657Z`（K=80）")
    w("- 正式 360：`runs/20260913T023645Z`")
    w("- 复现剩余（已全部完成则不必）：见 STATUS.md")
    w("")
    w("## 11. 局限")
    w("")
    w("- 小型 CLI，不是仓库级协作。")
    w("- 同一模型的角色提示 ≠ 真实多专家。")
    w("- 硬阶段 cap 可能主导 C/D。后续若做软结束敏感性实验，必须预先声明，不能改本 cohort。")
    w("- 模型别名不固定权重。temperature=0 仍有重复。")
    w("- 费用是公开非高峰单价估算，不是发票。")
    w("- I_precheck 用字节不是 tokenizer。")
    w("- Docker 启动未把 digest 写入 argv。")
    w("")
    w("## 12. 实践建议")
    w("")
    w("- 若要在产品里采用委员会，先看本电池区间是否越过 +10pp；本报告按预注册规则解释，不预设委员会必输。")
    w("- 设计多上下文流程时，阶段额度与「能否走到验收」是同一实验条件，不要事后把阶段耗尽解释成智力差异。")
    w("- 明确分工（E）的文件边界与拆解成本必须入账。")
    w("- 监督者可决定是否需要预先声明的软阶段敏感性实验。")
    w("")
    w("图：[`report/figures/pass_by_arm.svg`](report/figures/pass_by_arm.svg) 等（SVG+PNG）。绘图脚本在 `report/`，**不**在冻结统计实现中。")

    text = "\n".join(md) + "\n"
    (ROOT / "REPORT.md").write_text(text, encoding="utf-8")
    (RUN / "REPORT.md").write_text(text, encoding="utf-8")
    tables = {"da": da, "exploratory": explor, "arms": arms, "status": dict(st), "audit_ok": audit["n_ok"], "est_usd": total_usd}
    (ROOT / "report" / "tables.json").write_text(json.dumps(tables, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"point": point, "ci": da["ci95"], "interp": da["interpretation"], "n": len(rows), "status": dict(st)}, indent=2))


if __name__ == "__main__":
    main()
