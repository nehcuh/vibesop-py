"""Rewrite primary REPORT.md with 360 + exploratory 144 side by side.

Does not modify frozen analysis or primary 360 results. Snapshot remains REPORT.primary360.md.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SENS = ROOT.parent / "multi-expert-sensitivity"
PRICE_SRC = "https://api-docs.deepseek.com/quick_start/pricing/"
from report.usage_cost import cohort_costs  # noqa: E402


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _usd_block(name, usd, extra=""):
    return f"| {name} | {usd:.4f} | {extra} |"


def main() -> None:
    # Canonical REPORT.md is the editorial article. Regenerating the old
    # concatenation would destroy the coherent structure.
    canonical = ROOT / "REPORT.md"
    if canonical.is_file() and "发现（先看数字）" in canonical.read_text(encoding="utf-8")[:4000]:
        print("canonical editorial REPORT.md present; not overwritten")
        return
    snapshot = (ROOT / "REPORT.primary360.md").read_text(encoding="utf-8")
    tables360 = _load(ROOT / "report" / "tables.json")
    audit360 = _load(ROOT / "report" / "audit360.json")
    sens_tables = SENS / "report" / "tables.json"
    sens_report = SENS / "REPORT.md"
    if not sens_tables.is_file() or not sens_report.is_file():
        raise RuntimeError("sensitivity_report_missing")
    t144 = _load(sens_tables)
    da = t144["da"]
    arms = t144["arms"]
    lo, hi = da["ci95"]
    point = da["point"]
    a = arms["A"]
    d = arms["D_soft"]
    now = datetime.now(timezone.utc).isoformat()

    md = []
    w = md.append
    w("# 多专家组织对照：正式报告（主 360 + 探索性敏感性 144）")
    w("")
    w("面向实际做 AI 开发方法选择的读者。这是一份**受控小型 CLI 基准**的结果，不是异质专家团队、也不是整库工程的结论。")
    w("")
    w("本文并列两份**彼此独立**的研究：")
    w("1. **主实验 360**（确认性）：冻结流程与资源包络下的 A/B/C/D/E。失败全部保留。不得用后续改变改写该结果。")
    w("2. **探索性敏感性 144**：受主实验诊断启发，隔离硬阶段终止机制。标签明确为探索性，**不是独立新任务确认**，**不与 360 池化**。")
    w("")
    w(f"合并生成时间（UTC）：{now}")
    w("主 360 快照：[`REPORT.primary360.md`](REPORT.primary360.md)（保留 Git 历史）。")
    w("敏感性独立报告：[`../multi-expert-sensitivity/REPORT.md`](../multi-expert-sensitivity/REPORT.md)。")
    w("")
    w("---")
    w("")
    w("## A. 主实验 360（确认性，冻结）")
    w("")
    w("以下为原完整中文主报告正文，未改冻结统计。")
    w("")
    w(snapshot)
    w("")
    w("---")
    w("")
    w("## B. 探索性敏感性 144（D_soft）")
    w("")
    w("**标签：探索性敏感性分析，受主实验诊断启发。不是独立新任务确认，不与原 360 池化。**")
    w("")
    w("### B.1 触发")
    w("")
    w("主实验 D 失败 72/72 均为内部 `stage_budget_exhausted`（independent-0: 68，independent-1: 4）。")
    w("满足「至少一半为内部 stage_cap 终止」的预先记录触发条件，因此执行本 144，不等待额外授权。")
    w("")
    w("### B.2 机制")
    w("")
    w("仅 D_soft 在 independent-* / exchange-* 的 `stage_budget_exhausted` 时保留 history/private/partial，记录 `soft_close`，继续原定后续阶段。")
    w("不加预算、不改角色/提示/任务/输入字节预检、不追加摘要调用、不合成缺失的 deliver note。")
    w("A 原样。同批随机交错。D_soft 使用 `stage_caps_for('D')` 与 `run_arm(..., arm='D')`。")
    w("全局 T/I/K、API、hang、最终 integrate 失败仍计 0。")
    w("")
    w("### B.3 结果（冻结 analysis.py：12 任务配对 bootstrap 20k seed 20260913，+10pp）")
    w("")
    w("预固定统计：`interrupted` 计 0，分母 144。")
    w("")
    w(f"- D_soft−A 点估计：**{100*point:.2f} 个百分点**")
    w(f"- 95% 区间：**[{100*lo:.2f}, {100*hi:.2f}]**")
    w(f"- 解释函数：`{da['interpretation']}`")
    w(f"- 是否达到 +10pp：**{'是' if da['interpretation']=='support_adoption_threshold' else '否'}**")
    w("")
    w(f"| 组 | n | 通过 | 通过率(ITT) | 进入 hidden | 进入整合 | 中断 |")
    w("|---|---:|---:|---:|---:|---:|---:|")
    w(f"| A（同批） | {a['n']} | {a['pass']} | {100*a['rate']:.1f}% | {100*a['hidden']:.1f}% | {100*a['integrate']:.1f}% | {a.get('n_interrupted', 0)} |")
    w(f"| D_soft | {d['n']} | {d['pass']} | {100*d['rate']:.1f}% | {100*d['hidden']:.1f}% | {100*d['integrate']:.1f}% | {d.get('n_interrupted', 0)} |")
    w("")
    w("硬阶段终止是否解释主实验劣势：主实验 D=0/72、D−A=−93.1pp（CI 全负）。本 144 仅改独立/交流阶段的硬终止为软结束，")
    w(f"D_soft ITT {d['pass']}/72 vs 同批 A {a['pass']}/72，差值收窄到 {100*point:.1f}pp。硬终止是该包络下主导机制；")
    w("软结束后仍未达到 +10pp，点估计为负。这不是优化专家团队，也不能推广到其他任务。")
    w("")
    w("### B.3.1 控制器中断（过程失效，不是模型失败）")
    w("")
    st144 = t144.get("status") or {}
    w(f"状态：passed {st144.get('passed')}，failed {st144.get('failed')}，interrupted {st144.get('interrupted')}，error {st144.get('error', 0)}。")
    w("8 个 interrupted 来自 Grok headless 600s 后台超时杀进程，不是 DeepSeek API、也不是编排能力。7 个 D_soft + 1 个 A。")
    w("不得补跑这 8 个以变好分数。主表仍计 0。")
    w("")
    best = t144.get("da_best_interrupt") or {}
    worst = t144.get("da_worst_interrupt") or {}
    cc = t144.get("da_complete_case_biased") or {}
    if best and worst:
        w("事故后点估计界限（只翻转 interrupted；**不能替代**预固定 ITT）：")
        w("")
        w("| 口径 | 点估计 | 解释函数 |")
        w("|---|---:|---|")
        w(f"| ITT（主表） | {100*point:.2f}pp | `{da['interpretation']}` |")
        w(f"| 有利（中断D成功/A失败） | {100*best['point']:.2f}pp | `{best.get('interpretation')}` |")
        w(f"| 不利（中断D失败/A成功） | {100*worst['point']:.2f}pp | `{worst.get('interpretation')}` |")
        if cc:
            w(f"| complete-case（有偏，丢掉 {cc.get('pairs_dropped')} 对） | {100*cc['point']:.2f}pp | 不采用 |")
        w("")
        w("中断不随机，complete-case 不能声称无偏。")
        w("")
    w("### B.4 费用（仅参与模型推理估算）")
    w("")
    w("单价来源：" + PRICE_SRC + "。排除 Grok 研究实施、Codex 监督、Docker 与人力开销。不是发票。")
    w("")
    costs = cohort_costs()
    usd144 = t144.get("est_usd", 0)
    note144 = "已知下界：ledger + 中断行已落盘 usage；7 次无 response 的 HTTP 可能已计费、用量未知，未记 0"
    w("| 队列 | n | 估算 USD | 说明 |")
    w("|---|---:|---:|---|")
    w(f"| 校准 75（45 旧执行器 + 30 新执行器非正式） | {costs['calibration_75']['n']} | {costs['calibration_75']['usd']:.4f} | 非 360 样本；仅参与模型推理 |")
    w(f"| 主 360 | {costs['primary_360']['n']} | {costs['primary_360']['usd']:.4f} | 仅 360 次参与模型调用 |")
    w(f"| 补充 144 | 144 | {usd144:.4f} | {note144} |")
    w("")
    w("费用范围：仅参与模型推理估算（公开非高峰单价）。**排除** Grok 研究实施、Codex 监督、Docker 与人力开销。不是发票。")
    w("144 不得把 interrupted 的缺失 ledger 当成 0 用量，也不得宣称 144/144 调用都有 response。")
    w("")
    w("### B.5 仍不能做的判断")
    w("")
    w("- 纯角色效应未获可用对照（D vs C 同时改标题与焦点，且主实验两者均卡在独立分析额度；本 144 无 C_soft）。")
    w("- 异质专家、整库任务、强弱模型、skills：未做。")
    w("- 独立维护者/盲评维护性：原协议未实施，不能伪称完成。")
    w("- 任务根来自项目机制的**构造**小型 CLI，不是生产回放。")
    w("- 不得把 Grok 控制器终止的 7 个 D_soft / 1 个 A 当成编排缺陷，也不得用 complete-case 宣称无偏。")
    w("")
    w("敏感性独立全文与图见 `docs/experiments/multi-expert-sensitivity/`。")
    w("")

    text = "\n".join(md) + "\n"
    (ROOT / "REPORT.md").write_text(text, encoding="utf-8")
    print(json.dumps({"wrote": str(ROOT / "REPORT.md"), "dsoft_point": point, "interp": da["interpretation"]}, indent=2))


if __name__ == "__main__":
    main()
