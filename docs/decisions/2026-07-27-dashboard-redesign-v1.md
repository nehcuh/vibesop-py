# 2026-07-27 — Dashboard 重新设计 v1（吸收 5 路对抗 critique 后的修订稿）

> **Status**: Phase 2 — Revised after 5-way adversarial critique（待 grok+pi 二次评审）
> **Predecessor**: [v0 第一性原理分析](2026-07-27-dashboard-first-principles.md)
> **Author**: Claude

---

## 0. TL;DR

5 个对抗 sub-agent（产品经理 / IA / 视觉 / 怀疑论 / 工程）一致裁决：v0 **诊断对了，药方错了**。本 v1 吸收所有 critique，给出修订设计：

- **IA 收敛**: 6 个平铺视图 → **3 个一级 + 1 个横切 Insights 注解层 + cmd+k**
- **默认视图修正**: 不是 Now 实时流（用户开 dashboard 时根本没东西在发生）→ **Live 视图的"最近一次工作任务"叙事**
- **实时性降级**: SSE → **30s 轮询 + ETag**（YAGNI）
- **Insights 重定位**: 独立 tab → **横切注解层**（嵌入到 Skill/Work 卡片上）
- **视觉锚点**: 5 个参考产品 → **单一锚点 Linear + 默认 Light theme + 设计 tokens**
- **架构边界**: dashboard 是**只读视图层**；聚合缓存（aggregates.json）由 SpanWriter 写入侧维护；**"应用建议"不写文件，只生成 CLI 命令**
- **MVP 收敛**: P0 多项目 + Live（latest work）+ Library 骨架；P1 Library 完整 + cmd+k + 双主题；P2 Insights 注解层（依赖 v8.2 P2）

---

## 1. Phase 2 — 5 路对抗 critique 综合 + 裁决

### 1.1 共识（多位 reviewer 一致同意，必须改）

| # | v0 错误 | 共识裁决 |
|---|---------|---------|
| **C-1** | 6 个平铺视图（Now/Work/Skills/Agents/Insights/Cost） | **PM + IA**: 把"用户问题清单"当成"导航物理结构"。Skills/Agents/Cost 不正交（同一数据点同时属于三者）。→ **3 个一级 + Insights 横切层** |
| **C-2** | Now 作为默认 tab | **PM**: 用户开 dashboard 是事后回看（几小时/几天后），不是盯屏。Now 视图会显示"今天 0 active"空状态。→ **默认 = Live 视图的"最近一次工作任务"叙事** |
| **C-3** | Insights 作为独立视图 | **PM + IA**: Insights 应该是 context-aware 注解（挂在 Skill/Work 卡片上），不是孤岛 feed。且依赖 v8.2 P2 analyzer（未 ship）。→ **横切注解层** |
| **C-4** | SSE 实时流 | **Skeptic + Engineer**: 本地工具每分钟 0-2 个 span，SSE 工程成本（连接/重连/dedup/广播）远大于价值。→ **30s 轮询 + ETag/Last-Modified** |
| **C-5** | 单 HTML 文件 2000 行 | **Engineer**: 实际会膨胀到 2500-3000 行，不可维护。→ **Vite + vanilla TS 多文件开发 → build 成单 HTML** |
| **C-6** | "应用建议"按钮写 skill 文件 | **Engineer**: dashboard 监听 127.0.0.1，任何本机进程/恶意网页都能 POST = XSS→任意文件写→RCE。→ **只生成 `vibe insight apply <id>` CLI 命令**，用户复制执行 |
| **C-7** | 默认保留 dark theme | **Visual**: observability 工具实际 light-first（Datadog/Honeycomb/Stripe/Vercel Billing）。Dark 适合沉浸创作不适合扫读数字。→ **默认 Light，dark 作为 toggle** |
| **C-8** | 列 5 个参考产品 | **Visual**: Linear/Vercel/Raycast/Arc/Honeycomb 视觉 DNA 互不兼容。"按推荐度排序"=没有方向。→ **单一锚点 Linear**，其他只借鉴个别机制 |
| **C-9** | 虚荣指标：hit_rate / health_score / ROI | **PM**: hit_rate 是系统自评；health_score 是黑箱复合；ROI 公式量纲不一致。→ **只展示原始可 debug 的数字**（count / cost / satisfaction 独立显示，不组合） |
| **C-10** | 没考虑多项目支持 | **Engineer**: 当前 `_resolve_project_root()` 走 cwd，启动后锁死。用户切项目 = 重启 dashboard。→ **P0 阻塞项，启动参数 + UI 切换器** |

### 1.2 分歧与裁决

| # | 分歧 | 裁决 |
|---|------|------|
| **D-1** | **Skeptic**: 砍掉整个 dashboard 重建，做 `vibe report weekly` markdown 报告 + 200 行 HTML polish | **拒绝**（4-1 反对）。用户明确要求重新设计；CLI 已有但用户还是说 dashboard 鸡肋——证明 CLI 不能完全替代可视化（sub-agent 树/趋势 sparkline 是 CLI 不擅长的）。但 Skeptic 的"最小化"原则吸收到 MVP 分期 |
| **D-2** | **PM**: 砍掉 Agents 视图（"假需求"）vs **v0**: 保留 Agents 视图 | **裁决 PM 胜**，但**保留 agent 维度作为 Library 矩阵的列**（不是独立视图）。Engineer 也指出 `agent_id` 字段填充率未验证，先不单独做视图 |
| **D-3** | **PM**: MVP 是 Work + Skill Health + cmd+k vs **IA**: 3 一级（Live/Library/Account）+ Insights 横切 | **IA 胜**（结构更正交），但 PM 的"Skill Health 合并 Skills+Cost+skill 维度 Insights"作为 Library 默认视图 |
| **D-4** | **Visual**: 双主题默认 Light vs **Skeptic**: 不重要别折腾 | **Visual 胜**。Light/dark toggle 工程成本极低（一组 CSS variables 切换），价值真实 |

### 1.3 保留的 v0 亮点（5 路 critique 都认同）

1. **§1.3 "数据已捕获但 dashboard 没用上"清单** — Skeptic: "草案唯一硬核证据"。具体：v8.2 P1 已 ship 的 `cost_usd` / pricing table / sub-agent mirror (Path-2) / `vibe trace metrics` CLI 数据
2. **§5.3.2 Conversation 重定义为"工作叙事 + sub-agent 树"** — PM: "草案最锋利的洞察，直接命中真痛点"
3. **§5.1 IA 从数据源分类 → 用户旅程分类** — Engineer: "唯一在工程上正向 ROI 的部分"
4. **§4 哲学定位 "AI 协作的显微镜 + 教练"** — 没人反对（Skeptic 反对"教练"的写操作隐喻，但认可"显微镜"）

---

## 2. v1 修订设计

### 2.1 角色重新定义（窄化）

> **v0**: Dashboard = "AI 协作的显微镜 + 教练"
> **v1**: Dashboard = **"AI 协作的显微镜 + 镜子"**（去掉"教练"的写操作隐喻）

**为什么去掉"教练"**: 5 路 critique 一致认为 dashboard 不应该有"应用建议/写 skill 文件"能力。教练需要"动作"，但 dashboard 的边界是"观察"。建议生成交给 analyzer（v8.2 P2），应用交给 CLI（人在回路）。

**镜子**的隐喻：让用户看见自己的工作模式、agent 行为、成本结构——**所见即所是**，dashboard 不评判、不指挥。

### 2.2 修订后的信息架构

```
顶级导航（3 项 + 1 横切层 + 1 universal entry）
─────────────────────────────────────────────

🏠 Live      (#live, 默认)        — 我和 agent 们刚做了什么
   ├─ Latest Task（默认子视图）   — 最近一次工作任务的完整叙事
   └─ Activity Stream              — 时间倒序事件流（30s 轮询）

📚 Library   (#library)           — 我的 skill / agent 资产
   ├─ Skills × Agents 矩阵（默认） — skill 为行，agent 为列，cost/hit_rate 为 cell
   ├─ Instinct Timeline             — instinct 演化时间线
   └─ Loops                         — 自主循环任务状态

⚙️  Account   (#account)           — 设置 + 多项目
   ├─ Projects                     — 项目切换 + per-project 配置
   └─ Preferences                  — 主题 / 语言 / 数据保留

🔔 Insights (横切注解层)          — 不是 tab，是 inline annotation
   ├─ Skill 卡片上的"⚠️ 重叠"徽章
   ├─ Work 任务上的"💰 比平均贵 3x"气泡
   └─ 顶部铃铛 → 全部 insights inbox 列表

⌘K Command Palette (universal)    — 任何视图按 cmd+k
   ├─ 搜索会话 / skill / agent / insight
   ├─ 跳转任何视图 / 任何实体详情
   └─ 复制 vibe CLI 命令（apply suggestion / trace replay 等）
```

**为什么这样切**:
- 3 个一级视图符合 Miller's Law 7±2 的最佳实践（Nielsen Norman 推荐 ≤5）
- Skills × Agents 矩阵解决了正交性问题（PM + IA 共识）
- Insights 横切层避免"insight 跳到 Work 又跳回来"的孤岛问题
- cmd+k 提供键盘党的 universal entry，但不强制（参考 Linear / Raycast）

### 2.3 默认视图：Live → Latest Task

**核心问题**: 用户打开 dashboard 90% 的真实意图——"我刚才那个任务是怎么完成的？"

**布局**（修订后的 ASCII 草图）:

```
┌─────────────────────────────────────────────────────────────────────┐
│ ●VibeSOP  Live  Library  Account         │ 🔔3 ⌘K  ◐ theme  proj▾ │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ← Yesterday 14:23 · Claude Code · debug-task · 4m 12s · $0.23 →   │
│                                                                     │
│  ┌─ Sub-agent Tree ─────────────────────────────────────────────┐  │
│  │                                                              │  │
│  │  ● You: "fix the login bug in auth.py"                      │  │
│  │    │                                                         │  │
│  │    ▼  routed → skill: omx-tdd (conf 0.87)                   │  │
│  │    │                                                         │  │
│  │    ├─ ● Claude (main)                                        │  │
│  │    │   ├─ 🔧 Read(auth.py)            1.2s  ✓ 240 lines     │  │
│  │    │   ├─ 💭 thinking                  320 tok              │  │
│  │    │   ├─ 🔧 Explore sub-agent ─────┐                        │  │
│  │    │   │   ├─ 🔧 Grep("login")   │  0.8s  ✓ 12 hits         │  │
│  │    │   │   └─ 🔧 Read(test_auth)  │  0.6s  ✓ 89 lines       │  │
│  │    │   ├─ 🔧 Edit(auth.py:42)          0.4s  ✓ edited       │  │
│  │    │   ├─ 💭 thinking                  480 tok              │  │
│  │    │   └─ 💬 "Fixed: added null check..."                   │  │
│  │    │                                                         │  │
│  │    ▼  triggered instinct: debug-py-auth (×3 this week)      │  │
│  │                                                              │  │
│  │  Cost: $0.23 · Tokens: 4.2k in / 1.1k out · Cache hit 38%   │  │
│  │  Skills: omx-tdd · ⚠ code-review (low conf 0.52)            │  │
│  │                                                              │  │
│  │  [Open in CLI]  [Trace Replay]  [Mark as template]          │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ── Earlier Today ───────────────────────────────────────────      │
│                                                                     │
│  11:08  · Kimi · write-tests · 2m 30s · $0.11                       │
│  09:45  · Claude · refactor · 8m 50s · $0.67 ⚠ over budget         │
│  ...                                          [Load full history]   │
└─────────────────────────────────────────────────────────────────────┘
```

**关键设计**:
- 顶部大卡片 = 最近一次任务（自动从 conversations/ + spans.jsonl 聚合，按"工作任务"key）
- sub-agent 树状结构清晰展示层级（Path-2 mirror 数据已有）
- 每个 span 节点可点击展开看 prompt/response（progressive disclosure）
- 底部"Earlier Today"折叠列表，稀疏呈现
- "⚠ code-review (low conf)" 是**Insight 横切注解**的实例（不是独立 tab）
- 所有"操作"按钮都是生成 CLI 命令（不直接执行）

### 2.4 Library 视图：Skills × Agents 矩阵

**核心问题**: 我的 skill 装得有用吗？哪个 agent 配哪个 skill 最划算？

**布局**:

```
┌─────────────────────────────────────────────────────────────────────┐
│  Library > Skills × Agents                                          │
│                                                                     │
│  Filter: [All Packs ▾] [Last 7 days ▾] [Search skill...]           │
│                                                                     │
│  ┌──────────────┬──────────┬──────────┬──────────┬──────────────┐  │
│  │ Skill        │ Claude   │ Kimi     │ Pi       │ Total        │  │
│  ├──────────────┼──────────┼──────────┼──────────┼──────────────┤  │
│  │ omx-tdd      │ 23 / $0.8│ 12 / $0.3│ -        │ 35 / $1.1    │  │
│  │              │ 96% ✓    │ 91% ✓    │          │ ▁▃▅▇▆▅ trend │  │
│  ├──────────────┼──────────┼──────────┼──────────┼──────────────┤  │
│  │ code-review  │ 8 / $0.4 │ 3 / $0.1 │ 15/$0.6  │ 26 / $1.1    │  │
│  │ ⚠ overlap?   │ 72% ✓    │ -        │ 58% ⚠    │ ▂▃▂▅▄▃       │  │
│  ├──────────────┼──────────┼──────────┼──────────┼──────────────┤  │
│  │ superpowers/ │ 45/$1.9  │ -        │ -        │ 45 / $1.9    │  │
│  │  architect   │ 98% ✓    │          │          │ ▅▆▇▆▇▅       │  │
│  └──────────────┴──────────┴──────────┴──────────┴──────────────┘  │
│                                                                     │
│  ⚠ = analyzer suggestion (hover to see evidence)                    │
│  Click any cell → drill into conversation list                      │
└─────────────────────────────────────────────────────────────────────┘
```

**关键设计**:
- 行 = skill，列 = agent（解决 PM 的"维度内聚"要求）
- 每个 cell 三维度独立显示（PM: 不要复合 health score）: count / cost / success_rate
- Trend sparkline（30 天）一眼看出走势
- Insight 作为 inline 徽章（⚠ overlap?），hover 看证据
- Cost 不是独立视图，是矩阵的 metric 维度（IA 的"正交性"修复）

### 2.5 Insights 横切注解层

**v0 错误**: Insights 作为独立 tab，依赖未 ship 的 v8.2 P2 analyzer
**v1 修正**: Insights 是注解，挂在实体上；analyzer 出来前 dashboard 不渲染徽章；analyzer 出来后自动出现

**3 种出现形式**:

1. **Inline badge on Skill cell**（最常见）
   - "⚠ overlap?" 挂在 code-review skill 的 cell 上
   - Hover → tooltip 显示证据 + 建议的 CLI 命令
   - Click → 展开看完整 insight + 关联 conversations

2. **Bubble on Work task**（context-aware）
   - "💰 比平均贵 3x" 挂在超预算的任务上
   - Click → 跳到该任务的 cost breakdown

3. **Top-right bell + inbox**（全局视图）
   - 显示所有未处理 insights 的总数
   - Click → 下拉列表，可按 severity/kind 过滤
   - 每条带 "Copy CLI command" 按钮（不直接执行）

**为什么没有 "Apply" 按钮**（Engineer 安全裁决）:
- Dashboard 监听 127.0.0.1:8420，任何本机进程都能 POST
- 用户访问恶意网页 → 网页 `fetch('http://127.0.0.1:8420/api/insights/x/apply')` → 改写 skill 文件 = RCE
- 修正: dashboard 只生成 `vibe insight apply <id>` 命令字符串，用户复制到终端执行
- 写操作必须经过 VibeSOP CLI（已有 hooks/policy 校验，符合 CLAUDE.md §2.2 可逆性原则）

### 2.6 视觉风格（Linear-anchored）

**单一锚点**: Linear（DNA: 极简 + 阴影分层 + cmd+k + 深紫 accent + 小字号高密度）

**色板（Light theme — 默认）**:

```css
:root {
  /* 背景 — 三层灰阶，不是纯白 */
  --bg-canvas:    #fafaf9;   /* 页面背景，带极淡暖调 */
  --bg-surface:   #ffffff;   /* card 背景 */
  --bg-subtle:    #f5f5f4;   /* hover / 嵌套区 */

  /* 边框 — 两层透明度 */
  --border-default: rgba(0,0,0,0.08);
  --border-strong:  rgba(0,0,0,0.14);

  /* 文字 — 三档 */
  --text-primary:   #18181b;  /* Zink-900 */
  --text-secondary: #52525b;  /* Zink-600 */
  --text-tertiary:  #a1a1aa;  /* Zink-400 */

  /* 品牌 + 强调（替换 GitHub 蓝）*/
  --accent:         #6d28d9;  /* Violet-700 */
  --accent-hover:   #5b21b6;
  --accent-subtle:  rgba(109,40,217,0.08);

  /* 状态色 — 饱和度低于 accent */
  --success: #16a34a;
  --warning: #d97706;
  --danger:  #dc2626;
  --info:    #2563eb;
}

[data-theme="dark"] {
  --bg-canvas:    #09090b;
  --bg-surface:   #18181b;
  --bg-subtle:    #27272a;
  --text-primary:   #fafafa;
  --text-secondary: #a1a1aa;
  --text-tertiary:  #71717a;
  --accent:         #8b5cf6;
  --border-default: rgba(255,255,255,0.08);
}
```

**字体**:

```css
font-family: "Inter", "Inter Variable", -apple-system, "PingFang SC",
             "Microsoft YaHei", system-ui, sans-serif;
font-feature-settings: "cv11" 1, "ss01" 1;
font-variant-numeric: tabular-nums;  /* 数字宽度恒定，避免跳动 */

/* 等宽 */
font-family: "JetBrains Mono", "SF Mono", monospace;
```

**Spacing / Radius / Type scale**: 4px 基线（完整规范见 v0 §6.1，保留）

**图标**: Lucide Icons（MIT, 1500+ 图标, 16px / stroke 1.5，与 Linear 同源）

**动效清单**（精简）:
- 必须有: 列表项渐入（120ms）、数字 count-up（200ms）、状态点呼吸（1.5s）、cmd+k 弹出（80ms）
- 砍掉: 卡片 hover 阴影抬升（反 Linear DNA）、路由树展开动画、粒子飞溅

**字体加载**: 自托管（Fontsource），不走 Google Fonts（避免离线场景失效）

### 2.7 技术架构（Engineer 主导）

**前端栈**:
- Vite + vanilla TS（无 React/Vue）多文件开发
- 目录结构: `dashboard/src/{live,library,account,insights,cmdk}/`
- `vite build` 输出单一 `dist/index.html`（内联 JS/CSS，仍单文件部署）
- 编译期 TS 类型校验后端 schema（避免 `record.get("agent_id")` 动态访问）
- 估算: ~80KB gzipped，零运行时框架成本

**后端 API**（修订）:

```
GET  /api/health                     # 现有，加 Last-Modified header
GET  /api/live/latest-task           # 聚合最新 conversation + sub-agent 树
GET  /api/live/feed?since=<ts>       # 30s 轮询的事件增量
GET  /api/library/skills-agents      # 读 aggregates.json（O(1)）
GET  /api/library/instincts          # instinct 演化时间线
GET  /api/library/loops              # active loops 状态
GET  /api/account/projects           # 已注册项目列表
POST /api/account/project/switch     # 切换 active 项目
GET  /api/insights                   # 读 suggestions.jsonl（v8.2 P2 输出）
POST /api/insights/{id}/dismiss      # 仅标记忽略，不写 skill 文件
                                    # "apply" 不在 dashboard API；用户复制 CLI 命令执行
```

**聚合缓存架构（关键工程改动）**:

```
SpanWriter (in VibeSOP CLI process)
  ├── append spans.jsonl  (raw events, 不变)
  └── update aggregates.json  (新增, 原子写)
            │
            │  by_skill: { skill_id: {count, cost_usd, success_rate, p95_latency, ...} }
            │  by_agent: { agent_id: {...} }
            │  by_day:   { date: {...} }
            │  last_span_id: <水位标记，增量更新>
            │
            ▼
FastAPI dashboard server (read-only)
  └── /api/library/* → O(1) read aggregates.json
```

**为什么这样**:
- 当前每次 `/api/health` 都 O(N) 全扫 spans.jsonl（100K 行 ≈ 800ms-2s）
- 把聚合放到 SpanWriter 写入侧，每条 span 进来时增量更新 aggregates.json
- Dashboard 读取 O(1)，即使 100K spans 也 < 20ms
- aggregates.json 用 cross-lock（参考 `feedback-cross-lock-mutual-exclusion.md` 教训）保证多进程安全
- 这部分**是 v8.2 observability 应该补的 P1.5**，不是 dashboard 的事；但 dashboard 依赖它

**多项目支持（P0）**:
- CLI: `vibe dashboard --project <path>` 显式指定
- 启动时记录到 `~/.vibesop/projects.json` 注册表
- Dashboard UI 顶部右上角加项目切换器
- 当前 `_resolve_project_root()` 走 cwd 的逻辑保留作为 fallback

**前置数据完整性检查**（Engineer 提的 P0）:
- 跑 `jq '.agent_id | length' .vibe/observability/spans.jsonl | sort | uniq -c`
- 如果空值 > 30%，Agents 列维度先不做（Library 退化为纯 Skills 视图）
- 等到 SpanWriter 补 agent_id 字段后再加列

### 2.8 修订后的 MVP 路线图

#### P0（必做，2-3 天）— 多项目 + Live Latest Task + 骨架

**范围**:
- 多项目参数 + UI 切换器（`vibe dashboard --project`）
- Live 视图骨架 + Latest Task 子视图（sub-agent 树渲染）
- 设计 tokens 接入（Light theme 默认 + dark toggle）
- 视觉重做（Linear 风格 + Inter + Lucide）

**验收**: 用户打开 dashboard 30 秒内看到最近一次任务的完整叙事 + sub-agent 树 + cost。

#### P1（核心，3-4 天）— Library 矩阵 + cmd+k + Insights 注解

**范围**:
- Library 视图: Skills × Agents 矩阵（前提: agent_id 填充率 > 70%）
- 若 agent_id 不足: 退化为 Skills-only 矩阵（cost 作为 cell 维度）
- cmd+k 命令面板（自实现 ~100 行）
- Insights 横切注解层（占位 + 数据接口，等 v8.2 P2）
- 30s 轮询 + ETag

**验收**: 用户能在矩阵上一眼看出"哪个 skill 在烧钱/拖后腿"，cmd+k 能跳到任何视图/实体。

#### P2（依赖 v8.2，待 analyzer ship 后）— Insights 真实数据 + aggregates.json

**范围**:
- aggregates.json 在 SpanWriter 侧实现（这是 v8.2 P1.5，不是 dashboard 的事）
- Insights 接 v8.2 P2 `suggestions.jsonl`
- Backlinks（Obsidian 模式）: 在 skill 详情页显示"哪些 insight 提到它"
- Instinct Timeline 子视图（读 `instinct/*.json`）

**验收**: 用户在 Library 矩阵看到"⚠ overlap?"徽章 → 点击看证据 → 复制 CLI 命令 → 终端执行。

#### 明确拒绝清单

- ❌ SSE / WebSocket 实时流
- ❌ Dashboard 直接写 skill 文件 / "Apply suggestion" 按钮
- ❌ Agents 作为独立视图（保留为 Library 列维度）
- ❌ Cost 作为独立视图（保留为矩阵 metric 维度）
- ❌ Now 实时流作为默认视图
- ❌ Insights 作为独立 tab
- ❌ health_score 复合指标 / ROI 公式
- ❌ Tailwind CDN（离线风险）
- ❌ gradient / glow 浮夸视觉
- ❌ 卡片 hover 阴影抬升（反 Linear DNA）

---

## 3. 修订后与 v0 的对照表

| 维度 | v0 草案 | v1 修订 | 改动理由 |
|------|--------|---------|---------|
| IA | 6 视图平铺 | 3 一级 + Insights 横切 + cmd+k | PM + IA 共识: 正交性失败 |
| 默认视图 | Now 实时流 | Live → Latest Task 叙事 | PM: 用户事后回看，不是盯屏 |
| Insights | 独立 tab | inline 注解 + bell inbox | PM + IA: context-aware |
| 实时性 | SSE | 30s 轮询 + ETag | Skeptic + Engineer: YAGNI |
| 视觉参考 | 5 个产品 | 单一锚点 Linear | Visual: DNA 互不兼容 |
| 主题 | 默认 dark | 默认 Light + dark toggle | Visual: observability 实际 light-first |
| 复合指标 | hit_rate / health_score / ROI | 只展示原始可 debug 数字 | PM: 虚荣指标 |
| 写操作 | "Apply suggestion" 按钮 | 只生成 CLI 命令 | Engineer: 安全风险 |
| 前端栈 | 单 HTML 2000 行 | Vite + TS 多文件 → build 单 HTML | Engineer: 可维护性 |
| 后端聚合 | 每次 O(N) 扫 spans.jsonl | aggregates.json O(1) 读 | Engineer: 性能 |
| 多项目 | 未考虑 | P0 阻塞项 | Engineer: cwd 锁死 |
| Agents 视图 | 独立 | 矩阵列维度 | PM: 假需求 + IA: 非正交 |
| Cost 视图 | 独立 + ROI | 矩阵 metric 维度 | PM + IA + Engineer |
| Conversation | "工作叙事" | 同 v0（保留）| 5 路共识: 唯一锋利洞察 |
| "教练"隐喻 | 是 | 改为"镜子" | 5 路共识: 写操作越界 |

---

## 4. 留给 grok + pi 的开放问题

1. **Library 默认视图选 Skills × Agents 矩阵还是 Skills-only 列表？** 取决于 agent_id 填充率（需要先跑数据完整性检查）。
2. **aggregates.json 该放在 .vibe/observability/ 还是单独的 .vibe/aggregates/？** 影响备份/清理策略。
3. **Insights 注解的"证据展开"是 tooltip 还是 side panel？** Tooltip 信息量有限；side panel 占视觉空间。
4. **cmd+k 命令面板是否值得 100 行代码？** Skeptic 反对，PM/IA/Visual 支持。倾向支持但有保留。
5. **Live → Latest Task 的"工作任务"聚合 key**: session_group_id（强）+ cwd+time+skill（中）+ manual pin（弱）三层 fallback 是否够用？
6. **多项目切换是否需要重启 dashboard server？** 还是支持运行时切换（涉及 cwd 重新解析 + 缓存失效）？
7. **v0 的 v8.2 P2 依赖（Insights 真实数据）**: dashboard P2 应该等 v8.2 P2 ship 还是并行做？
8. **从单 HTML 迁移到 Vite + TS 的工程量**: 是否值得？还是 Skeptic 对的（200 行 polish 够了）？

---

*Phase 2 complete. 等待 grok + pi 二次评审。*
