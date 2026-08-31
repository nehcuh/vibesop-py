# 提案：Chrome 侧边栏「任务拆解清单」面板（v1.1 修订版）

> 状态：经四路推演（UX / 前端架构 / 对抗批判 / 竞品调研）+ Claude & Grok 双路复审（均为"有条件通过"）后的修订版
> 复审原始记录：`.omx/artifacts/ask-claude-task-plan-panel-review-*.md`、`.omx/artifacts/ask-grok-task-plan-panel-review-*.md`
> 修订说明：v1.0 中 9 项被双路一致判定为必改的问题已全部并入本文，标注【复审修订】

## 1. 背景与目标

Agent 识别到复杂任务时自动拆解为子任务并逐个执行。后端现实（vibesop 仓库）：

- `ExecutionPlan(plan_id, steps, status, execution_mode, workflow_pattern, is_dynamic, reorchestration_history)`，`PlanStatus = pending/active/completed/failed`
- `ExecutionStep(step_id, step_number, intent, status, started_at, completed_at, dependencies, parallel_group)`，`StepStatus = pending/in_progress/completed/skipped/failed`
- 拆解期上限 `MAX_SUB_TASKS = 5`；**Reorchestrator 每步完成后重新分析**，`ReorchestrationDecision = continue | append_steps | loop_back | escalate | terminate_early`——计划是非单调的
- 终态存在 `partial`（`_compute_final_status`），不能只看 `PlanStatus`
- 现有回调只有 phase 级 + `on_plan_ready`，**没有步骤级事件**

目标：让"它在干什么、要不要我插手"在侧边栏中环境化可见，不挤占对话主区，不展示无法干预的失败。

## 2. 交互设计

### 2.1 布局

侧边栏自上而下：顶栏（固定 48px）→ 任务清单面板（文档流内兄弟节点，非浮层）→ 对话区（flex:1，独立滚动，底部锚定）。

面板高度动画期间对话区用 `overflow-anchor` + stick-to-bottom 策略，避免消息区高度跳变两次【复审修订：Grok 布局跳动项】。

### 2.2 出现门槛

- 拆解出 **≥2 个子任务**且 `workflow_pattern ∈ {sequential, 依赖DAG}` 时才出现面板；tournament/squad/debate 等模式 v1 不渲染面板【复审修订：Grok 边界项】
- 由拆解器确定性触发，不交模型裁量（Cursor 的公开教训）
- 单任务、拆解失败时不出现面板
- 拆解进行中（`on_phase_start(decomposition/plan_building)`）显示"正在拆解任务…"占位条，失败即撤掉【复审修订：Grok 空态项】
- 1 步计划中途 `append_steps` 变 ≥2：面板中途插入，**不**自动高亮打扰

### 2.3 收起态（摘要条，~32px，默认态）

固定版式：`[状态色条] 正在「分析竞品页面」 · 2 完成 / 1 进行 / 2 等待`

- **计数规则【复审修订：双路一致判定 v1.0 的 `✓2/5` 与"已完成 N 步"自相矛盾】**：
  - 静态计划（pattern 白名单内、无 mutation）：可用 `x/N`（分母真实稳定）
  - 动态计划：`N 完成 / M 进行 / K 等待` 分项计数，不给分母
  - 完成态一律"✓ 共执行 N 步"（重跑次数小号标注），不带分母
  - `terminate_early`：`提前完成 · 未执行 M 步`，禁止显示 ✓5/5
- 320px 溢出收缩顺序：先耗时 → 再迷你进度条 → 再进行中文案截断【复审修订：Claude E7】
- 摘要条必须是 `aria-live="polite"` region；失败时输出文字"步骤「X」失败"，不靠呼吸闪烁当唯一信号【复审修订：双路 a11y 项】

### 2.4 展开态（清单）

- 单行 40px：状态图标（形状+颜色双编码）+ 序号 + intent 标题（单行省略，空 intent 降级为 input_query【复审修订：Grok】）+ 耗时；`max-height: 40vh` 内部滚动
- 失败行动作进 overflow 菜单或替换耗时位，不常驻双按钮（320px 放不下）【复审修订：Grok】
- **loop_back【复审修订：双路一致否决 v1.0 的"冻结已完成 + 划线替换行"——后端无 replace 语义】**：同一 `step_id` 回到 in_progress，行显示"重做中"视觉态 + 重跑次数角标 ×N；禁止静默 completed→in_progress 覆盖
- `append_steps`：新增行淡入 + "新"角标（保留至该步开始执行）
- 并行组：左侧竖线连接（polish，可推迟）

### 2.5 自动行为【复审修订：双路一致否决"自动展开确认"叙事】

- **v1 默认收起，不自动展开**。首次出现时摘要条 1.5s 高亮（不改对话区高度），之后不再提示
- "确认拆解正确性"如需支持，必须做成真 HITL（展开 + 暂停执行 + "就这么执行/调整"按钮，超时默认继续），列为阶段二可选项，不用自动展开冒充
- 用户手动收起后该 plan 内不再自动展开；**免打扰位与折叠状态一起按 `plan_id` 写入 `chrome.storage.session`**（不按 tabId、不靠内存）【复审修订：双路一致——side panel 是 window 级，任务是 conversation 级】
- **唯一强制展开例外：`escalate`（后端明确要求人介入）**
- 用户正在输入框打字时，豁免一切自动布局变化

### 2.6 失败与干预

- Agent 内部重试对用户隐藏；彻底失败（ErrorPolicy 用尽 / escalate）才升级为可见失败
- 可见失败时：收起态摘要条警示色 + aria-live 文字 + **内联动作**（单失败直接给"重试/跳过"，多失败聚合"2 个子任务失败 · 处理"）【复审修订：Claude M3——干预入口不能埋在永不自动展开的容器里】
- **skip 依赖语义（现在就要定的数据契约）**：有下游 `dependencies` 依赖时禁止单独跳过，提供"级联跳过"或阻断，不做行内装饰按钮
- 多 plan 并存：会话级单计划队列，新 plan 排队而非替换；切 tab 时面板不换皮

### 2.7 无障碍基线（纳入阶段一验收）

aria-expanded、aria-live polite、键盘可达、prefers-reduced-motion 下所有动画降级为即时切换、状态不单独依赖颜色。

## 3. 技术架构

### 3.1 分层【复审修订：双路一致否决"SW 做状态真源"】

```
Agent 后端（执行真源 + append-only 事件日志 + 单调 event_seq + 活跃计划回放窗口）
   ⇅ WebSocket（可断，指数退避重连，seq 断点续传）
Service Worker / Offscreen document（中继 + 热缓存 + 连接管理）
   ⇅ chrome.runtime.connect Port
Side Panel（投影 + 少量 UI 态：collapsed、manual_override、last_seen_seq）
```

- **event_seq 由后端单一写者分配**；SW 冷启后从 `storage.session` 快照 + 后端 seq 续传恢复；SYNC 增量仅在面板 seq ≥ 后端回放窗口起点时可用，否则全量快照；plan-not-found 有显式终态
- 需跨面板关闭存活则用 `chrome.offscreen` 持有 WS；否则接受"面板关闭即断开"但后端必须能 replay
- `storage.session` 快照只存 `{plan_id, seq, steps[{id,number,intent,status,started_at}], collapsed, manual_override}`，**不存产出文本**
- 砍掉：SW 端 100ms 合批、面板 rAF 批提交（分钟级低频事件，为不存在的负载设计）、`storage.local` 50 条历史环形缓冲（没有对应 UI）【复审修订：双路一致判定过度设计】

### 3.2 前置数据契约（先于 UI 开工）【复审修订：双路一致——没有这层协议，面板是空中楼阁】

1. **步骤级事件**：`plan_snapshot` / `step_transition{step_id, status, at, event_seq}` / `plan_terminal{final_status: completed|partial|failed|terminated_early}` / `plan_mutated{decision, ...}`——枚举全部 reorchestration 决策 ↔ UI 状态映射表
2. **控制面协议**（阶段二用，现在定契约）：重试/跳过映射到已有 `loop_back` / `ErrorPolicy.SKIP`，带 `command_id` + 幂等 + 进行中拒绝重复点击
3. **消息块携带 `step_id`**：阶段二"点击子任务跳转对话区锚点"依赖它，是消息模型的数据合同，必须现在锁定
4. 时钟：`started_at/completed_at` 由后端事件携带，面板不算 `setInterval` 耗时

### 3.3 渲染层

Preact + 外置 vanilla store（锁定，不进框架争议）；reducer 按非单调设计（允许 completed→in_progress）；v1 必须包含**最小动态处理**（状态迁移 + 当前步标签 + 计数），diff 可视化才允许推迟【复审修订：Claude M6——v1.0 的 is_dynamic 表述写反了，且会污染止损实验数据】。

## 4. 分阶段交付与度量【复审修订：双路一致否决"展开点击率 <10%"止损线】

**阶段一**（环境进度条）：摘要条（默认收起 + 首次高亮）+ 只读清单（四态）+ 失败 aria-live + 最小动态处理 + a11y 基线。

阶段一要验证的指标：
- 摘要条曝光下（仅对出现过面板的复杂任务会话计）的任务完成率
- 失败后展开率（清单价值浓度最高的场景）
- 展开/收起导致的对话滚离底部率
- 双分母（reach 与 per-exposure 分开）、按计划结果分段、设晋升判据

**阶段二**：失败干预动作（依赖契约已实现）、动态计划 diff 可视化、子任务点击跳转锚点、escalate 强制展开、HITL 确认可选。

**明确不做**：content script 悬浮层、虚拟列表、拖拽分隔条、SW 合批、历史环形缓冲。

## 5. 风险残留

- 后端事件日志 + 回放窗口是本方案的关键路径，工作量在 Python 侧而非扩展侧
- escalate 强制展开是"永不自动展开"原则的唯一例外，需在埋点中单独观测是否惹恼用户
- 动态计划的分项计数（N 完成/M 进行/K 等待）在 loop_back 高频时仍可能让用户困惑，阶段二 diff 可视化是根本解
