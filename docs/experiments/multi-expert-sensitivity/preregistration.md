# 探索性敏感性分析（D_soft）预注册

**标签：探索性敏感性分析，受主实验诊断启发。不是独立新任务确认，不与原 360 池化。**

触发：原 360 中 D 失败至少一半为内部 `stage_budget_exhausted`（independent-* / exchange-*）。实测 72/72（independent-0: 68，independent-1: 4）。

决策记录：`/Users/huchen/Projects/vibesop-py/.experiment/sensitivity-decision.md`（主实验早期、first12 后预先写下，不是看完 360 再发明方案）。

## 设计

12 任务 × 2 spec × A（原样）/ D_soft × 3 repeat = **144**。

- seed **20260914**；并发 8；模型/工具/T=24000/I=400000/K=120/hang=600 与主实验相同。
- 新 A 与新 D_soft **同一批随机交错**，不能只拿新 D 和历史 A 比。
- A 不启用任何新机制。
- D_soft **必须** `stage_caps_for('D')` + `run_arm(..., arm='D')`（原 ROLE 提示）。禁止 `stage_caps_for('D_soft')` 变成无阶段限制。
- 唯一机制：independent-* 与 exchange-* 上的 `stage_budget_exhausted` 记录 `soft_close`，保留 history/private 产物，继续后续成员与整合。不增加额度、不改提示、不追加摘要调用、不合成缺失的 deliver note。
- integrate / 全局 T/I/K / API / hang / 最终截断 / 所有权：仍硬失败，计 0。
- 全部 144 失败保留，无选择重跑；不可池化原 360。

## 统计

使用**原冻结** `harness/analysis.py`：12 任务等权、配对 2 spec × 3 repeat、cluster bootstrap 20000、seed **20260913**、+10pp 阈值。比较 D_soft（映射为 D 仅用于该函数）相对**同批新 A**。`confirmatory=False`。

成功定义与主实验相同：总预算内交付 + 全部隐藏验收通过 + 无所有权/路径违规。`failed`/`error`/`interrupted` 记 0。

## 要回答的问题（不预设结果）

1. 硬阶段终止是否解释主实验 D 相对 A 的劣势？
2. 软结束后 D_soft 相对同批 A 的成功率/成本与区间如何？
3. 是否达到 +10pp？
4. 哪些判断仍不能做（纯角色效应、异质专家、整库、强弱模型、skills、盲评维护性）？

## 非目标

这不是「最好的多智能体」搜索，也不是对专家能力的一般确认。只隔离一条编排终止规则。
