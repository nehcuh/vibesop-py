# RIPER Research Update — v2.1（2026-07-15）

> 接收新事实，更新 v2 综合（`2026-07-15-control-panel-synthesis.md`）
> 触发：用户补充三条关键 Research 数据

## 新事实录入

### F1 — GUI 必要性已被研究证实（推翻 Pi 核心质疑）

**v2 Pi 立场**：CLI 工具的用户已选 CLI，给 GUI 是反偏好；"先 CLI 加固，再诚实问 GUI 是否需要"。
**用户研究事实**：vibesop-py 已经发现"对普通用户不友好"，调研显示大部分用户希望有 GUI。

**结论**：Pi 的 Phase 0.5 "诚实评估" 是不必要的卡点。GUI 是已确立的需求，不是待验证假设。直接进入 GUI 设计。

### F2 — Langfuse 必须自部署（推翻"不做 Langfuse"结论）

**v2 三方结论**：Langfuse 自部署 ~1.5GB 内存常驻，砍掉；连云都不接（隐私）。
**用户事实**：产品定位是"企业内部产品"，不接云端是硬约束。

**结论**：自部署是 mandatory。但 Pi/Kimi "1.5GB" 的估算过时：
- **Langfuse v3 self-hosted** 已不需要 ClickHouse（可选），只需 Postgres → 实际内存 ~400-600MB
- 替代候选：**Arize Phoenix**（Python 原生，单 container，~300MB，OTLP-native）
- 路线：vibesop 加 OpenTelemetry instrumentation → backend 可换（Langfuse / Phoenix / Jaeger / 自建）

### F3 — 三个新功能面（v2 brief 未覆盖）

用户具体想要的 GUI 能力：
1. **代码变动可视化** — 看 diff（不只是文本，可能要 AST 级）
2. **变动影响分析** — 改了 X 文件，影响哪些 agent / 哪些 skill / 哪些下游任务
3. **多 Agent 动作可视化** — 实时看不同 agent 在做什么（event feed / timeline）

这三个需求**显著扩大 GUI 范围**。v2 推荐的"按场景分工（CLI + 小 web viewer + Textual TUI）"不够 — diff/impact/agent feed 需要统一的实时 dashboard，Textual TUI 表达力不够。

---

## 对 v2 综合的修订

| v2 结论 | v2.1 修订 | 触发事实 |
|---|---|---|
| Phase 0.5 "诚实评估 GUI 是否需要" | ❌ **删除** — GUI 已被研究确认需要 | F1 |
| 按场景分工（CLI + Textual + 小 web viewer） | ⚠️ **改为统一 Web dashboard** | F3（diff/impact/agent feed 需要统一实时面板） |
| 不做 Langfuse | ❌ **改为 mandatory 自部署** | F2 |
| Phase 0 = CLI 加固 2 周 | ⚠️ **保留**，但与 GUI 设计并行 | F1（GUI 不能等 CLI 完成才做） |
| Textual TUI 作为主形态 | ❌ **降级**为 power-user 选项 | F3 |
| Kimi 的 Web dashboard (FastAPI + React) 推荐 | ✅ **现在变成正确答案** | F3（React 生态有 diff/图形组件） |

---

## 新技术约束

### C1 — 自部署 observability 选型

候选：
- **Langfuse v3 self-hosted**（Postgres only，~500MB，OTLP-compatible）
- **Arize Phoenix**（Python 原生，单 container，~300MB，OTLP-native，更适合 Python 项目）
- **OpenObserve**（Rust，轻量，OTLP）
- 自建：FastAPI + Postgres + 自己写 dashboard（最重，最定制）

推荐路径：**vibesop 全链路加 OpenTelemetry instrumentation**，backend 用 Phoenix（轻 + Python 原生），未来可换 Langfuse。这样 Langfuse 自部署是「可选 backend」不是「核心依赖」。

### C2 — Code diff / impact 技术栈

- **Monaco Editor diff mode**（VS Code 同款，React 集成成熟）
- **Tree-sitter** 做 AST 解析（影响分析的基础）
- **react-flow** 或 **D3** 做依赖图

### C3 — Agent action feed

- WebSocket 推送（FastAPI 原生支持）
- 复用 `vibesop.agent.runtime` 的现有 hook（如果有的话）
- Event sourcing：所有 agent action 落 JSONL + 实时 stream

---

## RIPER 阶段定位

当前在 **Research 完成 → 待进 Innovate**。

**已确认的研究事实**：
- 项目：vibesop-py v8.0.0.dev0 Python SkillOS
- 已有：5 adapter / Squad / lifecycle / `vibe trace` / `vibe orchestrate` / `vibe loop` / `vibe instinct` / `vibe market`（90% 引擎）
- 用户研究：GUI 是已确认需求（"对普通用户不友好"）
- 关键 GUI 能力：代码 diff / 变动影响 / agent action feed
- Langfuse 约束：自部署 mandatory（企业内部）
- 三方一致砍：跨 Agent 异构编排 / 节点连线 workflow / LSP 管理
- 三方一致保留：OS keychain / MCP 模板分发 / vibesop 子包 / 同进程 import

**Research 阶段剩余未决**：
1. 目标用户：自用 / Python 社区开源 / 企业内部商业？（决定 license + 多租户 + 部署）
2. 是否需要再跑 v3 三方评审（scope 已显著变化，Pi 的核心质疑被推翻）？
3. Innovate 阶段：直接列出 2-3 个 GUI 架构候选，还是先做更细的需求拆解？
