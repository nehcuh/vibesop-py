# 2026-07-27 — Dashboard 重新设计 v2 FINAL（吸收 grok + pi 二次评审）

> **Status**: Phase 4 — Final design（v0 → 5 路对抗 → v1 → grok+pi → v2）
> **Predecessors**:
> - [v0 第一性原理分析](2026-07-27-dashboard-first-principles.md)
> - [v1 5 路对抗综合稿](2026-07-27-dashboard-redesign-v1.md)
> **Author**: Claude

---

## 0. TL;DR

Grok + pi 二次评审共同发现 v1 的**根本盲点**：所有设计都建立在一个**未定义的核心实体**之上。Grok 视角：Work Task 没有写入侧契约；pi 视角：Persona 没有锚定。两者其实是同一问题——**没有定义"为谁、围绕什么实体、解决什么问题"**。

v2 FINAL 的核心修订：

1. **核心实体 = Work Task**（一等公民，写入侧契约：`task_id, root_session, children[], skills[], cost_usd, agent, started_at, status`），所有视图围绕它
2. **Persona = 独立开发者本人**（事后回看 + 改进路由 + 优化成本；**不是团队 lead，不是布道场景**）
3. **Live 视图重定义**: 从"sub-agent 树"（工程师自我陶醉）→ **"决策路径图"**（为什么选 X、跳过 Y、结果如何）
4. **aggregates.json 提前到 P0.5**（不是 P2 可选项；Live + Library 都依赖）
5. **多项目降级**: CLI `--project` 已支持，UI 切换器延后；P0 走 cwd
6. **Account 一级视图砍掉**: 项目/主题/偏好收进右上角齿轮下拉
7. **写操作闭环**: dashboard 起内部 socket（仅前端可达）→ `vibe insight apply --dry-run` 唤起；不直写文件、不强迫复制粘贴
8. **IA 最终**: `Live | Library | 🔔 | ⚙` —— 两一级视图 + Insights 侧栏 + 设置齿轮；cmd+k 是加速器不是导航

---

## 1. Phase 3 — Grok + Pi 二次评审综合

### 1.1 共识（两方一致，必须改）

| # | v1 错误 | 两方共识裁决 |
|---|---------|------------|
| **G+P-1** | aggregates.json 在 P2（v1 §2.8） | **提前到 P0.5/P1 前置依赖**。Live 也需要 cost 数据；不做聚合 = 每次扫全量 = Engineer 已判死刑 |
| **G+P-2** | 多项目在 P0 | **延后**。CLI `--project` 已支持（已验证 `vibe dashboard --help` 有 `-P` 选项），UI 切换器可延后；P0 默认 cwd |
| **G+P-3** | "复制 CLI 命令到终端" = 死 UX | **闭环中间态**: dashboard 内部 socket（仅前端可达）+ Approve 按钮 → `vibe insight apply --dry-run` 预览 + 终端确认。**不直写文件，但不强迫复制粘贴** |
| **G+P-4** | Account 作为一级视图 | **砍掉**。Pi: "把垃圾桶放在客厅正中央"。项目切换 + 主题 + 偏好收进右上角齿轮下拉 |
| **G+P-5** | cmd+k 与一级视图并列 | **降级为加速器**。是交互模式，不是导航目标；不上首页导航条 |

### 1.2 分歧与裁决

| # | Grok | Pi | 我的裁决 |
|---|------|----|---------|
| **D-1** | **致命盲点 = Work Task 未实体化**（写入侧缺 `task_id` 契约） | **致命盲点 = Persona 未定义**（三个画像摇摆） | **两者统一**: Persona = 独立开发者本人 → 这个 Persona 的核心需求 = 看见 Work Task 全貌 → 所以 Work Task 必须实体化。**两个问题是一个问题的两面** |
| **D-2** | IA 替代: Inbox/History/Catalog 或 Session/Patterns/⚙ | IA 替代: Live/Library/🔔/⚙ | **Pi 胜**: Inbox 单列会使 Insights 重新孤岛化（违反 v1 横切层设计）；Live/Library 保留 + Insights 铃铛侧栏 + 设置齿轮。**Insights 保持横切，不升级为一级** |
| **D-3** | "改一件事 = Work Task 实体化 + 写入侧契约" | "改一件事 = sub-agent 树 → 决策路径图" | **两者都做**: Work Task 实体化（数据层）+ 决策路径图（呈现层）。两者互补：实体定义"任务是什么"，呈现定义"任务如何被看见" |

### 1.3 v1 → v2 的 deltas

| 维度 | v1 | v2 |
|------|----|----|
| 核心实体 | Work Task 概念存在但靠 cwd+time 启发式 | **Work Task 一等公民，SpanWriter 写入侧落盘** |
| Persona | 隐含（混合三个画像） | **明确锚定: 独立开发者本人** |
| Live 呈现 | sub-agent 树（实现细节罗列） | **决策路径图**（为什么/跳过/结果叙事） |
| aggregates.json | P2 可选 | **P0.5 前置依赖，与 SpanWriter 同批** |
| 多项目 | P0 阻塞 | **CLI 已支持，UI 切换器 P2** |
| 写操作 | 只生成 CLI 命令字符串 | **内部 socket + Approve 按钮 + dry-run** |
| 一级视图 | Live / Library / Account | **Live / Library**（+ 🔔 侧栏 + ⚙ 下拉） |
| cmd+k | 与一级并列 | **降级为加速器** |

---

## 2. Persona 锚定（v2 新增）

### 2.1 唯一 Persona: 独立开发者本人

**画像**:
- 用 Claude Code / Kimi / Pi / OpenCode 等 AI 编码工具的个人开发者
- 同时使用多个 agent（不是因为团队，是因为不同任务有不同最优解）
- 工作模式: 写代码 → 让 agent 跑任务 → 几小时/几天后想回看
- 心智状态: "我刚才那个任务花了我多少钱？该不该换 skill？"
- **不是团队 lead**: 不做效能管理、不评估下属
- **不是布道者**: 不展示给外人看

### 2.2 这个 Persona 的 JTBD（Jobs-to-be-Done）

| Job | 频率 | 当前 dashboard 满足度 | v2 解决方案 |
|-----|------|---------------------|------------|
| "我刚才那个任务是怎么完成的？" | 高（每天 1-3 次） | ❌（conversations 一堆 JSON，没叙事） | Live → Latest Task 决策路径图 |
| "我装得 skill 有用吗？哪个该优化？" | 中（每周 1-2 次） | 部分（top_skills 但无健康度） | Library → Skills × Agents 矩阵 |
| "我花了多少钱？哪个 skill 烧钱？" | 中（每周 1 次） | ❌（cost_usd 已有但未展示） | Library 矩阵的 cost cell |
| "VibeSOP 自动学到了什么 instinct？" | 低（每月 1-2 次） | ❌（instinct 不可见） | Library → Instinct Timeline（P2） |
| "数据告诉我应该改进什么？" | 低（每月 1 次） | ❌（无 analyzer） | Insights 注解层（依赖 v8.2 P2） |

### 2.3 非 Persona（明确排除）

- ❌ 团队 lead: 不做团队效能、不做多人 dashboard、不做权限
- ❌ 布道者: 不做高密度截图友好布局、不做 demo 模式
- ❌ SRE: 不做实时告警、不做 SLO 监控、不做 incident response

---

## 3. Work Task 实体化（v2 核心数据层）

### 3.1 实体定义（写入侧契约）

```python
@dataclass
class WorkTask:
    task_id: str             # 稳定 ID（uuid 或 hash of root_session+start_ts）
    root_session: str        # 主 conversation 的 session_id
    children: list[str]      # sub-agent conversation 的 session_id 列表
    skills: list[str]        # 涉及的 skill_id 列表（按时间序）
    cost_usd: float          # 总成本（sum of all span.cost_usd）
    tokens_input: int
    tokens_output: int
    agent: str               # 主 agent（claude-code / kimi-cli / pi / opencode / ...）
    started_at: datetime
    duration_ms: int
    status: Literal["completed", "failed", "interrupted"]
    # 决策路径数据
    decision_path: list[dict]   # [{type, skill_id, confidence, chosen, reason}, ...]
    # 关联
    conversation_ids: list[str]
    span_ids: list[str]
```

### 3.2 落盘位置

```
.vibe/observability/tasks.jsonl     # 新文件，append-only
```

每行一个 WorkTask JSON。

### 3.3 写入侧（在 SpanWriter 同批实施）

**触发点**: conversation 写入完成时（主 conversation 闭环）。

**聚合逻辑**:
1. 检测 conversation.metadata.is_subagent == false（主会话）
2. 用 `root_session_id` 拉所有相关 spans（task span + 其下所有 llm/tool spans）
3. 用 `parent_session` 字段拉所有 sub-agent conversations
4. 聚合 cost / tokens / skills / decision_path
5. Append 到 `tasks.jsonl`

**Cross-lock**: 复用 spans.jsonl 的 cross-process lock（参考 `feedback-cross-lock-mutual-exclusion.md` 教训）。

### 3.4 渐进聚合（不要 cwd+time 启发式）

**主键**: `task_id = root_session_id`（如果 conversation 已经有 session_id，直接用）。

**Sub-agent 归属**: 通过 `metadata.parent_session` 显式引用（Path-2 mirror 已支持，不再需要 cwd+time fallback）。

**P0 验收（grok 共识）**: 给定真实 `.vibe` 数据，dashboard 必现最近一条 task 树 + cost，且 URL 可深链 `#live/<task_id>`。

### 3.5 决策路径数据（Pi 洞察：从实现细节 → 决策叙事）

每个 WorkTask 的 `decision_path` 字段记录**决策事件序列**：

```json
[
  {"type": "route", "skill_id": "omx-tdd", "confidence": 0.87, "chosen": true, "reason": "matched keyword 'fix bug' + scenario layer"},
  {"type": "route", "skill_id": "code-review", "confidence": 0.52, "chosen": false, "reason": "lower confidence, deferred"},
  {"type": "tool", "name": "Read(auth.py)", "result": "240 lines, no obvious bug"},
  {"type": "subagent", "agent_type": "Explore", "task": "find related test files"},
  {"type": "edit", "path": "auth.py:42", "op": "null check added"},
  {"type": "instinct_match", "instinct_id": "debug-py-auth", "boost": 0.15}
]
```

**这是 Live 视图的核心叙事数据**——不是"调了什么工具"，而是"做了什么决策、为什么、结果如何"。

---

## 4. aggregates.json（v2 提前到 P0.5）

### 4.1 文件位置

```
.vibe/observability/aggregates.json     # 单文件，原子写
```

### 4.2 Schema

```json
{
  "schema_version": 1,
  "project_id": "default",
  "last_span_id": "abc123",
  "last_updated": "2026-07-27T14:32:18Z",
  "by_skill": {
    "code-review": {
      "count_24h": 8, "count_7d": 26, "count_30d": 89,
      "cost_24h": 0.4, "cost_7d": 1.1, "cost_30d": 4.2,
      "success_rate_7d": 0.72,
      "p95_latency_ms": 1200,
      "trend_sparkline_30d": [3, 4, 2, 5, 6, 4, 5]
    }
  },
  "by_agent": {
    "claude-code": {"count_7d": 45, "cost_7d": 1.9, "success_rate_7d": 0.96}
  },
  "by_day": {
    "2026-07-27": {"count": 12, "cost": 0.3, "by_skill": {...}, "by_agent": {...}}
  }
}
```

### 4.3 写入侧

SpanWriter 在每次 append spans.jsonl 后，**增量更新** aggregates.json：
1. 读 `last_span_id` 水位
2. 处理新 spans，更新对应 `by_skill` / `by_agent` / `by_day`
3. 原子写（tmp + rename，复用 cross-lock）

### 4.4 读取侧

Dashboard 所有聚合 API（`/api/library/*`）直接 `json.load(aggregates.json)`，O(1)。

---

## 5. 最终信息架构（v2 FINAL）

### 5.1 一级结构

```
┌──────────────────────────────────────────────────────────────────────┐
│ ●VibeSOP  Live  Library           🔔3   ⌘K   ◐ theme   ⚙ proj▾      │
└──────────────────────────────────────────────────────────────────────┘
                                       │      │       │         │
                                       │      │       │         └─ 项目切换 + 主题 + 偏好（齿轮下拉）
                                       │      │       └─ 主题切换
                                       │      └─ cmd+k 命令面板（加速器，不在导航条）
                                       └─ Insights 通知铃铛 → 点击展开侧栏（横切注解层）

#live  #library
```

### 5.2 视图清单

| 视图 | 路由 | 一级 tab | 子视图 | 数据源 |
|------|------|---------|--------|--------|
| **Live** | `#live` | ✅ | Latest Task（默认） | `tasks.jsonl` + `conversations/*.json` + `spans.jsonl` |
| **Live → Activity Stream** | `#live/activity` | ✅ | 时间倒序事件流 | `spans.jsonl` + `analytics.jsonl` |
| **Library** | `#library` | ✅ | Skills × Agents 矩阵 | `aggregates.json` |
| **Library → Instinct Timeline** | `#library/instincts` | ✅ | instinct 演化时间线 | `instinct/*.json` |
| **Library → Loops** | `#library/loops` | ✅ | 自主循环任务状态 | `loop-state.json` |
| **Insights 侧栏** | (横切，无独立路由) | ❌ | 全部 insights inbox 列表 | `suggestions.jsonl`（v8.2 P2 输出） |
| **设置下拉** | (横切，无路由) | ❌ | 项目 / 主题 / 偏好 | localStorage |

### 5.3 Live → Latest Task 视图（v2 核心）

**Persona**: 独立开发者本人，事后回看。
**核心问题**: "我刚才那个任务是怎么完成的？AI 做了什么决策、为什么、结果如何？"

**呈现**（Pi 洞察：决策路径图，不是 sub-agent 实现细节）:

```
┌─────────────────────────────────────────────────────────────────────┐
│ ← Yesterday 14:23 · Claude Code · debug-task · 4m 12s · $0.23 →   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─ Your intent ──────────────────────────────────────────────┐    │
│  │ "fix the login bug in auth.py"                             │    │
│  └────────────────────────────────────────────────────────────┘    │
│                              ▼                                       │
│  ┌─ Decision ─────────────────────────────────────────────────┐    │
│  │                                                             │    │
│  │  ✓ Routed to omx-tdd          confidence 0.87              │    │
│  │    why: matched "fix bug" + scenario layer                 │    │
│  │    boosted by instinct debug-py-auth (×3 this week)         │    │
│  │                                                             │    │
│  │  ⊘ Skipped code-review        confidence 0.52              │    │
│  │    why: lower confidence, deferred to post-fix              │    │
│  │                                                             │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                              ▼                                       │
│  ┌─ Execution ────────────────────────────────────────────────┐    │
│  │                                                             │    │
│  │  ● Claude (main)                                            │    │
│  │    ├─ 💭 thinking "need to read auth.py first" 320 tok     │    │
│  │    ├─ 📖 Read(auth.py)           1.2s  240 lines           │    │
│  │    ├─ 🔍 Explore sub-agent ─┐                              │    │
│  │    │   ├─ 🔧 Grep("login") │ 0.8s  12 hits                 │    │
│  │    │   └─ 📖 Read(test)     │ 0.6s  89 lines               │    │
│  │    ├─ ✏️  Edit(auth.py:42)       0.4s  "added null check"  │    │
│  │    └─ 💬 "Fixed: added null check..."                      │    │
│  │                                                             │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                              ▼                                       │
│  ┌─ Outcome ──────────────────────────────────────────────────┐    │
│  │  ✓ Completed in 4m 12s                                      │    │
│  │  💰 $0.23 (vs avg $0.18 for similar tasks, +27%)            │    │
│  │  📊 4.2k input / 1.1k output tokens, 38% cache hit          │    │
│  │  🧠 Instinct reinforced: debug-py-auth (now ×4)             │    │
│  │                                                             │    │
│  │  [Open in CLI]  [Trace Replay]  [Mark as template]          │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ── Earlier Today ───────────────────────────────────────────      │
│  11:08  · Kimi · write-tests · 2m 30s · $0.11                       │
│  09:45  · Claude · refactor · 8m 50s · $0.67                        │
└─────────────────────────────────────────────────────────────────────┘
```

**关键设计原则**（Pi 洞察）:
- **三段叙事**: Your intent → Decision → Execution → Outcome
- **Decision 段是核心**: 不只显示"调用了什么"，而是"为什么选这个、跳过什么"
- **执行细节可折叠**: 默认只显示骨架，点击展开看 prompt/response
- **Outcome 是反思触发点**: cost vs avg、instinct 强化、token 效率
- **操作按钮生成 CLI 命令**（不直接执行）

### 5.4 Library 视图（保留 v1 设计）

Skills × Agents 矩阵（前提: agent_id 填充率 > 70%）。如果 agent_id 不足，退化为 Skills-only 列表（cost / success_rate / trend sparkline 三维度独立）。

---

## 6. 写操作闭环（v2 中间态方案）

### 6.1 双方共识

- **Grok**: 复制 CLI ≠ 闭环；建议 `vibe insight apply --dry-run` 或 `vibesop://` 协议
- **Pi**: 内部 socket（仅前端可达）+ Approve 按钮；不破安全边界但闭环 UX

### 6.2 v2 采纳方案: 内部 socket + dry-run 预览

```
┌──────────────────────────────────────────────────────────────────┐
│ Dashboard Frontend (browser, port 8420)                          │
│   ┌─────────────────────────────────────────────┐                │
│   │ Insight Card                               │                │
│   │  ⚠ code-review overlap with review-related │                │
│   │  [Copy CLI]  [Approve]  [Dismiss]          │                │
│   └──────────────────┬──────────────────────────┘                │
│                      │ Click Approve                              │
│                      ▼                                            │
│   Dashboard Backend (FastAPI, port 8420)                         │
│   ├── POST /api/insights/{id}/preview                            │
│   │     ↓                                                         │
│   │   Spawns: vibe insight apply <id> --dry-run                  │
│   │     ↓                                                         │
│   │   Returns: diff preview                                      │
│   │     ↓                                                         │
│   │   User confirms in UI → POST /api/insights/{id}/apply        │
│   │     ↓                                                         │
│   │   Spawns: vibe insight apply <id> (writes skill file)        │
│   └─────────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────────┘
```

**安全边界**:
1. **绑定 127.0.0.1**: dashboard backend 不接受外部 IP 请求
2. **Origin check**: 所有 POST 必须来自 `Origin: http://127.0.0.1:8420`
3. ** CSRF token**: dashboard 首次加载时签发 token，所有写操作必须携带
4. **写操作走 CLI**: dashboard backend 不直接写文件，而是 `subprocess.Popen(['vibe', 'insight', 'apply', id])` —— 走 CLI 的 hooks/policy 校验链
5. **dry-run 预览必经**: 不允许直接 apply，必须先 preview

### 6.3 为什么不破 v1 的安全裁决

- **v1 错误**: dashboard 直接 open 文件 + 写 skill 内容
- **v2 修正**: dashboard backend 调用 CLI subprocess（已有 hook 校验）
- **保留的边界**: 任何本机进程仍不能直接 `fetch('http://127.0.0.1:8420/api/insights/x/apply')` 写文件（缺 CSRF token + Origin 不符）

### 6.4 简化版（如果不愿做 CSRF）

只用 "Copy CLI" 按钮（v1 方案）+ 一个明显的"打开终端"按钮（链接到 `iterm://` 或 `terminal://` 协议）。用户两个点击即可执行：Copy → Open Terminal → Paste → Enter。比 v1 的"复制切窗口粘贴"少一步。

---

## 7. 修订后的 MVP 路线图（v2 FINAL）

### P0 — 实体契约 + Live Latest Task + 视觉骨架（3-4 天）

**前置数据工作**（与 SpanWriter 同批）:
- `tasks.jsonl` 写入侧实现（WorkTask 实体落盘）
- `aggregates.json` 写入侧实现（增量聚合 + cross-lock）
- `decision_path` 字段从 spans 还原（route spans + tool spans + instinct events）

**Dashboard 范围**:
- Live 视图骨架（Latest Task 子视图）
- 决策路径图渲染（三段叙事：intent / decision / execution / outcome）
- 视觉 tokens 接入（Light theme 默认 + dark toggle）
- Inter 字体 + Lucide 图标 + Linear-anchored 视觉
- 默认走 cwd（多项目延后）

**验收（grok 共识）**:
- 给定真实 `.vibe` 数据，dashboard 必现最近一条 task 树 + cost
- URL 可深链 `#live/<task_id>`
- 30 秒内用户看到完整决策路径（不是空表格）

### P1 — Library 矩阵 + cmd+k + 30s 轮询（3-4 天）

**前置数据检查**（P0 第一天跑）:
- `agent_id` 填充率: 当前数据显示 50% EMPTY（全在 llm spans）—— 需要在 SpanWriter 修复 llm span 继承 task span 的 agent_id
- 修复后填充率 > 70% → 上 Skills × Agents 矩阵
- 修复后仍 < 70% → 退化为 Skills-only 列表

**Dashboard 范围**:
- Library 视图: Skills × Agents 矩阵（或 Skills-only fallback）
- 30s 轮询 + ETag
- cmd+k 命令面板（自实现 ~100 行）
- Library → Instinct Timeline（读 instinct/*.json）
- Library → Loops（读 loop-state.json）

**验收**:
- 用户在矩阵上一眼看出"哪个 skill 烧钱 / 拖后腿"
- cmd+k 能跳到任何视图/实体

### P2 — Insights 注解层 + 多项目 UI + 写操作闭环（依赖 v8.2 P2，1-2 周）

**前置依赖**:
- v8.2 P2 InsightAnalyzer ship
- v8.2 P2 `suggestions.jsonl` 输出

**Dashboard 范围**:
- Insights 横切注解层（inline badge + bell inbox）
- 内部 socket + dry-run 预览 + Approve 按钮
- 多项目 UI 切换器（齿轮下拉）
- Backlinks（Obsidian 模式）: skill 详情页显示"哪些 insight 提到它"

**验收**:
- 用户在 Library 矩阵看到"⚠ overlap?"徽章 → 点击看证据 → Approve → dry-run 预览 → 确认 → CLI 应用
- 多项目切换不需要重启 dashboard

### 明确拒绝清单（与 v1 一致）

- ❌ SSE / WebSocket 实时流
- ❌ Dashboard 直写 skill 文件（必须走 CLI subprocess）
- ❌ Account 作为一级视图（降为齿轮下拉）
- ❌ Now 实时流作为默认视图
- ❌ Insights 作为独立 tab
- ❌ health_score 复合指标 / ROI 公式
- ❌ Tailwind CDN（离线风险）
- ❌ gradient / glow 浮夸视觉
- ❌ 卡片 hover 阴影抬升（反 Linear DNA）
- ❌ cwd+time 启发式当 Work Task 主键

---

## 8. 实施清单（具体任务）

### Phase A — 后端数据层（v8.2 P1.5，与 dashboard 解耦）

- [ ] A1: 在 `src/vibesop/observability/` 加 `task_aggregator.py`（WorkTask 实体 + tasks.jsonl 写入）
- [ ] A2: 在 `src/vibesop/observability/` 加 `aggregator_cache.py`（aggregates.json 增量更新）
- [ ] A3: SpanWriter 接 task_aggregator（conversation 写完时触发 WorkTask 落盘）
- [ ] A4: SpanWriter 接 aggregator_cache（每 span 后增量更新 aggregates.json）
- [ ] A5: 修复 llm span 不继承 task span 的 agent_id 字段（数据完整性 bug）
- [ ] A6: 决策路径数据采集（route spans + instinct events → decision_path 字段）
- [ ] A7: cross-lock 复用（参考 `feedback-cross-lock-mutual-exclusion.md`）

### Phase B — Dashboard P0（实体消费侧）

- [ ] B1: 引入 Vite + vanilla TS 多文件结构（开发用）→ build 成单 HTML
- [ ] B2: 视觉 tokens 接入（CSS variables + Light/Dark theme）
- [ ] B3: Lucide Icons CDN（自托管，不走 Google Fonts）+ Inter 字体（Fontsource）
- [ ] B4: 新 API `/api/live/latest-task` 读 tasks.jsonl
- [ ] B5: 决策路径图渲染组件（三段叙事）
- [ ] B6: Hash router（`#live/<task_id>`）
- [ ] B7: P0 验收测试：真实 .vibe 数据回放

### Phase C — Dashboard P1（Library + cmd+k）

- [ ] C1: agent_id 填充率检查（A5 修复后）
- [ ] C2: 新 API `/api/library/skills-agents` 读 aggregates.json
- [ ] C3: Skills × Agents 矩阵渲染（或 Skills-only fallback）
- [ ] C4: 30s 轮询 + ETag
- [ ] C5: cmd+k 命令面板（自实现）
- [ ] C6: Library → Instinct Timeline
- [ ] C7: Library → Loops

### Phase D — Dashboard P2（Insights + 写闭环 + 多项目）

- [ ] D1: 等 v8.2 P2 InsightAnalyzer ship
- [ ] D2: Insights 横切注解层（inline badge + bell inbox）
- [ ] D3: 内部 socket + dry-run 预览 + Approve 按钮
- [ ] D4: CSRF token + Origin check
- [ ] D5: 多项目 UI 切换器
- [ ] D6: Backlinks

---

## 9. 完整设计历史

| 阶段 | 文档 | 关键产出 |
|------|------|---------|
| Phase 1 — 第一性原理 | [v0 first-principles.md](2026-07-27-dashboard-first-principles.md) | 诊断（L1/L2/L3 三层缺失）+ 6 视图草案 + 哲学映射 |
| Phase 2 — 5 路对抗 | [v1 redesign-v1.md](2026-07-27-dashboard-redesign-v1.md) | 综合裁决（6→3+横切）+ 视觉锚定（Linear）+ 工程架构（aggregates.json） |
| Phase 3 — grok+pi 二次评审 | 本文档 v2 | 核心实体定义（Work Task）+ Persona 锚定 + 决策路径图 + 写操作闭环 |

---

## 10. 设计哲学（一句话总结）

> **VibeSOP Dashboard 不是"看数据的网页"，是"独立开发者本人回看 AI 协作、改进路由、优化成本的镜子"——围绕 Work Task 实体，以决策路径叙事呈现，让用户从执行结果看见下一次更好的决策。**

三个支柱:
1. **Work Task 是原子单元**（不是 conversation / span / route）
2. **决策路径是叙事框架**（不是 sub-agent 实现细节）
3. **Persona 是独立开发者本人**（不是团队 lead，不是布道场景）

---

*Phase 4 complete. 最终设计 v2 ready for implementation.*
