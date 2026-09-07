# 仲裁合成 — next-opt-design-v0 → v1

> 日期：2026-09-07
> 三路：A 正确性 / B 架构契约 / C 产品表面（kimi）
> 终裁对象：固件 v0。v1 见 `.omx/artifacts/next-opt-design-v1.md`
> 本文件是仲裁，不是第四路新发现。

## 三路 Verdict

| 路 | 镜头 | Verdict |
|---|---|---|
| A | 实验口径 / 方法论 | NEEDS_FIX |
| B | 架构接线 | NEEDS_FIX |
| C | 产品/声明/部署 | NEEDS_FIX |

**仲裁：v0 NEEDS_FIX。主线成立，W1 可在 v1 契约下开工，不得按 v0 字面实现。**

## 亲证（仲裁人，非评审转述）

| 主张 | 路 | 亲证 | 裁决 |
|---|---|---|---|
| SQUAD/ORCHESTRATE 走 `router.orchestrate()`，`is_multi_intent` 后 `mode="orchestrate"` | A,B | `agent_runtime.py:610-633` | **确认** |
| orchestrate 跳过单技能 inject / 空正文 demote | A,B | `:754-758` | **确认** |
| hook 活路径发 `[VibeSOP Execution Plan]`，不是 `[ACTIVE SKILL]`；无 `skill_content` 键 | A,B | `to_hook_response` `:183-201` | **确认** |
| `filter_routable` 在 EXPLICIT 之前 | B | `unified.py:556-613` | **确认** |
| `filter_management_candidates` 在 EXPLICIT 之后、early 层之前，注释写明 EXPLICIT exempt | B | `unified.py:682-686` | **确认** 作为 D1 过滤缝 |
| `has_match` 排除 FALLBACK_LLM，裸 `expect: []` 把 fallback 算过 | A,B | `models.py:217-219`；`eval_routing.py` 文档 | **确认** |
| 短查询 ≥2 roles / composite → ORCHESTRATE；长查询默认 ORCHESTRATE；squad_needed 仍进 SQUAD | A,B | `intent_interceptor.py:290-367` | **确认** |
| Claude adapter 把技能原文拷进 `output_dir/skills/` | C | 未逐行打开本轮，C 给了 `claude_code.py:360-367`；与 adapter 惯例一致，**作 P1 采纳**，v1 要求 pin 测试而非口头 | **采纳，开工前 v1 写进契约** |

## 发现收敛

### 确认 → 写入 v1（不改则不得按 v0 开工）

| ID | 来源 | 内容 |
|---|---|---|
| P0-hook | A,B 2/2 | D3 断言必须打 Execution Plan / `plan.steps`，禁止只 grep `[ACTIVE SKILL]` / `skill_content` |
| P0-filter | B | D1 不得用 `filter_routable` 丢 disable 卡；复用 management 过滤缝（EXPLICIT 全量池，其后剥离） |
| P0-demote | B | orchestrate 不走空正文 demote；fail-closed 必须剥计划步骤 id |
| P0-siblings | A,B 2/2 | D2 只删 ROLE_KEYWORDS 不够：短查询 composite→ORCHESTRATE、heuristic squad_needed、LLM 角色表、默认长句 ORCHESTRATE 都要停用「角色词计数」 |
| P1-L1 | A | L1 改条件句：本周期只保证**打标卡**默认不注入 |
| P1-L3 | A | L3 改 won't-grow，不把未测格子写成唯一增量定理 |
| P1-expect | A,B 2/2 | `must_not_inject` 的 ok1：primary 空 **且** 不得 fallback_llm；`--force` 不得吸收该类失败 |
| P1-Q5 | A,B,C 3/3 | 生成规则改口升格为 W1 必做；改模板源 + grep 验收 |
| P1-entry | C | D2 必须列出显式并行入口（CLI flag + hook 口语句式） |
| P1-docs | C (+A L5) | 文档轨含 GOALS/CHANGELOG/architecture；L5 改成冻结增量 + 撤回 squad auto-trigger，不把已发布市场/已落地 deprecate 标 won't-do |
| P1-adapter | C | D1 作用域 = vibe 路由注入层；`vibe build` 副本必须透传字段，并声明无该语义的平台副本树怎么处理 |
| P1-instinct | A,B 2/2 | D4 写明 auto-promote 已能经 instinct boost 改 primary |

### 驳回 / 降级

- C「无 P0」：A/B 的 hook 假绿是真 P0（验收与已记录伤害不对齐）。不采纳 C 的「代码可按 v0 先行」。
- 「29 字段会炸」：三路都否定。Q1 锁一等字段。
- 把整机流水线塞回 W1：三路都确认 **没有**。保持 L4。
- 再做一个专家系统判小队：禁止。显式并行词典必须极小。

## 开放问题终裁（3/3 一致处直接锁）

| Q | 终裁 |
|---|---|
| Q1 | 一等 `SkillSpec.disable_model_invocation`。parser kebab 映射 + 候选 stamp。不改 extra=forbid。 |
| Q2 | 删除 ROLE_KEYWORDS 快路径，**同时**拆同源角色编制（见 P0-siblings）。并行另写小词典，禁止复用实现/审查/测试/架构。 |
| Q3 | 同一 `routing_eval.yaml` + `category: must_not_inject`，且 category **改变 ok1**。 |
| Q4 | W1.1，不进 W1。 |
| Q5 | W1 必做。改适配器模板源与生成物；§7 加可 grep 文案探针。 |

## 给确认轮（kimi / pi）的问题

请只核对：合成是否歪曲了各路原意；v1 是否把上表「确认」项写进契约；有没有把未确认项升成 P0。不要再发明一条新主线。
