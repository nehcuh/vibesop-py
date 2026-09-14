"""Sensitivity figures. Presentation-only; frozen analysis is untouched."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "report" / "figures"


def _cjk() -> None:
    from pathlib import Path as _P
    files = [
        "/System/Library/Fonts/Supplemental/Songti.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    ]
    for path in files:
        p = _P(path)
        if p.exists():
            try:
                font_manager.fontManager.addfont(str(p))
            except Exception:
                pass
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = [
        "Songti SC", "Heiti SC", "Hiragino Sans GB", "Arial Unicode MS", "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False


_cjk()


def _save(fig, name: str) -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(FIG / f"{name}.svg", bbox_inches="tight")
    fig.savefig(FIG / f"{name}.png", dpi=140, bbox_inches="tight")
    plt.close(fig)


ARMS = ["A", "D_soft"]


def pass_by_arm(rows: list[dict]) -> None:
    rates = []
    for a in ARMS:
        xs = [r for r in rows if r.get("arm") == a]
        rates.append(sum(1 for r in xs if r.get("status") == "passed") / len(xs) if xs else 0)
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(ARMS, [100 * x for x in rates], color="#4c78a8")
    ax.set_ylabel("通过率 (%)")
    ax.set_xlabel("实验组")
    ax.set_title("敏感性：同批 A 与 D_soft 通过率（n=72/组；interrupted 计 0）")
    ax.set_ylim(0, 100)
    for i, v in enumerate(rates):
        ax.text(i, 100 * v + 1.5, f"{100*v:.1f}%", ha="center", fontsize=9)
    _save(fig, "pass_by_arm")


def resources_by_arm(rows: list[dict]) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.8))
    keys = [("used_t", "输出 T"), ("used_i", "输入 I"), ("used_k", "工具 K")]
    for ax, (key, title) in zip(axes, keys):
        data = []
        for a in ARMS:
            vals = [
                ((r.get("ledger") or {}).get(key) or 0)
                for r in rows
                if r.get("arm") == a and r.get("status") != "interrupted" and (r.get("ledger") or {}).get(key) is not None
            ]
            data.append(vals)
        try:
            ax.boxplot(data, tick_labels=ARMS, showfliers=True)
        except TypeError:
            ax.boxplot(data, labels=ARMS, showfliers=True)
        ymax = max((max(v) if v else 0) for v in data)
        ax.set_ylim(0, ymax * 1.08 if ymax else 1)
        ax.set_title(title)
        ax.set_xlabel("组")
    fig.suptitle("敏感性：各组资源用量（箱线；含失败；不含控制器中断、不用 0 填 ledger）")
    _save(fig, "resources_by_arm")


def fail_mix(rows: list[dict], classify) -> None:
    kinds = [
        "passed",
        "stage_cap",
        "i_precheck",
        "global_budget",
        "hidden_implementation_failure",
        "failed_without_hidden_eval",
        "protocol",
        "ownership_or_path",
        "api_or_harness_error",
        "interrupted",
    ]
    fig, ax = plt.subplots(figsize=(9, 5.2))
    bottom = np.zeros(len(ARMS))
    cmap = plt.cm.tab10
    for i, kind in enumerate(kinds):
        vals = []
        for a in ARMS:
            xs = [r for r in rows if r.get("arm") == a]
            vals.append(sum(1 for r in xs if classify(r) == kind))
        ax.bar(ARMS, vals, bottom=bottom, label=kind, color=cmap(i % 10))
        bottom += np.array(vals, dtype=float)
    ax.set_ylabel("分配数")
    ax.set_title("敏感性：结局构成（interrupted=控制器中断计0，不是模型失败）")
    ax.legend(fontsize=8, ncol=2, loc="upper center", bbox_to_anchor=(0.5, -0.18), frameon=False)
    fig.subplots_adjust(bottom=0.28)
    _save(fig, "fail_mix")


def task_heatmap(rows: list[dict]) -> None:
    tasks = sorted({r["task_id"] for r in rows})
    mat = np.zeros((len(tasks), len(ARMS)))
    for i, t in enumerate(tasks):
        for j, a in enumerate(ARMS):
            xs = [r for r in rows if r["task_id"] == t and r.get("arm") == a]
            mat[i, j] = sum(1 for r in xs if r.get("status") == "passed") / len(xs) if xs else 0
    fig, ax = plt.subplots(figsize=(6, 6))
    im = ax.imshow(mat, cmap="Blues", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(ARMS)), ARMS)
    ax.set_yticks(range(len(tasks)), tasks, fontsize=8)
    ax.set_title("敏感性：任务 × 组 通过率")
    fig.colorbar(im, ax=ax, fraction=0.03, label="通过率")
    _save(fig, "task_arm_heatmap")


def da_forest(task_means: dict[str, float], point: float, lo: float, hi: float) -> None:
    tasks = sorted(task_means)
    ys = np.arange(len(tasks))
    fig, ax = plt.subplots(figsize=(8, 5.5))
    vals = [100 * task_means[t] for t in tasks]
    ax.axvline(0, color="#333", lw=0.8)
    ax.axvline(10, color="#d62728", ls="--", lw=0.8, label="+10pp 采用阈值")
    ax.scatter(vals, ys, color="#4c78a8")
    ax.axvspan(100 * lo, 100 * hi, color="#4c78a8", alpha=0.15, label="总体 95% CI")
    ax.axvline(100 * point, color="#4c78a8", ls=":", label=f"总体点估计 {100*point:.1f}pp")
    ax.set_yticks(ys, tasks, fontsize=8)
    ax.set_xlabel("D_soft−A 成功率差（百分点）")
    ax.set_title("探索性敏感性：按任务的 D_soft−A 差（不是独立新任务确认）")
    ax.legend(fontsize=8)
    _save(fig, "dsoft_by_task")
