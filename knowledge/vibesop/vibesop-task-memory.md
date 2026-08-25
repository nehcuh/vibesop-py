---
name: vibesop-task-memory
description: VibeSOP 任务记忆与本能学习环（v8.0+）— recall 语义召回过往轨迹、trace 观测回放、instinct 工具序列挖掘晋升、Discovery 候选队列（scan/promote/dismiss + shadow verifier）、跨项目可信池
type: domain_knowledge
tags:
  - vibesop
  - task-memory
  - instinct
  - recall
  - discovery
---

# VibeSOP 任务记忆与本能学习（v8.0+）

v8.0 引入的核心能力：**观测你的真实工作流，把重复模式沉淀为可复用资产**。整条链路分五个子系统。

## 任务记忆环（task-memory loop）

把"做过什么"变成"能查到什么"：

1. 每次路由/执行产生 **span**（含 session_id、project_id、task_id）写入本地 traces
2. query 派生 task_id（纯 query 派生，跨进程稳定）→ trace 聚类
3. 簇达到 gold 判定条件（如 ≥60 秒间隔的独立出现）标记为金标准任务
4. `vibe recall "<query>"` 用 embedding 余弦相似度语义检索过往轨迹，返回步骤序列与来源 trace

```bash
vibe recall "上次怎么修的 Windows 路径 bug"
vibe recall "<query>" --cross-project   # 跨项目召回（需池内有该项目）
```

中文 query 的 BM25 召回接近 0%，所以 embedding 检索是 day-1 必需项（MiniLM 级本地模型即可）。

## 观测与回放（observability）

```bash
vibe trace metrics          # span 聚合指标
vibe trace replay <id>      # 单 trace 回放
vibe dashboard              # Web 面板可视化
```

配合 conversation mirror：主会话与 sub-agent 内部过程（thinking/tool_calls/model/usage/stop_reason）全量镜像到本地，供回放与归因。

## 本能学习（instinct learning）

从会话工具序列中挖重复模式，成熟即晋升：

```bash
vibe analyze session   # 挖掘当前会话的工具序列模式
vibe instinct eval     # 晋升成熟候选：≥5 次出现 且 ≥80% 成功率
vibe instinct status   # 按置信度分带查看本能清单
```

后台采集靠 launchd（macOS）定时任务，文件存储带跨进程锁。

## Discovery 候选队列（技能蒸馏）

重复任务聚类 → 候选池 → 人工审阅：

```bash
vibe skill scan-candidates   # 聚类近期 spans，填充候选池
vibe skill candidates        # 队列视图：评分/模式/来源/行为/为什么在
vibe skill promote <id>      # 候选 → SKILL.md 草稿 + 状态翻转
vibe skill dismiss <id>      # 否决（支持 --shape agent-echo 批量）
```

队列设计要点：

- **自解释列头**——"为什么在"只从实存字段直译，不编造
- **agent-echo 识别**——子代理提示词回声簇打 `shape: agent-echo` 标沉底，可批量否决；promote 回声簇是允许的人工 override，但会给出警告（派生 skill_id 的 slug 来自回声文本，建议改语义名）
- **shadow verifier**——promote 时输出 PASS/WARN 徽章（无 FAIL、永不阻断），verdict 存 `promote_verdicts.jsonl`

## 跨项目可信池（cross-project pool）

```bash
vibe pool add    # 项目入池（幂等）
vibe pool list / status / remove
```

池内项目的沉淀经验可被其他项目 `recall --cross-project` 复用——例如在项目 A 修过的某类 bug，项目 B 遇到同类问题可直接召回。数据文件带原子写入与跨进程锁保护。

## 隐私边界

全部本地存储（项目 `.vibe/` 与全局 `~/.vibe/`）；未命中查询只存哈希计数；跨项目召回需要显式把项目加入可信池。
