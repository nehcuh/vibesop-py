# VibeSOP 使用案例指南

> **目标读者**：第一次接触 VibeSOP 的开发者，想知道"这玩意儿到底能帮我干什么"
> **不是什么**：本文档不是命令参考（看 [`user/CLI_REFERENCE.md`](user/CLI_REFERENCE.md)），不是哲学阐述（看 [`PHILOSOPHY.md`](PHILOSOPHY.md)）
> **是什么**：12 个具体场景，每个都有"痛点 → 方案 → 命令 → 预期输出"，挑你今天遇到的那条照着做
>
> **English**: [USE_CASES.en.md](USE_CASES.en.md)

---

## VibeSOP 解决什么问题

如果你遇到过下面任何一个，VibeSOP 就是为你的：

- "我知道 superpowers / gstack / omx 这些 skill pack 很强，但**记不住几十个命令**"
- "我在 Claude Code 装了技能，**切到 Cursor 又得重装一遍**"
- "团队 5 个人，每个人都各自摸索同样的工作流，**重复造轮子**"
- "下班后 CI 红了没人管，**第二天上班才发现**昨晚的 build 挂了 8 小时"
- "我想做'分析代码 + 写测试 + 写文档'这种**多步任务**，但每次都漏一步"
- "装了一堆技能不用，**半年后已经忘了哪个有用**"

VibeSOP = **SkillOS**（技能操作系统）+ **Loop Engine**（自主任务引擎）。它管理 AI 辅助开发中技能的**全生命周期**：发现 → 安装 → 路由 → 编排 → 自主执行 → 评估 → 保留/淘汰。

---

## 五大类场景速查

| 类别 | 解决的问题 | 关键命令 | 对应能力层 |
|---|---|---|---|
| **1. 日常开发** | 记不住命令 | `vibe route "<意图>"` | L1 路由注入 |
| **2. 复杂任务** | 多步串行易遗漏 | `vibe route --guided "<复杂任务>"` | L2 编排 |
| **3. 跨平台** | 工具切换重装 | `vibe install <pack>` | 跨平台适配 |
| **4. 自主监控** | 下班没人盯 | `vibe loop create ...` | L0 自主执行 |
| **5. 生命周期** | 技能越装越乱 | `vibe skill stale` / `cleanup` | 生命周期管理 |

---

## 第一类：日常开发（最常用）

### 案例 1：调试一个奇怪的崩溃

**痛点**：你的 Python 服务抛了 `RuntimeError: coroutine was never awaited`，你不知道这是 asyncio 的常见坑。Claude Code 默认会从零开始分析，但你装了 superpowers 包里的 `systematic-debugging` 技能——问题是**你忘了它的存在和命令**。

**VibeSOP 方案**：直接说意图，VibeSOP 路由到正确技能并注入 SKILL.md 内容到 Agent 上下文。

**命令**：
```bash
# 在 Claude Code 里直接说：
debug this RuntimeError: coroutine was never awaited in my FastAPI endpoint

# 或者从 CLI 显式触发路由
vibe route "调试 asyncio coroutine never awaited 错误"
```

**预期输出**（Claude Code hook 自动注入）：
```
🎯 VibeSOP routed: superpowers/systematic-debugging (94% confidence)

NEXT STEP (MANDATORY): read the `skill_file` path from this result
Do NOT guess skills/<id>/SKILL.md.
Do NOT proceed without reading this file.

[ACTIVE SKILL: superpowers/systematic-debugging]
You MUST follow this skill's workflow. Do not skip steps.
... (full SKILL.md content) ...
```

**为什么这有用**：Agent 现在按 systematic-debugging 的 6 阶段流程（reproduce → minimise → hypothesise → instrument → fix → regression-test）走，而不是乱猜。

---

### 案例 2：写测试（TDD）

**痛点**：你想给一个新函数写测试，但**忘了 TDD 的红绿循环**到底怎么开始。

**VibeSOP 方案**：

**命令**：
```bash
# 在 Claude Code 里：
write tests for src/auth/token.py using TDD approach

# 或 CLI：
vibe route "给 src/auth/token.py 写 TDD 测试"
```

**预期**：路由到 `superpowers/test-driven-development`，Agent 会先写失败测试 → 跑 → 实现 → 跑通 → refactor。

---

### 案例 3：代码审查（多维度）

**痛点**：你想让 AI 审查你的 PR，但**不知道有哪些审查角度**（安全？性能？可读性？）。

**VibeSOP 方案**：触发多角色 Squad——implementer + reviewer + red-team。

**命令**：
```bash
vibe route --guided "审查 PR #234 的安全性、性能、可读性三个维度"
```

**预期**：VibeSOP 检测到"三个维度"是多角色查询，自动进入 MULTI_AGENT_SQUAD 模式，分配三个 agent 各审一个维度，最后汇总。

---

## 第二类：复杂任务编排

### 案例 4：架构分析 + 测试生成 + 文档化（端到端）

**痛点**：你接手了一个老项目，需要**同时**做三件事：理解架构、补测试、写文档。手动串行做容易漏，且每步要切不同技能。

**VibeSOP 方案**：一句话触发 3 步编排计划。

**命令**：
```bash
vibe route --guided "分析 src/payment/ 模块架构，补单元测试，更新 README"
```

**预期输出**：
```
🔀 VibeSOP detected multiple intents. Execution plan injected.

Plan:
  Step 1: superpowers/architect → analyze src/payment/ structure
  Step 2: superpowers/test-driven-development → cover gaps
  Step 3: mattpocock/write-docs → update README

Strategy: sequential (each step's output feeds the next)
```

Agent 按 plan 走，每步上下文承接上一步输出。

---

### 案例 5：跨技能工作流（Cross-Cutting Workflow）

**痛点**：每次新功能上线都要走"PR → 代码审查 → 安全审计 → 发布"流程，**手动串接 4 个技能**容易忘。

**VibeSOP 方案**：定义一次，反复调用。

**命令**：
```bash
# 一次性定义（团队 git 共享）
vibe workflows create release-pipeline \
  --steps "create-pr, code-review, security-audit, deploy"

# 之后每次新功能，一句话触发完整流程
vibe route "走 release-pipeline 工作流发布 feature/payment-v2"
```

工作流定义保存在 `.vibe/skills/cross-cutting/release-pipeline/SKILL.md`，git 追踪，团队共享。

---

## 第三类：跨平台技能管理

### 案例 6：多 Agent 工作流（Claude Code + Cursor + Kimi CLI）

**痛点**：你白天用 Claude Code 写代码，晚上回家用 Cursor，跨语言任务用 Kimi CLI（中文工作流）。每个工具的技能目录不同：
- Claude Code: `~/.claude/skills/`
- Cursor: `~/.config/cursor/skills/`
- Kimi CLI: `~/.kimi-code/skills/`

手动维护 3 份副本是噩梦。

**VibeSOP 方案**：中央存储 + 软链接。

**命令**：
```bash
# 一次安装，自动分发到所有平台
vibe install superpowers

# 指定哪些平台接收
vibe config set platforms.install_targets '["claude-code", "cursor", "kimi-cli"]'

# 验证
vibe verify
```

**结果**：
```
~/.config/skills/superpowers/         ← 中央存储（实际文件）
~/.claude/skills/superpowers          ← 软链接
~/.config/cursor/skills/superpowers   ← 软链接
~/.kimi-code/skills/superpowers       ← 软链接
```

任何一个 Agent 都能路由到同一份技能内容。

---

### 案例 7：团队共享技能配置

**痛点**：团队 5 个人，每个人都在自己机器上装 superpowers、gstack、omx。新人入职要花 1 小时配置。

**VibeSOP 方案**：把 `.vibe/` 提交到 git。

**命令**：
```bash
# 团队 lead 配置好后：
git add .vibe/config.toml .vibe/skills/cross-cutting/
git commit -m "feat: team skill baseline"

# 新人 clone 后：
vibe install --auto      # 一键安装团队选定的 packs
vibe verify              # 验证环境
```

新人 5 分钟从零到能用。

---

## 第四类：自主监控（v8.0 Loop System）

### 案例 8：CI 失败自动诊断（最经典）

**痛点**：你下班后 PR 触发了 CI，凌晨 2 点 CI 红了。**第二天早上 9 点上班才发现**，挂了 7 小时。

**VibeSOP 方案**：创建 loop，每 30 分钟检查一次 CI，失败时用 systematic-debugging 技能诊断并 issue 化。

**命令**：
```bash
# 创建 loop
vibe loop create ci-watcher \
  --skill systematic-debugging \
  --schedule "*/30 * * * *" \
  --desc "每 30 分钟检查 CI 状态，失败时自动诊断"

# 配置外部调度器（macOS launchd 例子，见 docs/loop-setup-guide.md）
launchctl load ~/Library/LaunchAgents/com.vibesop.looptick.plist

# 看运行状态
vibe loop show ci-watcher
```

**预期**：CI 红的那一刻起的 30 分钟内，loop 触发，systematic-debugging 自动分析失败日志，结果写入 `~/.vibe/loops/ci-watcher/state.json`。早上班看一眼就知道夜里出了什么问题。

---

### 案例 9：每日 PR 状态汇总

**痛点**：每天早上要打开 GitHub 看 10+ 个 open PR 的状态（CI 红绿、review 进度、conflict 情况），**重复劳动**。

**VibeSOP 方案**：每天 9 点自动跑一次，结果发到 Slack 或写文件。

**命令**：
```bash
vibe loop create daily-pr-digest \
  --query "汇总今天所有 open PR 的状态：CI 结果、review 进度、是否有 conflict" \
  --schedule "0 9 * * *" \
  --desc "每天 9 点 PR 状态汇总"
```

`--query` 模式走完整 4 阶段路由级联（不像 `--skill` 显式指定），适合"我不知道该用哪个技能，让 VibeSOP 选"。

---

### 案例 10：依赖漏洞扫描

**痛点**：dependabot 提了 4 个 PR，你不知道**哪个紧急哪个可以等**。

**VibeSOP 方案**：

**命令**：
```bash
vibe loop create deps-scan \
  --query "扫描项目依赖的安全漏洞，对 dependabot PR 按严重程度排序" \
  --schedule "0 8 * * 1" \
  --desc "每周一早上 8 点依赖安全扫描"
```

每周一早上 8 点触发，输出"PR #234 (high severity, RCE) > PR #235 (medium) > ..."。

---

## 第五类：技能生命周期管理

### 案例 11：清理过期技能

**痛点**：半年前装了一堆技能，现在不知道**哪些还在用、哪些可以删**。

**VibeSOP 方案**：自动追踪使用频率，按 A-F 分级，归档建议默认只读，经你显式确认才执行。

**命令**：
```bash
# 看哪些技能闲置了
vibe skill stale

# 交互式清理
vibe skill cleanup

# 显式应用归档建议（90 天没用 + C/D/F 级 → 归档；默认只读）
vibe skill cleanup --auto
```

**预期输出**：
```
📋 Skill Health Report:
  ✅ superpowers/systematic-debugging  A级  使用 47次/月
  ⚠️  gstack/old-helper                  D级  使用 1次/月  (建议归档)
  ❌ mattpocock/experimental             F级  90天未用    (经 cleanup --auto 归档)
```

---

### 案例 12：从你的工作模式自动生成技能

**痛点**：你发现自己**反复**用同样的工具序列（比如"git diff → 分析变更 → 写 commit message"），但没想过把它固化成技能。

**VibeSOP 方案**：InstinctLearner 自动检测重复模式。

**命令**：
```bash
# 看系统学到的"本能"
vibe instinct status

# 高置信度的本能转成正式技能
vibe instinct evolve --threshold 0.8

# 生成的技能会进入 .vibe/skills/auto/，可编辑后发布
```

**预期**：系统发现你过去 30 天里 23 次跑了同样的 4 步序列，自动生成 `auto/commit-with-context` 技能，下次你说"提交代码"就直接路由过去。

---

## 不适合的场景（明确边界）

VibeSOP **不是**下列工具，强行用反而低效：

| ❌ 不适合 | 原因 | 应该用 |
|---|---|---|
| 大规模代码生成 | 这是 L3 层的职责 | 直接让 Claude Code / Cursor |
| 实时聊天协作 | 不是 IM 工具 | Slack / Discord |
| 长时间运行任务（>1 小时） | Loop v1 不支持 | CI/CD pipeline |
| 需要图形界面 | 纯 CLI | IDE 插件 |
| 修改 skill 内容 | VibeSOP 不生产技能内容 | 找 skill pack 作者 |
| 数据库迁移等高风险操作 | 没有 Guard 系统（v8.1 才有） | 手动 + 人审 |

---

## 推荐上手路径

### 第 1 天：单平台试水
```bash
vibe install superpowers           # 装 1 个 pack
vibe route "debug this error"      # 试 L1 路由
vibe route --explain               # 看路由决策树
```

### 第 1 周：跨平台铺开
```bash
vibe install gstack omx            # 装更多 pack
vibe config set platforms.install_targets '["claude-code", "cursor"]'
vibe verify                        # 验证多平台
```

### 第 1 个月：编排 + 团队共享
```bash
vibe route --guided "分析+测试+文档"   # L2 编排
vibe workflows create release-pipeline # 跨技能工作流
git add .vibe/ && git commit           # 团队共享
```

### 第 2 个月起：自主化
```bash
vibe loop create ci-watcher ...        # L0 自主监控
vibe skill stale                       # 生命周期管理
vibe instinct status                   # 模式学习
```

---

## 下一步

- **想装技能**：[`SKILLS_GUIDE.md`](SKILLS_GUIDE.md) 详解 18 个内置技能 + 社区技能包
- **想跨平台**：[`QUICKSTART_USERS.md`](QUICKSTART_USERS.md) 安装指南
- **想做 loop**：[`loop-setup-guide.md`](loop-setup-guide.md) 24 小时部署
- **想理解原理**：[`PHILOSOPHY.md`](PHILOSOPHY.md) 设计哲学
- **想看路线图**：[`ROADMAP.md`](ROADMAP.md) v4.x → v8.0

遇到具体场景不在本文档里？提个 issue，加进下一版。
