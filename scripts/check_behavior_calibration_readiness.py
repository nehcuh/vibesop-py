#!/usr/bin/env python3
"""R4 就绪度检查：``_BEHAVIOR_JACCARD_THRESHOLD`` 是否已具备重新标定的数据条件。

预注册：``.omx/artifacts/optimization-convergence-r4-prereg.md`` §1(四条门槛)
前序：``.omx/artifacts/m3-behavior-calibration.md``(2026-08-21:正例对 = 0,exit 2 fail-closed)

为什么单独做这个脚本
--------------------
前序标定的结论是"证据不足",并给出触发条件:"任一候选簇积累 ≥2 条带工具序列的 trace"。
**该触发条件目前靠人记忆与手工重跑**。本脚本把它变成可机器检查的门槛,
使"什么时候该复检"不再依赖某人想起来 —— 这是把一个待收口项变成可运营项的最小代价。

本脚本 **只读**,不改任何生产数据、不写任何标定结论、不固化任何阈值。

退出码
------
- ``0`` 四条门槛全部满足 → 可以开跑标定
- ``1`` 未就绪 → 保持 ``unavailable``,不要跑决策带
- ``2`` 数据文件缺失或不可读 → fail-closed

四条门槛(prereg §1,写死)
------------------------
1. 至少 1 个候选簇拥有 ≥2 条带非空 bigram 的 trace
2. 跨簇负例对 ≥ 30
3. 正例对 ≥ 30
4. 入选 trace 的 span producer 覆盖 ≥ 2 个平台

设计约束
--------
- 复用 ``core.observability.behavior_consistency`` 的既有口径(folded 口径、
  复合键 ``(project_id, task_id)``、防泄漏去重),**不另立第二套实现** ——
  双处定义会让两个数字互相矛盾(gate24 pi#7 单一来源原则)。
- 隐私:只读 tool span 的 ``name``,绝不读 ``input_data`` / 参数值。
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: 门槛(prereg §1)。改这些数即等于改判据,须先改预注册文件。
_MIN_POSITIVE_PAIRS = 30
_MIN_NEGATIVE_PAIRS = 30
_MIN_PLATFORMS = 2
_MIN_SEQUENCES_IN_A_CLUSTER = 2


@dataclass
class Readiness:
    clusters_with_sequences: int
    total_sequences: int
    positive_pairs: int
    negative_pairs: int
    producers: set[str]
    best_cluster_seq_count: int

    @property
    def gates(self) -> dict[str, bool]:
        return {
            "g1_cluster_has_2_sequences": self.best_cluster_seq_count
            >= _MIN_SEQUENCES_IN_A_CLUSTER,
            "g2_negative_pairs": self.negative_pairs >= _MIN_NEGATIVE_PAIRS,
            "g3_positive_pairs": self.positive_pairs >= _MIN_POSITIVE_PAIRS,
            "g4_producer_coverage": len(self.producers) >= _MIN_PLATFORMS,
        }

    @property
    def ready(self) -> bool:
        return all(self.gates.values())

    def as_dict(self) -> dict[str, Any]:
        return {
            "clusters_with_sequences": self.clusters_with_sequences,
            "total_sequences": self.total_sequences,
            "positive_pairs": self.positive_pairs,
            "negative_pairs": self.negative_pairs,
            "producers": sorted(self.producers),
            "best_cluster_seq_count": self.best_cluster_seq_count,
            "gates": self.gates,
            "ready": self.ready,
        }


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        msg = f"not found: {path}"
        raise FileNotFoundError(msg)
    rows: list[dict[str, Any]] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            rows.append(json.loads(stripped))
        except json.JSONDecodeError as exc:
            msg = f"{path}:{lineno} invalid JSON: {exc}"
            raise ValueError(msg) from exc
    return rows


def _producer_of(span: dict[str, Any]) -> str:
    """尽力取 producer 标识;取不到归 ``"unknown"``(不丢弃该 span)。"""
    for key in ("producer", "source", "platform", "sdk", "client"):
        value = span.get(key)
        if isinstance(value, str) and value:
            return value
    return "unknown"


def check_readiness(
    spans: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> Readiness:
    """按行为一致性模块的既有口径统计四条门槛。

    TODO(r4-wire): 直接 import ``core.observability.behavior_consistency`` 的
    ``tool_sequence_items_for_tasks`` 与 ``_bigrams``,复用生产口径而非在
    本脚本内复写。当前留作显式接线点,原因:该模块的候选键展开需要
    ``cluster_candidates.jsonl`` 的实际字段形状(``task_ids`` 布局),
    该形状须在真实数据上核对一次,避免用猜测的字段名静默产出错误的门槛判断。
    接线前本函数**不得**用于对外结论。
    """
    del spans, candidates
    msg = (
        "readiness computation not wired yet (TODO(r4-wire)): must reuse "
        "core.observability.behavior_consistency locators instead of a second "
        "implementation. See docstring."
    )
    raise NotImplementedError(msg)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--spans",
        type=Path,
        default=Path(".vibe/observability/spans.jsonl"),
        help="span 数据(默认沿用前序标定的路径)",
    )
    parser.add_argument(
        "--candidates",
        type=Path,
        default=Path(".vibe/observability/cluster_candidates.jsonl"),
        help="候选池数据",
    )
    parser.add_argument("--json", action="store_true", help="只输出 JSON,便于 CI 消费")
    args = parser.parse_args(argv)

    try:
        spans = _load_jsonl(args.spans)
        candidates = _load_jsonl(args.candidates)
    except (FileNotFoundError, ValueError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2

    try:
        result = check_readiness(spans, candidates)
    except NotImplementedError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2

    if args.json:
        print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"spans: {len(spans)}  candidates: {len(candidates)}")
        print(
            f"clusters with sequences: {result.clusters_with_sequences}  "
            f"best cluster sequences: {result.best_cluster_seq_count}"
        )
        print(f"pairs: positive = {result.positive_pairs}, negative = {result.negative_pairs}")
        print(f"producers: {sorted(result.producers)}")
        for name, ok in result.gates.items():
            print(f"  [{'x' if ok else ' '}] {name}")
        print(
            "READY: run scripts/calibrate_behavior_threshold.py"
            if result.ready
            else "NOT READY: keep _BEHAVIOR_JACCARD_THRESHOLD unavailable (prereg §1)"
        )

    return 0 if result.ready else 1


if __name__ == "__main__":
    sys.exit(main())
