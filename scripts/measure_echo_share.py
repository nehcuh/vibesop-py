#!/usr/bin/env python3
"""gate35 回声基线测量 (裁决 1 / 修订 G): agent-prompt 形状占比。

对指定项目根（--project-root，默认 cwd）读
``.vibe/observability/spans.jsonl`` 与 ``cluster_candidates.jsonl``，
报告三组数：

(a) miss 池 agent-prompt 形状占比 —— 双报:
    完整谓词 ``_is_agent_prompt_shape``（含 150 字符长度规则, 冻结）与
    展示层前缀谓词 ``_has_agent_prompt_prefix``（修订 C）。
(b) **已入队卡片**（pending 候选, project + global 双 scope 合并去重,
    与 ``vibe skill discover`` 队列同口径 —— cluster_id 去重、保留
    project_distribution 更大的记录、平手 project scope 优先, 参照
    skill_commands ``_gather_scoped_candidates`` /
    dashboard/_discoveries ``_load_scoped_candidates``）的前缀谓词
    占比 —— 重议门槛口径（不做清单: 队列卡片回声率 >80% 且长 query
    风险人口 <1% 才可重议 intake 过滤；卡片口径钉死用前缀谓词,
    与展示一致）。**(b) 分母只滤 ``status != "pending"``, 不含指纹
    负名单/静音的可见性过滤, 与 discover 默认视图有轻微口径差
    （方向: 可能高估卡片回声率 —— 已 dismiss/mute 的回声卡仍在
    分母里）。
(c) ">150 字符且非 agent 前缀形状"的 miss 占比 —— 长 query 风险人口
    （风险人口, 不是"误杀率", 修订 G 措辞修正）。

miss 池推导与 ``scan_candidates`` 同口径（is_route_miss_span 且非
低信息 query, skill_promote.py:1446-1449）——只读, 不做任何 intake
过滤改动。**已知偏差**: scan 侧还有一道 legacy age-out
（``project_id == "default"`` 的 pre-W5.0 spans 默认剔除,
skill_promote.py:1404-1408）, 本脚本分母含 legacy spans 时会与真实
扫描池有偏差（偏保守, 分母偏大）。结果打印并写
``.omx/artifacts/gate35-echo-measure.md``（目录可写时）。样本不足
时明说（沿用 calibrate_behavior_threshold.py 的纪律）。

Usage:
    uv run python scripts/measure_echo_share.py [--project-root PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from vibesop.core.observability.clustering import _extract_query
from vibesop.core.observability.gold_detection import is_route_miss_span
from vibesop.core.observability.skill_promote import (
    _AGENT_PROMPT_MAX_LEN,
    _has_agent_prompt_prefix,
    _is_agent_prompt_shape,
    _is_low_information_query,
)

ARTIFACT = Path(".omx/artifacts/gate35-echo-measure.md")
# ≥30 再议纪律 (skill_promote.py:164-165): 低于此样本量只报数字不下结论。
MIN_SAMPLE = 30


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _miss_queries(spans: list[dict]) -> list[str]:
    """scan_candidates 同口径 miss 池 (skill_promote.py:1429-1433)。"""
    out = []
    for s in spans:
        if not is_route_miss_span(s):
            continue
        q = _extract_query(s) or ""
        if _is_low_information_query(q):
            continue
        out.append(" ".join(str(q).split()).lower())
    return out


def _pending_cards(project_root: Path) -> list[dict]:
    """Pending candidates from BOTH scopes, deduped by cluster_id.

    discover 队列同口径 (gate35 复审 claude-MAJOR): project
    (``<root>/.vibe/observability``) + global (``~/.vibe/observability``)
    合并, cluster_id 去重保留 ``project_distribution`` 更大的记录,
    平手 project 优先（迭代顺序 project-first, 仅严格更大才替换）——
    与 ``_gather_scoped_candidates`` / ``_load_scoped_candidates``
    的 lockstep 规则一致。scan-candidates --cross-project 的候选只落
    global store, 漏掉它会让 (b) 口径系统性低估。
    """
    scope_dirs = (
        project_root / ".vibe" / "observability",
        Path.home() / ".vibe" / "observability",
    )
    by_id: dict[str, dict] = {}
    for obs_dir in scope_dirs:
        for c in _load_jsonl(obs_dir / "cluster_candidates.jsonl"):
            if c.get("status", "pending") != "pending":
                continue
            cid = c.get("cluster_id")
            if not isinstance(cid, str) or not cid:
                continue
            existing = by_id.get(cid)
            if existing is None or len(c.get("project_distribution") or {}) > len(
                existing.get("project_distribution") or {}
            ):
                by_id[cid] = c
    return list(by_id.values())


def measure(spans: list[dict], pending: list[dict]) -> dict[str, int]:
    miss = _miss_queries(spans)
    n = len(miss)
    full = sum(1 for q in miss if _is_agent_prompt_shape(q))
    prefix = sum(1 for q in miss if _has_agent_prompt_prefix(q))
    risk = sum(
        1 for q in miss if len(q) > _AGENT_PROMPT_MAX_LEN and not _has_agent_prompt_prefix(q)
    )

    # 已入队卡片口径: pending 候选 (双 scope 去重后), 代表 query
    # (queries[0]) 过前缀谓词 —— 与展示层 candidate_agent_echo 同规则
    # (标集=否决集)。
    echo_cards = 0
    for c in pending:
        queries = c.get("queries") or []
        if queries and _has_agent_prompt_prefix(str(queries[0])):
            echo_cards += 1

    return {
        "miss_pool_size": n,
        "miss_full_shape": full,
        "miss_prefix_shape": prefix,
        "miss_long_non_prefix": risk,
        "pending_cards": len(pending),
        "echo_cards": echo_cards,
    }


def _pct(part: int, whole: int) -> str:
    return f"{part}/{whole} = {part / whole:.1%}" if whole else "0/0 = n/a"


def render(project_root: Path, m: dict[str, int]) -> str:
    lines = [
        "# gate35 回声基线测量 (measure_echo_share.py)",
        "",
        f"- project_root: `{project_root}`",
        f"- measured_at: {datetime.now(UTC).isoformat(timespec='seconds')}",
        "",
        "## 结果",
        "",
        f"- miss 池大小: {m['miss_pool_size']}",
        "- (a) miss 池 agent-prompt 形状占比（双报）:",
        f"  - 完整谓词 `_is_agent_prompt_shape`（含 150 字符规则）: "
        f"{_pct(m['miss_full_shape'], m['miss_pool_size'])}",
        f"  - 前缀谓词 `_has_agent_prompt_prefix`（修订 C, 无长度规则）: "
        f"{_pct(m['miss_prefix_shape'], m['miss_pool_size'])}",
        f"- (b) 已入队卡片回声占比（前缀谓词, 重议门槛口径）: "
        f"{_pct(m['echo_cards'], m['pending_cards'])}"
        f"（pending 卡片 {m['pending_cards']} 张, project+global 双 scope 去重）",
        f"- (c) 长 query 风险人口（>{_AGENT_PROMPT_MAX_LEN} 字符且非 agent 前缀）miss 占比: "
        f"{_pct(m['miss_long_non_prefix'], m['miss_pool_size'])}",
        "",
        "## 重议门槛参照（gate34 不做清单, 修订 G）",
        "",
        "队列卡片回声率 >80% 且长 query 风险人口占比 <1% 才可重议 intake 过滤。",
    ]
    if (m["miss_pool_size"] or 0) < MIN_SAMPLE:
        lines += [
            "",
            f"⚠ SAMPLE TOO THIN: miss 池 {m['miss_pool_size']} < {MIN_SAMPLE} —— "
            "只报数字, 不下结论（沿用 ≥30 再议纪律）。",
        ]
    if not m["pending_cards"]:
        lines += [
            "",
            "⚠ 无 pending 候选卡片: (b) 卡片口径无法计算 "
            "（先运行 `vibe skill scan-candidates` 入池后再测）。",
        ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        default=".",
        help="项目根（读 .vibe/observability 下的 spans/candidates; 默认 cwd）",
    )
    parser.add_argument(
        "--out",
        default=None,
        help=f"结果 markdown 落盘路径（默认 <project-root>/{ARTIFACT}; 目录不可写则只打印）",
    )
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    obs = root / ".vibe" / "observability"
    spans = _load_jsonl(obs / "spans.jsonl")
    pending = _pending_cards(root)
    if not spans and not pending:
        print(f"FATAL: no spans/candidates under {obs} (or global scope)", file=sys.stderr)
        return 1

    text = render(root, measure(spans, pending))
    print(text)

    out = Path(args.out) if args.out else root / ARTIFACT
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"written: {out}")
    except OSError as exc:
        print(f"(artifact not written — {exc}; stdout above is the record)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
