# VibeSOP Control Panel — v3 Brief（最终约束已锁定）

> 日期：2026-07-15
> 项目：~/Projects/vibesop-py v8.0.0.dev0 Python SkillOS
> 背景：v2 评审后用户补充关键 Research 数据，推翻两个 v2 结论 + 加 3 个新功能面
> 评审目的：在已锁定的最终约束下，让 kimi + pi 评审 GUI 架构选型

---

## 1. v2 → v3 关键变化

| 维度 | v2 综合 | v3 锁定 | 来源 |
|---|---|---|---|
| GUI 必要性 | "Phase 0 后诚实评估" | ✅ **已被用户研究证实**（"对普通用户不友好"） | 用户补充 |
| Langfuse | 不做（连云都不接） | ✅ **Langfuse v3 self-hosted mandatory** | 用户补充（企业内部） |
| 产品定位 | 待定 | ✅ **开源 Python 社区**（MIT，单租户为主） | 用户答 |
| Diff 深度 | 未提及 | ✅ **三层全要**：文本 + 文件级 + AST 影响分析 | 用户答 |
| 产品形态 | "按场景分工" CLI + Textual + 小 web | ⚠️ **需重新评估** — diff/impact/feed 需统一 dashboard | 新需求推翻 |

## 2. v3 锁定的最终约束

### 2.1 必须满足（不可谈判）

- ✅ GUI 是刚需（研究证实）
- ✅ Langfuse v3 self-hosted（Postgres only，~500MB）
- ✅ 开源 Python 社区产品（MIT license）
- ✅ 代码 diff 三层：文本（Monaco）+ 文件级（树）+ AST 级（Tree-sitter 影响图）
- ✅ Agent 动作可视化（实时 event feed）
- ✅ Per-Agent Provider 管理（OS keychain）
- ✅ MCP 模板分发（不做运行时统一）
- ✅ Role 显式抽象
- ✅ vibesop-py 子包，同进程 import
- ✅ 纯 Python 后端（FastAPI）+ 同生态前端

### 2.2 已确认砍掉（v2 三方一致，仍 hold）

- ❌ 跨 Agent 异构编排（连文件接力都不建系统）
- ❌ 节点连线 workflow 编辑器（永远不做）
- ❌ LSP 集中管理
- ❌ GUI Agent（Cursor/VS Code/Zed）深度管理（只读 config）
- ❌ 自部署 Langfuse v2 ClickHouse 版本（用 v3）

### 2.3 仍存疑（v3 重点评审）

- SPA 框架：React vs Vue vs Svelte vs Solid？（开源社区偏好 + diff/图形生态）
- 状态管理：Redux Toolkit / Zustand / Jotai？
- 实时 feed 协议：WebSocket / SSE / Long polling？
- AST 影响分析：Python only？还是 Tree-sitter 多语言？
- Langfuse SDK 集成方式：装饰器 / context manager / OpenTelemetry bridge？
- 部署：pip install + `vibe panel` 启动？还是 docker-compose？
- 多用户/RBAC：开源单租户版本是否完全不做？

---

## 3. v2.1 Research Update 已识别的新技术约束

### 3.1 自部署 observability 选型

**用户答：Langfuse v3 self-hosted**

Langfuse v3 self-hosted 关键事实（请评审是否准确）：
- 仅需 Postgres（ClickHouse 可选，self-host 默认不启）
- 内存常驻 ~500MB
- Docker compose 一键起
- Python SDK：`langfuse.openai` 包装器 / `@observe()` 装饰器 / OTLP bridge

集成路径候选：
- A. 全 OpenTelemetry instrumentation，Langfuse 作为 OTLP backend
- B. Langfuse Python SDK 直接装饰 `AgentRouter.route()` / `Orchestrator.run()` 等关键方法
- C. 双轨：OpenTelemetry 通用 + Langfuse SDK 用于 LLM call 特化（prompt/cost tracking）

### 3.2 Code diff / impact 三层技术栈

| 层 | 推荐选型 | 工作量 | 备注 |
|---|---|---|---|
| 文本 diff | **Monaco Editor diff editor**（React 集成成熟） | 小 | VS Code 同款，行/字符高亮 |
| 文件级范围 | 文件树 + 变更徽章（git status 风格） | 小 | 复用 `git diff --name-status` |
| AST 影响图 | **Tree-sitter**（Python first，可扩多语言） + **react-flow** DAG 可视化 | **大** | 调用图 / 引用图；改函数 X → 谁调用 X → 影响范围 |

AST 影响分析的关键设计点：
- 静态分析（vs 动态 trace）— 静态覆盖率高但 false positive
- 增量分析（vs 全量）— 大项目必须增量
- 跨语言（vs Python only）— 用户答"全部都要"可能意味着多语言

### 3.3 Agent 动作可视化

复用现有：`vibesop.agent.runtime.StepContextInjector` / `StepRunner` 已有 step 级 output 收集。
新增：把 step lifecycle（pending → running → success/failed）作为 event 推 WebSocket。

---

## 4. v3 评审重点

### 4.1 GUI 架构（最关键）

v2 Kimi 推 Web dashboard (FastAPI + React) — 现在 GUI 是刚需且要承载 diff/impact/feed，**Web dashboard 几乎肯定是答案**。但请评审：

- SPA 框架：**React**（生态最大，Monaco/react-flow 集成成熟）/ **Vue**（中国开源社区偏好）/ **Svelte/Solid**（轻量）？
- 是否需要 SSR（Next.js）？还是纯 SPA（Vite）足够？
- Textual TUI 还有保留价值吗？（power user 备选 / 砍掉）

### 4.2 AST 影响分析的可行性

这是 v3 最重的技术赌注。请评审：
- Tree-sitter Python 是否足够稳定？
- 是否该 MVP 先做"文件级 + 文本 diff"，AST 留 P2？
- 静态调用图工具：复用（如 `pycg` / `pyan3`）vs 自建？
- 跨语言扩展成本？

### 4.3 Langfuse v3 集成方式

A/B/C 三条路径（见 3.1）哪个最合适？
- 评估：vibesop 是否计划支持多 backend observability（OTLP 抽象）？
- 还是绑定 Langfuse（更深度集成 prompt/cost）？

### 4.4 部署 / 分发

开源 Python 社区产品，最佳分发？
- `pip install vibesop[panel]` → `vibe panel` 起 FastAPI + 自动开浏览器
- `docker compose up`（含 Langfuse + vibesop panel）
- 两者都做？

### 4.5 多用户 / RBAC

开源 Python 社区 = 单机单人为主。但 Langfuse 自部署常意味着团队共享。
- 完全不做 auth（localhost only）？
- 做最简 auth（basic auth / 单 token）？
- 留 hook 给企业版？

### 4.6 v2 → v3 工期重新评估

v2 估 2-9 周。v3 新增 Langfuse + 三层 diff + AST 分析 + agent feed，请重新评估：
- MVP 范围（P0）
- 完整范围工期
- 哪些可以并行做

---

## 5. 期望反馈格式

1. **总体判断**：v3 约束是否合理？哪里有遗漏或冲突？
2. **致命风险**：AST 影响分析 / Langfuse 集成 / SPA 框架 — 哪个最危险？
3. **架构推荐**：FastAPI + React 是否仍是答案？SPA 选型？
4. **AST 分析方案**：MVP 该做到哪一层？复用 vs 自建？
5. **Langfuse 集成路径**：A/B/C 哪个？为什么？
6. **部署方案**：pip / docker / 两者？
7. **多用户/auth**：是否做？做到什么程度？
8. **路线图 v3**：MVP（P0）范围 + 工期 + 并行机会
9. **与 v2 结论的差异**：哪些 changed / still hold？

务必对比 v2 综合文档（`/Users/huchen/Projects/vibesop-py/docs/decisions/2026-07-15-control-panel-synthesis.md`）。
