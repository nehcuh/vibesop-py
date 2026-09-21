---
id: builtin/task-briefing
name: task-briefing
description: >-
  Use when asked to write a task brief / task assignment (任务书) before
  executing or delegating a non-trivial task, or to turn a coarse request
  into a complete one (写任务书, 先写任务书, 把任务书写满, task brief,
  write a task brief). Not for executing an already-complete brief.
tags: [task brief, briefing, spec, requirements, 任务书, 写满任务书,
       acceptance criteria, non-goals]
triggers:
  - "写任务书"
  - "先写任务书"
  - "把任务书写满"
  - "写一份任务书"
  - "task brief"
  - "write a task brief"
  - "write the task brief first"
  - "/task-briefing"
version: 1.0.0
allowed-tools:
  - Read
  - Bash
intent: >-
  Turn a coarse request into a complete task brief — goal, deliverables,
  acceptance criteria, constraints, non-goals — before execution or
  delegation, so downstream work is verifiable and skills land where the
  brief leaves gaps.
namespace: builtin
type: prompt
---

# Task Briefing — 先写满任务书,再动手

> Trigger: "帮我写一份任务书" / "write a task brief for this task"

Grounding (F1, research-survey §7): 技能的价值以 spec 缺口为前提。
任务书写满时,先验就能盖住任务(R1-R3/R7 五次平手);任务书粗糙时,
技能与返工才显形(R8 人评,盲评未结算)。任务书质量是那个杠杆——
本技能只做一件事:**在执行前把粗任务变成写满的任务书**。

## When NOT to use

- 任务书已经写满(有目标、有交付物、有验收、有非目标)——直接执行,
  不要为了走流程重写它
- 琐碎任务(改一个 typo、回答一个问题)——写任务书的成本超过任务本身
- 用户要的是**执行**一份既有任务书——那是执行技能的事
- 会话收尾、进度保存 → `session-end`
- 用户只是要评估/验收既有产物 → `verify-result`

## Steps

### 1. 收集缺口

对照清单逐项检查请求,列出缺什么:

- **目标**:做完之后世界有什么不同?一句话说不出就是缺
- **交付物**:产出落在哪个文件/目录/系统?看不到路径就是缺
- **验收**:怎么判定完成?能落到命令、退出码、可复查的输出吗?
  「看起来对了」不算
- **边界(非目标)**:明确**不要**做什么?没有非目标,执行者会自行扩权
- **上下文**:相关文件、既往决策、硬约束(环境、预算、期限)

已有信息不重复问;缺口能从仓库/文档/会话历史里查到的,先查再问。

### 2. 写满任务书

输出一份编号任务书,五个必备节:

1. **目标** — 一句话,动词开头
2. **交付物** — 具体路径/位置,一个交付物一行
3. **验收清单** — 每条可由命令输出、退出码或人工复查判定;
   写明跑什么命令、期望什么结果
4. **非目标** — 显式排除项(「不要 push」「不改 X」「不做 Y」)
5. **上下文与约束** — 指向既有材料,不复制正文

铁律:**每一行都要能追溯到用户原话或显式标注的假设**。
用户没说的,写成 `[假设:…]` 并在下一步确认,不得默默替用户拍板。

### 3. 确认或获准

- 交互可达:把任务书给用户确认,重点确认所有 `[假设:…]` 项
- 用户已明确授权连续执行(如「不要停下来问我」):引用授权原话,
  假设项记录在任务书里随交付一并汇报,不阻塞

### 4. 移交执行

任务书定稿后交给执行(同一 agent 继续或委派)。移交时说明:

- 写满的任务书上,路由到的技能按参考处理(任务书更具体时以任务书为准);
  信封若带 `[VibeSOP report-only] spec_gap: low` 注释,就是这个含义
- 粗糙任务书上,跟技能走——那是技能显形的地方(R8)
- 验收以任务书第 3 节为准,不用现场发明标准

## Anti-Patterns

- 重写一份已经写满的任务书(为流程而流程)
- 替用户发明需求——任务书里出现无来源、无 `[假设:…]` 标注的要求
- 把验收写成「完成 X 功能」这类不可判定的句子
- 用任务书绕开任务明确需要的技能(「任务书写了就不用读 SKILL.md」)
- 问用户任务书里已经回答了的问题
- 在第 3 步之前就开始改代码

## Exit Criteria

- [ ] 任务书五节齐全(目标/交付物/验收/非目标/上下文)
- [ ] 每条验收都能由命令、退出码或复查判定,并写明判定方式
- [ ] 每一行需求可追溯到用户原话或显式 `[假设:…]` 标注
- [ ] 用户已确认,或显式授权被引用(含未确认假设的处置方式)
- [ ] 未发生任何执行侧改动(写任务书阶段不动代码)
---
