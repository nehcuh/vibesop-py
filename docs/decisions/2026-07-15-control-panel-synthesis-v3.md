# VibeSOP Control Panel — 三方评审综合 v3（最终，准备进 RIPER Plan）

> 日期：2026-07-15
> 项目：~/Projects/vibesop-py v8.0.0.dev0
> Brief：`docs/decisions/2026-07-15-control-panel-brief-v3.md`
> 评审：Kimi v3 (`bdauyv33h.output`) + Pi v3 (`but3bjl5f.output`)
> 我（Claude）仲裁

---

## 0. 一句话结论

**v3 综合收敛：FastAPI + React + Vite + Monaco + react-flow + Langfuse（路径 B 先）+ AST 留 P1 SPIKE。但三方在工期上有 3x 差距（Kimi 4-5 周 vs Pi 12-16 周）— 这个差距本身就是 v3 最重要的信号：scope 还没真正定下来。**

---

## 1. 三方一致（v3 强收敛）

### 1.1 架构（v2 → v3 多处自我修正后，最终收敛）

| 决策 | 状态 |
|---|---|
| FastAPI + React + Vite（**不要 Next.js SSR**） | ✅ 三方一致 |
| Monaco Editor 做 text diff | ✅ 三方一致（React 生态锁定） |
| react-flow 做 DAG 可视化 | ✅ 三方一致 |
| **Textual TUI 砍掉**（v2 的"power user 备选"被否） | ✅ 三方一致 |
| SSE 或 WebSocket 做 agent feed | ✅ 一致（Pi 偏 WebSocket，Kimi 偏 SSE — 都可） |
| 纯 Python 后端 + 同进程 import | ✅ 仍然 hold |
| vibesop 子包（`src/vibesop/panel/`） | ✅ 仍然 hold |
| 共享 `~/.vibe/` | ✅ 仍然 hold |

**v2 → v3 自我修正**：
- v2 推 htmx/静态 HTML → v3 改 React（**我错了**，diff/DAG/feed 锁定了 React 生态）
- v2 推 Textual TUI 备选 → v3 砍掉（统一 dashboard 覆盖）
- v2 推按场景分工 → v3 改统一 dashboard（diff/impact/feed 强交互）

### 1.2 AST 影响分析 — 不进 P0

**Pi 的关键洞察（Kimi 同意）**：AST 影响分析不是「diff 的第三层」，而是「mini PyCharm 的调用图模块」。Tree-sitter 只做 syntax parsing，**做不了跨文件调用图**。需要：
- 调用图构建器（`pycg` / `pyan3`，但都不稳）
- import 解析（Python 动态特性致静态分析必有误差）
- 增量更新机制

**MVP 策略**：
- P0：文本 diff（Monaco）+ 文件级范围树（git status 风格）
- P1：**SPIKE 先行 1 周** — 在 vibesop 自己代码库跑 pycg，验证能否捕到 `AgentRouter.route() → Orchestrator.run() → StepRunner.execute()` 这条已知链路。捕不到就别承诺。
- P2（仅当 SPIKE 通过）：跨文件调用图

**复用 vs 自建**：不自建。SPIKE 验证 pycg；不够就退到「lint-style 规则匹配」（改了 `@deprecated` 函数 → 弹警告）。

### 1.3 跨 Agent 编排 / LSP / 节点连线 / GUI Agent 深度管理 — 仍然砍

v2 → v3 hold。

⚠️ Pi 提醒：AST 影响分析功能上接近 LSP，要警惕 scope creep 回到 LSP。**纪律**：影响分析只读，不做编辑辅助 / 不做 completion。

---

## 2. 三方分歧（已仲裁）

### 2.1 Langfuse：mandatory vs optional

| 立场 | 来源 | 论据 |
|---|---|---|
| **mandatory** | 用户原话 + 我 v3 brief | 企业内部产品需自部署 observability |
| **应改 optional，mandatory 是过度反应** | Kimi | 开源 Python 社区用户预期 `pip install` 即用；强制 Docker 拉起 500MB Postgres 是劝退 |
| **既然 mandatory 就用路径 B 用好它** | Pi | 直接用 SDK 拿 prompt/cost/generation nesting |
| **→ 仲裁：mandatory 功能 + 默认禁用 + 一键启用** | Claude（我） | 见下 |

**仲裁**：
- Langfuse 集成代码进入主线（mandatory 功能），但**默认配置 `observability.backend = "none"`**
- 用户主动配置后启用：`vibe langfuse up`（docker compose 包装）+ 配置文件指向
- 未启用时面板显示「Langfuse 未检测到，trace 功能降级到 JSONL viewer」
- 这样：开源用户零负担启用，企业用户一键到位

**集成路径**：采用 Pi 的 **路径 B 先**（Langfuse SDK 装饰 `AgentRouter.route()` 等关键方法）→ P2 升级到路径 C（双轨 OTLP）

### 2.2 工期：Kimi 4-5 周 vs Pi 12-16 周（3x 差距）

**这个差距本身就是 v3 最重要的信号** — scope 还没真正定下来。

| 模块 | Kimi 估 | Pi 估 | 我的估 |
|---|---|---|---|
| FastAPI + WebSocket 后端 | （含在骨架） | 3-4 周 | 3-4 周 |
| React + Vite 前端骨架 | （含） | 2 周 | 2 周 |
| Provider 管理 UI + keychain | 1 周 | 2 周 | 1-2 周 |
| MCP 模板管理 UI | （含） | 1 周 | 1 周 |
| Role CRUD UI | （含） | 1 周 | 1 周 |
| Monaco text diff | 1-2 周 | 2 周 | 2 周 |
| 文件级范围树 | （含） | 1 周 | 1 周 |
| Agent feed（WebSocket + timeline） | 1-2 周 | 2-3 周 | 2 周 |
| Langfuse 集成（路径 B） | 1-2 周 | 1-2 周 | 1-2 周 |
| Langfuse docker compose + `vibe langfuse up` | （含） | 1 周 | 1 周 |
| 集成测试 + 文档 | （含） | 2 周 | 2 周 |
| **MVP 合计** | **4-5 周** | **12-16 周** | **8-12 周** |

**为什么 Kimi 偏乐观**：Kimi 把多个 UI 模块合并算，且没有显式算后端 API 设计（Pi 提到的遗漏）。

**为什么 Pi 偏保守**：Pi 显式列出每个模块 + 集成测试/文档/前端骨架分开算。

**仲裁工期**：**8-12 周 P0（1-2 人），16-20 周完整（含 P1 AST + auth）**。Pi 的拆分更可靠，但部分模块可压缩。

### 2.3 Auth / 多用户

Kimi: P0 完全不做，P1 单 token
Pi: P0 不做，P1 单 token
**三方一致**：P0 绑 localhost 不做 auth；P1 加 `VIBE_PANEL_TOKEN` 单 token；永远不做 RBAC（企业版才考虑）

### 2.4 部署

Kimi: pip 主，docker compose 二线
Pi: 两者都做，pip 主
**三方一致**：pip 是主路径（`pip install vibesop[panel]` → `vibe panel`），docker compose 二线（`vibe langfuse up` 包装）

---

## 3. Pi 提到但 Kimi 未充分讨论的关键点

### 3.1 后端 API 设计哲学未定

v3 brief 完全没讨论 REST + WebSocket API 的设计哲学（RESTful vs RPC、版本管理、schema）。

**这必须在 RIPER Plan 阶段定下来**，因为它直接约束 SPA 状态管理选型。

### 3.2 三视图联动协议

diff 三层 + agent feed 不是独立功能，**真正复杂度来自联动**：
- 用户在 Monaco 改一行 → 文件树变红 → AST 影响图高亮调用者 → agent feed 显示"检测到 X 影响，建议跑测试 Y"

这个交互协议是 dashboard 的核心设计点，v3 brief 未触及。

### 3.3 GIL 风险

agent feed (WebSocket 推) + Monaco diff 计算 + Langfuse SDK 都在同一 FastAPI 进程时，GIL 可能成为瓶颈。

**对策**：FastAPI 用 `uvicorn --workers > 1`；WebSocket 走 Redis pub/sub 分发（如需多 worker）。

但 Pi 自己也指出：v2 说「不常驻 daemon」现在受挑战 — agent feed 必须常驻进程收集 event。这是 v3 的 architectural shift。

---

## 4. v3 最终 MVP（P0）锁定范围

```
模块清单（按依赖排序）：
1. FastAPI + uvicorn + WebSocket 后端骨架（2 周）
2. React + Vite + Tailwind + Zustand 前端骨架（1.5 周）
3. OpenAPI schema + REST 端点设计（1 周，与 1 并行）
4. Agent feed：WebSocket event stream + 前端 timeline（2 周）
5. Per-Agent Provider 管理 UI + keychain（1.5 周）
6. MCP 模板分发 UI（1 周）
7. Role CRUD UI（1 周）
8. Monaco text diff 集成（1.5 周）
9. 文件级范围树（0.5 周）
10. Langfuse SDK 路径 B 集成（1 周）
11. `vibe langfuse up` docker compose 包装（0.5 周）
12. 集成测试 + 文档（2 周）

合计：~10-12 周（1-2 人）
```

**显式不做（P0）**：
- ❌ AST 影响分析（P1 SPIKE 先）
- ❌ RBAC / 多用户
- ❌ Textual TUI
- ❌ SSR / Next.js
- ❌ Skill marketplace 浏览（已有 CLI）
- ❌ 跨 Agent 编排
- ❌ Langfuse 路径 C 双轨 OTLP

---

## 5. v3 → RIPER Innovate / Plan

**Innovate 阶段已隐式完成**：三方一致收敛到 FastAPI + React + Vite + Monaco + react-flow + 路径 B Langfuse。没有可信的 alternative。

**直接进 Plan**，Plan 阶段重点解决：

1. **后端 API 设计**（REST 端点 + WebSocket event schema）
2. **三视图联动协议**（Monaco change event → 文件树更新 → feed push）
3. **数据模型**（panel 与现有 `~/.vibe/` 的关系，是否新增 panel.db）
4. **进程模型**（uvicorn workers / GIL 缓解 / 是否需要 Redis）
5. **前端状态管理**（Zustand stores 划分 / WebSocket 状态）
6. **目录结构**（`src/vibesop/panel/` 内部组织）
7. **测试策略**（FastAPI TestClient + React Testing Library + Playwright E2E？）

---

## 6. v2 → v3 完整 changed / hold 矩阵

### Changed（v3 推翻 v2）

| v2 结论 | v3 状态 |
|---|---|
| Phase 0 后诚实评估 GUI 是否需要 | ❌ 推翻 — 研究已证实 |
| 不引入 React，静态 HTML + htmx | ❌ 推翻 — Monaco/react-flow 锁定 React |
| Langfuse 不做（连云都不接） | ❌ 推翻 — mandatory 功能 + 默认禁用 |
| Textual TUI + 按场景分工 | ❌ 推翻 — 统一 dashboard |
| 工期 2-9 周 | ❌ 上修至 10-12 周（P0） |
| Python GIL 不是问题 | ⚠️ tension — agent feed + Langfuse + WebSocket 同进程有风险 |
| 不常驻 daemon | ⚠️ tension — agent feed 需常驻进程 |

### Still Hold

| v2 结论 | v3 状态 |
|---|---|
| vibesop-py 子包，同进程 import | ✅ |
| 纯 Python 后端 | ✅ |
| 跨 Agent 异构编排砍掉 | ✅ |
| 节点连线 workflow 永远不做 | ✅ |
| LSP 管理砍掉 | ✅（警惕 AST scope creep） |
| GUI Agent 深度管理只读 config | ✅ |
| OS keychain 强制 | ✅ |
| MCP 模板分发 | ✅ |
| Role 显式抽象 | ✅ |
| 共享 `~/.vibe/` | ✅ |

---

## 7. 还需用户回答才能进 RIPER Plan

1. **MVP 工期 10-12 周可接受吗？** 还是要砍到 6-8 周（删 agent feed 或 Langfuse 之一）？
2. **人力**：1 人 / 2 人 / 团队？这决定能否并行
3. **AST 影响分析的承诺程度**：P1 SPIKE 失败就放弃，还是必须做出来（哪怕半成品）？
4. **三视图联动协议**：是否在 Plan 阶段细化？还是 P0 各自独立、P1 才做联动？
5. **是否需要更新 v1 综合文档**（标记为 deprecated）？

---

**附**：本次 v3 评审完整原文：
- Kimi v3：`bdauyv33h.output`（session `e0364f3d-a48c-43df-9d0c-4ad9aa660158`）
- Pi v3：`but3bjl5f.output`（真 pi agent）
