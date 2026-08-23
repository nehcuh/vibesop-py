# VibeSOP SkillOS — 项目目标

> 最后更新: 2026-06-19

---

## 项目定位

VibeSOP 是一个 **SkillOS（技能操作系统）**，管理 AI 辅助开发中技能的全生命周期：发现 → 安装 → 路由 → 编排 → 评估 → 保留/淘汰。简单任务由 VibeSOP 端到端完成（路由→注入→引导执行），复杂任务由 AI Agent（Claude Code, Cursor, OpenCode, Kimi Code CLI）接手。

---

## 目标列表

### A. 安装与发现

#### 1. 推荐社区流行技能包一键安装
- `vibe install --list` 展示可信技能包
- `vibe install --auto` 一键安装推荐包
- `vibe skills recommended` 基于技术栈和协同过滤推荐
- `vibe skills featured` 浏览精选技能注册表
- `vibe sync-registry` 远程同步精选注册表
- 已内置 superpowers, gstack, omx, mattpocock 四个可信包

#### 2. 智能识别技能包安装配置
- `SkillAutoConfigurator` 自动分析 SKILL.md 生成路由配置
- `RepoAnalyzer` 克隆仓库 → 解析 SKILL.md → 提取安装说明
- `vibe skill add` 6 阶段智能安装流程（检测 → 安全审计 → scope 选择 → 安装 → 自动配置 → 验证同步）
- 支持 `.claude-plugin/plugin.json` 注册表格式
- LLM 增强配置：规则引擎 + Agent 环境回退

#### 3. `vibe install` 从 URL 智能安装
- `vibe install <git-url>` 支持任意 Git URL
- `vibe skills install --url <url>` 下载远程包
- `vibe skill add <url>` 从 URL 克隆分析安装
- Market crawler 搜索 GitHub `topic:vibesop-skill`

### B. 技能生命周期

#### 4. 项目级别 vs 全局技能
- Scope 系统: `project` vs `global`
- `vibe skill add --global` 安装时选择 scope
- Scope-aware routing: 项目技能在项目外不可见
- `vibe skills scope <id> --set project/global`

#### 5. 全局技能排序和整理
- A-F 质量分级（`RoutingEvaluator`）
- `RetentionPolicy` 按时效/使用频率排序
- `FeedbackLoop` 收集满意度数据
- `vibe skills featured` 按技术栈和评分浏览精选技能

#### 6. 清理不使用/过时技能
- `vibe skill cleanup` 交互式/自动清理
- `vibe skill stale` 健康分析报告
- 90 天自动归档（D/F 级技能）
- `vibe skill end-check` 会话结束检查
- `vibe trace clean` 清理旧路由追踪

### C. 路由与编排

#### 7. 智能判断最适合技能 + 用户选择优先级
- 10 层路由 Pipeline（EXPLICIT → SCENARIO → AI_TRIAGE → KEYWORD → TFIDF → EMBEDDING → LEVENSHTEIN → CUSTOM → NO_MATCH → FALLBACK_LLM）
- 4 级降级策略（AUTO / SUGGEST / DEGRADE / FALLBACK）
- `PreferenceBooster` 学习用户偏好
- `ConflictResolver` + 5 种冲突解决策略 (ExplicitOverride, ConfidenceGap, NamespacePriority, Recency, Fallback)
- `--trace` 路由追踪模式（受 SkillTree 启发）
- `vibe trace list/show` 查看历史路由决策

#### 8. 多意图编排（Orchestration）
- `MultiIntentDetector` 两阶段检测（启发式 + LLM 确认）
- `TaskDecomposer` 分解复杂 query
- `PlanBuilder` + `PlanTracker` 执行计划管理
- Sequential / Parallel / Mixed 三种执行模式
- `--agents` 指定 Agent 池进行 Agent-Skill 绑定编排
- `AgentRegistry` 根据技能类型自动分配最佳 Agent
- `vibe workflows` 跨技能工作流定义和管理（受 SkillTree 启发）

#### 9. 跨技能工作流（Cross-Cutting Workflows）
- `CrossCuttingDiscovery` 发现 `.vibe/skills/cross-cutting/` 下的工作流定义
- `vibe workflows list` 列出所有跨技能工作流
- `vibe workflows show <id>` 查看工作流详情（依赖技能、步骤）
- `vibe workflows create` 交互式创建跨技能工作流
- `vibe workflows match <skill_ids>` 查找覆盖指定技能的工作流
- 工作流 SKILL.md 格式：`type: cross-cutting` + `depends_on` + `steps`
- 受 SkillTree 的 `cross-cutting/SKILL.md` 模式启发

#### 10. 路由透明与调试
- `--explain` / `--verbose` 展示完整路由决策树
- `--trace` 每层决策记录保存到 `.vibe/traces/`
- `vibe trace show <id>` 查看每层匹配/拒绝的候选技能及原因
- Rejected candidates 展示被拒绝技能及理由

### D. 学习与进化

#### 10. 多轮对话自动生成技能
- `InstinctLearner`：从多轮工具调用序列中检测重复模式
- `SkillSuggestionCollector`：候选持久化 + 阈值触发（≥5 次，≥80% 成功率）
- `vibe instinct eval` → `vibe skills suggestions` → `vibe skills create --from-suggestion`
- `vibe instinct evolve`：高置信度 instinct（≥0.8，≥10 次使用）→ 正式技能

#### 11. 失败处理与偏航记录
- `deviation.py`：记录 Agent 跳过路由推荐的偏航，6 种标准原因码
- `analyze_deviations()`：偏航模式分析
- `FeedbackLoop.analyze_all()`：低质量技能自动降级/归档
- `RetentionPolicy`：F 级 30 天 + 使用 < 3 次 → 建议移除；D 级 60 天 → 警告

#### 12. `/instinct` 对话洞察
- `vibe instinct` 全命令行系统
- `learn`：手动记录成功模式（pattern + action + context + tags）
- `eval`：审查自动检测序列模式 → 转为技能建议
- `status [--tag]`：查看按置信度分级的已学习 instinct
- `export/import`：JSON 格式团队共享
- `evolve`：高置信度 instinct → 正式 SKILL.md 技能

### E. 跨平台与 Agent 集成

#### 13. 多平台中央存储 + 软链接
- 中央存储：`~/.config/skills/`（实际文件）
- 平台软链接：`~/.claude/skills/`, `~/.config/opencode/skills/`, `~/.kimi-code/skills/`, `~/.config/cursor/skills/`
- `vibe verify` 验证各平台配置完整性（hooks, AGENTS.md, 脚本权限）
- `SkillInjector` 将技能内容注入 Agent 上下文
- Windows 不支持软链接时自动 fallback 复制

#### 14. 对话结束动作
- `vibe skill end-check`：会话结束 retention + 技能建议检查
- `FeedbackLoop.end_of_session_check()`：自动分析过期技能 + 检测新模式
- 可通过 session-end hook（POST_STOP）自动触发

#### 15. Agent 能力模型 + Agent-Skill 绑定
- 4 个 Agent Profile：
  - **Claude Code** — 复杂推理、架构设计、调试、多步骤分析
  - **OpenCode** — 代码编辑、重构、多文件变更
  - **Kimi Code CLI** — 中文工作流、文档、双语任务
  - **Cursor** — 交互式编辑、IDE 集成工作流
- `AgentRegistry.assign_agents_to_steps()`：编排时自动分配最佳 Agent
- `--agents` 指定可用 Agent 池

#### 16. 社区分享与发现
- `vibe skill share <id>`：通过 GitHub Issues 分享技能到社区
- `vibe skill discover [query]`：搜索社区分享的技能（命名冲突已识：现 `vibe skill discover` 为本地候选队列；本愿景落地时应命名为 `vibe market search` 之类）
- 按 👍 反应排序

### F. 自主执行与在线值守（v8.0+）

#### 17. 定时循环任务（vibe loop）
- `vibe loop create` — 创建定时循环任务
- 支持 cron 表达式（`*/30 * * * *`, `0 22 * * *` 等）
- 支持指定目标技能（`--skill`）或查询语句（`--query`）
- 持久化到 `~/.vibe/loops/{name}/`（`spec.json` + `state.json`）
- `vibe loop list` / `show` / `delete` / `pause` / `resume`
- `vibe loop logs` — 查看执行历史

#### 18. 两种执行模式
- **Hook API（被动）** — 作为 Claude Code 等 Agent 的 skill router
- **Runtime API（主动）** — 独立运行，自带 LLM，定时执行
- 共享同一套核心（路由、技能管理、安全、生命周期）

#### 19. Loop Guard 安全系统
- `max_failures`: 连续失败上限 → DEAD 状态
- **Dead man's switch**: loop 停止 → 告警
- **人工审批门**: 关键操作（merge-to-main 等）等待人类确认
- **通知集成**: Slack / Email / GitHub Issue（v8.1）

#### 20. Loop 适用场景分类
- **监控类**: CI 状态、依赖漏洞、测试覆盖率、过期分支
- **收集类**: PR 汇总、issue 分类、反馈聚类
- **分析类**: 代码质量趋势、性能基准、安全审计
- **报告类**: 每日日报、周报、项目健康度

**不适用场景**（需人类 + Claude Code）:
- 代码实现、架构设计、代码审查、复杂重构、安全渗透

---

## 启发来源

- **oh-my-codex** — Instinct 学习系统、多平台中央存储、Agent Runtime 层
- **SkillTree** — 路由追踪模式、跨技能工作流定义、强制深度限制
- **mattpocock/skills** — 高质量技能设计范式、`.claude-plugin/plugin.json` 注册表格式

---

## 相关文档

- [README.md](README.md) — 项目概述与快速开始
- [docs/ROADMAP.md](docs/ROADMAP.md) — 版本路线图
- [docs/PHILOSOPHY.md](docs/PHILOSOPHY.md) — 设计哲学
- [docs/QUICKSTART_SKILL_INSTALLATION.md](docs/QUICKSTART_SKILL_INSTALLATION.md) — 技能安装指南
