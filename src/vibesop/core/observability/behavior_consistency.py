"""M3 行为一致性门 — tool-sequence bigram-Jaccard.

Design contract: ``.omx/artifacts/m12-product-design.md`` (M3, 阈值哲学).
同一 miss/gold 模式的多次复现,如果 agent 的处理方式(工具调用序列)也
相似,说明这是稳定工作流,候选可信度更高。

Three-state semantics (gate decision, recorded here because the design doc
原文只写 consistent/unavailable 两态 —— "有数据且低于阈值" 不能诚实归入
unavailable;设计文档 gate24 已同步为三态):

- ``consistent``:  ≥ ``_MIN_SEQUENCES`` 条有效序列且成对 Jaccard 聚合值 ≥ 阈值
- ``divergent``:   数据够但不达标(模式复现但处理方式各异 —— 候选可信度降档信号)
- ``unavailable``: 数据不足(平台无 hook、有效序列 < ``_MIN_SEQUENCES``);
  字段缺失(None)在展示层另有 "not_collected / 未采集" 标注
  (``discovery.behavior_evidence_label``)

Known residual risk (gate24 pi#5, accepted): 单工具 trace 的 bigram 集为
空,不参与成对计数 —— 一个簇若夹着单工具离群 trace(处理方式与主流
不同的一次性调用),``consistent`` 判定可能对这类簇高估(离群 trace
被静默排除而非拉低分数)。序列提取侧不区分"平台无 hook"与"该 trace
恰好一次调用",这是诚实盲区,记录在案。

Privacy (设计 §隐私边界): 只读 tool span 的 ``name``(工具名),绝不读
``input_data`` / 参数值。

Knob 归属(设计 §阈值哲学): 不进 RoutingConfig —— 模块常量
``_BEHAVIOR_JACCARD_THRESHOLD`` + scan-candidates CLI flag,沿用
skill_promote.py 的 miss knob 惯例。
"""

from __future__ import annotations

import itertools
from typing import Any, Literal

BehaviorState = Literal["consistent", "divergent", "unavailable"]

#: 占位起点 (M12 设计 §阈值哲学 "bigram-Jaccard ≥ 0.5,标定后固化").
#: gate M3 标定结果(.omx/artifacts/m3-behavior-calibration.md):cmspark
#: 真实数据上候选簇内同簇正例对 = 0(没有任何候选簇有 ≥2 条带工具序列的
#: trace),跨簇负例对 = 1 —— 决策带证据不足,0.5 维持为待验证起点,
#: 待更多平台 hook 数据后复检。
_BEHAVIOR_JACCARD_THRESHOLD = 0.5

#: 少于 2 条有效序列无法构成任何成对比较 → unavailable。
_MIN_SEQUENCES = 2

#: 三态合法值 —— skill_promote.ClusterCandidate 的运行时校验从这里
#: import(gate24 pi#7: 单一来源,不双处定义)。
_VALID_BEHAVIOR_STATES: frozenset[str] = frozenset({"consistent", "divergent", "unavailable"})


def _tool_name(span: dict[str, Any]) -> str | None:
    """Read the tool name from a tool_call span (privacy: name ONLY).

    Real data carries two shapes: ``tool:Read`` (newer, no space) and
    ``tool: read_file`` (older producer). Both normalize to the bare name.
    """
    if span.get("span_kind") != "tool_call":
        return None
    name = span.get("name")
    if not isinstance(name, str) or not name.startswith("tool:"):
        return None
    bare = name.removeprefix("tool:").strip()
    return bare or None


def _collapse_consecutive(names: list[str]) -> list[str]:
    """折叠连续同名调用,保留非连续重复(gate24 MINOR-C 诚实版理由).

    ``_bigrams`` 返回 set,长重复段不存在"数量淹没";真正的理由是:
    (X, X) 自环 bigram 在 set 语义下对序列间比较没有区分度(任意两条
    含重复段的 trace 共享它),折叠后 bigram 集反映的是"不同工具间的
    转移"而非重复执行。已知方向性偏差:折叠会抬高含长重复段 trace 的
    得分(gate24 claude 实测一例 0.5 → 1.0)—— 接受,因为连续重复
    本身不携带顺序信息;标定脚本输出 folded/unfolded 双口径对照,
    复检时可量化该偏差。非连续重复(Read→Grep→Read)保留 —— 那是
    真实的"回看"行为信号。
    """
    out: list[str] = []
    for name in names:
        if not out or out[-1] != name:
            out.append(name)
    return out


def tool_sequence_items_for_tasks(
    task_keys: list[tuple[str, str]],
    spans: list[dict[str, Any]],
    *,
    collapse: bool = True,
) -> list[tuple[str, list[str]]]:
    """候选复合键 → ``[(分组键, 工具有序序列)]``(每 trace 一条).

    Join path (gate24 MAJOR-B 修订版):

    - 候选键是 ``(project_id, task_id)`` 复合 —— 与聚类键口径一致
      (``Cluster.task_keys``, W5.1);裸 task_id join 会把跨项目扫描中
      同 task_id 的外项目 trace 混入。无 project_id 的 legacy span 按
      现有惯例归 ``"default"``。
    - tool span 归属: ``parent_span_id`` 指向候选 route span 为准;
      parent 不是候选 route(孤儿 / 嵌套非 route 子任务的 tool span)
      时回退 ``trace_id`` ∈ 候选 traces。OR-union 方向(gate24 双路
      复审决定保留,真实数据 159/159 两键一致): union 不丢嵌套子
      任务的 tool span。
    - 分组键与归属键统一(gate24 pi#4): 经 parent 归属的 span 按
      parent 链的 trace 分组(parent route 的 trace_id;parent 无
      trace_id 时用 parent span id),不再优先取自身 trace_id ——
      否则嵌套 trace 的工具调用会被错误地按自身 trace 聚成独立序列。

    单工具序列保留在返回中(它们是"有 hook 数据"的证据);bigram 为空
    导致其无法参与成对计数,由 ``assess_behavior_consistency`` 处理。
    """
    wanted = {(str(pid or "default"), tid) for pid, tid in task_keys}
    if not wanted:
        return []
    candidate_routes: dict[str, dict[str, Any]] = {}
    candidate_trace_ids: set[str] = set()
    for span in spans:
        name = span.get("name")
        if not isinstance(name, str) or not name.startswith("route:"):
            continue
        key = (str(span.get("project_id") or "default"), span.get("task_id"))
        if key not in wanted:
            continue
        span_id = span.get("id")
        if isinstance(span_id, str) and span_id:
            candidate_routes[span_id] = span
        trace_id = span.get("trace_id")
        if isinstance(trace_id, str) and trace_id:
            candidate_trace_ids.add(trace_id)
    if not candidate_routes and not candidate_trace_ids:
        return []

    by_trace: dict[str, list[tuple[str, str]]] = {}
    for span in spans:
        tool = _tool_name(span)
        if tool is None:
            continue
        parent = candidate_routes.get(str(span.get("parent_span_id") or ""))
        if parent is not None:
            # parent 归属 → 分组键取 parent 链的 trace(gate24 pi#4)
            parent_trace = parent.get("trace_id")
            group = (
                parent_trace
                if isinstance(parent_trace, str) and parent_trace
                else str(span.get("parent_span_id"))
            )
        else:
            trace_id = span.get("trace_id")
            if not (isinstance(trace_id, str) and trace_id in candidate_trace_ids):
                continue
            group = trace_id
        by_trace.setdefault(group, []).append((str(span.get("started_at") or ""), tool))

    items: list[tuple[str, list[str]]] = []
    for group, entries in by_trace.items():
        entries.sort(key=lambda e: e[0])
        names = [name for _ts, name in entries]
        items.append((group, _collapse_consecutive(names) if collapse else names))
    return items


def tool_sequences_for_tasks(
    task_keys: list[tuple[str, str]], spans: list[dict[str, Any]]
) -> list[list[str]]:
    """薄封装: 只要序列不要分组键(生产路径用;标定脚本用 items 版
    做同 trace 去重 —— gate24 MAJOR-A)。"""
    return [seq for _key, seq in tool_sequence_items_for_tasks(task_keys, spans)]


def _bigrams(sequence: list[str]) -> set[tuple[str, str]]:
    return set(itertools.pairwise(sequence))


def _jaccard(a: set[tuple[str, str]], b: set[tuple[str, str]]) -> float:
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def assess_behavior_consistency(
    task_keys: list[tuple[str, str]],
    spans: list[dict[str, Any]],
    *,
    threshold: float = _BEHAVIOR_JACCARD_THRESHOLD,
) -> tuple[BehaviorState, float | None, int]:
    """→ (state, score, n_sequences) for one candidate cluster.

    ``task_keys`` 是 ``(project_id, task_id)`` 复合键(``Cluster.task_keys``,
    gate24 MAJOR-B —— 裸 task_id 会跨项目混入外项目 trace)。

    ``n_sequences`` counts only sequences with a NON-EMPTY bigram set —
    a single-tool trace cannot participate in pairwise similarity, so it
    is honest evidence of hook coverage but not of consistency. (A trace
    of one tool call carries no ordering information.)

    Aggregation: MEAN of pairwise Jaccards. Chosen over min/median on
    principle, not on calibration data (正例对样本量为零,见模块常量注):
    min 让单条异常 trace 否决整个簇(过敏感),median 在小 n(n=2)下与
    mean 等价;n 大时若数据积累显示区分度不足再复检。
    """
    if not (0.0 <= threshold <= 1.0):
        msg = f"threshold must be in [0.0, 1.0], got {threshold}"
        raise ValueError(msg)
    sequences = tool_sequences_for_tasks(task_keys, spans)
    bigram_sets = [bg for seq in sequences if (bg := _bigrams(seq))]
    n = len(bigram_sets)
    if n < _MIN_SEQUENCES:
        return "unavailable", None, n
    scores = [_jaccard(bigram_sets[i], bigram_sets[j]) for i in range(n) for j in range(i + 1, n)]
    score = sum(scores) / len(scores)
    state: BehaviorState = "consistent" if score >= threshold else "divergent"
    return state, score, n
