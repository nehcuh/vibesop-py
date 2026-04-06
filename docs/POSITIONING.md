# VibeSOP-Py 项目定位

> **Version**: 4.0.0
> **Date**: 2026-04-06
> **Status**: Confirmed

---

## 一、一句话定义

**VibeSOP 是 AI 辅助开发的智能路由引擎 — 理解用户意图，发现最佳工作流，管理技能生态，让 AI 工具从"每次从零开始"变成"越用越聪明"。**

---

## 二、我们是什么

### 核心能力（3 个）

1. **智能路由** — 用户说"帮我调试"，VibeSOP 知道该用 systematic-debugging 而不是 brainstorming
2. **技能管理** — 发现、安装、审计、监控所有可用技能（builtin + 外部包 + 自定义）
3. **上下文感知** — 通过记忆、偏好学习、会话分析，让路由决策越来越准

### 我们不是什么

- **不是** 技能执行引擎 — 执行是 AI Agent（Claude Code / OpenCode）的事
- **不是** 技能创造平台 — 技能以 SKILL.md 定义，VibeSOP 负责发现和路由
- **不是** AI 工具本身 — VibeSOP 运行在 AI 工具之上，是工作流层
- **不是** 配置模板集 — VibeSOP 是可执行的框架，有路由、记忆、学习

---

## 三、核心哲学

### 路由引擎的四个原则

1. **发现优于执行** — 知道有什么可用，比自己能执行更重要
2. **匹配优于猜测** — 多层匹配（keyword → TF-IDF → embedding → fuzzy）让路由更准
3. **记忆优于智能** — 记住用户偏好和历史，比每次都重新推理更有价值
4. **开放优于封闭** — 任何符合 SKILL.md 规范的技能都可以接入

### 技能包统一模型

所有外部技能包（superpowers、gstack、omx、自定义）使用**完全一致**的处理方式：

```
vibe install superpowers   → clone + 分析 + 安装
vibe install gstack        → clone + 分析 + 安装
vibe install omx           → clone + 分析 + 安装
vibe install <url>         → clone + 分析 + 安装
```

**不再有特殊对待。** omx 不再手动复制 SKILL.md 到代码库，不再手写 Python 实现。
它和 superpowers、gstack 一样，是一个可安装的外部技能包。

### 与参考项目的关系

```
┌─────────────────────────────────────────────────────┐
│                    用户意图                           │
│              "帮我调试这个 bug"                       │
└──────────────────────┬──────────────────────────────┘
                       │
              ┌────────▼────────┐
              │   VibeSOP       │  ← 我们在这里
              │  智能路由引擎    │
              │                 │
              │  • 理解意图      │
              │  • 匹配技能      │
              │  • 冲突解决      │
              │  • 偏好学习      │
              │  • 健康检查      │
              └────────┬────────┘
                       │ 推荐: systematic-debugging
          ┌────────────┼────────────┐
          │            │            │
   ┌──────▼──────┐ ┌──▼───────┐ ┌─▼──────────┐
   │ Claude Code │ │ OpenCode │ │ 其他平台    │
   │ (执行技能)   │ │ (执行技能)│ │ (执行技能)  │
   └──────┬──────┘ └──┬───────┘ └─┬──────────┘
          │            │           │
   ┌──────▼────────────▼───────────▼──────┐
   │          技能生态（SKILL.md）          │
   │                                       │
   │  builtin  │ superpowers │ gstack │ omx│
   │  (12)     │    (7)      │ (19)   │ (7)│
   └───────────────────────────────────────┘
```

### 差异化对比

| 维度 | VibeSOP | superpowers | gstack | oh-my-codex |
|---|---|---|---|---|
| **定位** | 智能路由引擎 | 技能包 | 技能包 + 浏览器工具 | Codex 工作流层 |
| **平台** | 跨平台 | Claude Code | Claude Code | Codex CLI |
| **核心能力** | 路由 + 管理 | 7 个通用技能 | 19 个工程技能 | 7 种方法论 |
| **执行** | 不执行，路由到 Agent | SKILL.md 指令 | SKILL.md + 浏览器 | TypeScript/Rust 运行时 |
| **学习** | 偏好学习 + 记忆 | 无 | 无 | 项目记忆 |
| **生态** | 开放，任何 SKILL.md | 封闭 | 封闭 | 封闭 |

**VibeSOP 的护城河：**
- 跨平台（不绑定任何 AI 工具）
- 开放生态（任何技能都可以接入）
- 智能路由（8 层管道 + 偏好学习 + 冲突解决）
- 上下文感知（记忆 + 会话分析 + 模式发现）

---

## 四、项目边界

### VibeSOP 负责

- ✅ 用户意图理解（多层匹配）
- ✅ 技能发现与注册（builtin + 外部）
- ✅ 技能路由推荐（冲突解决 + 偏好学习）
- ✅ 技能安装（已知包 + 任意 URL + 单文件）
- ✅ 技能安全审计（外部技能加载前扫描）
- ✅ 技能健康检查（版本、依赖、可用性）
- ✅ 配置生成（渲染到目标平台）
- ✅ 记忆管理（会话状态、项目知识）
- ✅ 偏好学习（instinct 提取、路由权重调整）
- ✅ 会话分析（模式发现、技能建议）

### VibeSOP 不负责

- ❌ 技能的实际执行（这是 AI Agent 的事）
- ❌ 替代 Agent 的工具调用（Read/Grep/Bash/Edit）
- ❌ 工作流 pipeline 执行（SKILL.md 已定义步骤）
- ❌ A/B 测试和用户分流（不是路由引擎的职责）
- ❌ 浏览器自动化（这是 gstack/browse 的事）
- ❌ 代码生成和修改（这是 AI Agent 的事）

---

## 五、技能全生命周期

### 1. 安装

```bash
# === 已知技能包 ===
vibe install superpowers          # 预定义的 URL 和安装规则
vibe install gstack
vibe install omx

# === 任意 Git 仓库 ===
vibe install https://github.com/xxx/my-skills
    │
    ▼ 智能分析流程:
    1. Clone 到临时目录
    2. 递归扫描所有 SKILL.md 文件
    3. 读取 README.md 提取安装说明
    4. 检查 setup 脚本（package.json, Makefile 等）
    5. 生成安装计划并展示
    6. 用户确认后执行

# === 单个技能文件 ===
vibe install https://example.com/my-skill.md
    │
    ▼
    1. 下载 SKILL.md
    2. 安全审计
    3. 安装到 ~/.vibe/skills/my-skill/

# === 本地技能 ===
vibe install ./path/to/my-skill   # 从本地目录安装
vibe skill create my-audit        # 创建新项目技能
```

### 智能安装器工作流程

```
vibe install https://github.com/obra/superpowers
    │
    ▼
┌─────────────────────────────────────────────────┐
│ Step 1: Clone                                   │
│ → 临时目录: /tmp/vibe-install-xxx/              │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│ Step 2: 分析项目结构                             │
│ → 递归扫描 SKILL.md: 找到 7 个                   │
│ → 读取 README.md: 提取安装说明                   │
│ → 检查 setup 脚本: 无额外步骤                    │
│ → 识别技能目录: skills/tdd/, skills/brainstorm/  │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│ Step 3: 生成安装计划                             │
│                                                 │
│ 📦 发现技能包: superpowers                       │
│   来源: https://github.com/obra/superpowers      │
│   发现技能: 7 个                                 │
│     - tdd         (skills/tdd/SKILL.md)          │
│     - brainstorm  (skills/brainstorm/SKILL.md)   │
│     - refactor    (skills/refactor/SKILL.md)     │
│     - debug       (skills/debug/SKILL.md)        │
│     - architect   (skills/architect/SKILL.md)    │
│     - review      (skills/review/SKILL.md)       │
│     - optimize    (skills/optimize/SKILL.md)     │
│                                                 │
│   README 说明: 直接复制 skills/ 目录到目标位置    │
│   额外步骤: 无                                   │
│   安装目标: ~/.config/skills/superpowers/        │
│                                                 │
│   是否继续? [Y/n]                                │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│ Step 4: 执行安装                                 │
│ → 复制/链接技能文件到目标位置                     │
│ → 创建平台 symlink（claude-code, opencode）       │
│ → 安全审计每个技能                               │
│ → 更新 registry                                  │
│ → 验证安装                                       │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│ Step 5: 安装完成                                 │
│ ✅ superpowers 安装成功                          │
│   7 个技能已就绪                                 │
│   运行 vibe skills list --namespace superpowers  │
│   查看已安装技能                                 │
└─────────────────────────────────────────────────┘
```

### 2. 发现

技能发现是**分层**的，优先级从高到低：

```
层级  来源                        路径                           优先级
────  ──────────────────────────  ─────────────────────────────  ──────
L0    项目自定义技能              .vibe/skills/                  最高
L1    项目共享技能                skills/
L2    Claude Code 原生技能        ~/.claude/skills/
L3    外部技能包                  ~/.config/skills/{pack}/
L4    VibeSOP 全局技能            ~/.vibe/skills/
L5    VibeSOP 内置技能            core/skills/ (代码库内)
L6    注册表元数据                core/registry.yaml
```

### 3. 管理

```bash
# 查看所有可用技能
vibe skills list

# 按命名空间查看
vibe skills list --namespace gstack

# 查看技能详情
vibe skills show systematic-debugging

# 查看技能统计
vibe skills stats
# 输出: total: 45, builtin: 12, superpowers: 7, gstack: 19, omx: 7

# 检查技能健康
vibe skills health
# 输出: superpowers ✅ v1.2.0, gstack ✅ v2.0.1, omx ✅ v0.3.0

# 搜索技能
vibe skills search "debug"

# 卸载技能包
vibe uninstall superpowers

# 更新技能包
vibe update superpowers
```

### 4. 路由

```bash
# 用户说："帮我调试这个 bug"
vibe route "帮我调试这个 bug"
# → 输出: Matched skill: systematic-debugging (95% confidence)
```

### 5. 运行时完整链路

```
用户在 Claude Code 中说: "帮我调试这个 bug"
    │
    ▼
Claude Code 读取 ~/.claude/CLAUDE.md
    │  (由 vibe install claude-code 生成)
    │  里面写了: "ALWAYS call vibe route before any task"
    │
    ▼
Claude Code 执行: vibe route "帮我调试这个 bug"
    │
    ▼
UnifiedRouter 路由引擎:
    1. 预过滤: 排除不相关的命名空间
    2. Keyword: 匹配 "debug"/"调试" → systematic-debugging
    3. 偏好学习: 用户过去 3 次都用 systematic-debugging → 加权
    4. 冲突解决: 有 gstack/investigate 也匹配 → 规则说 builtin 优先
    5. 输出: systematic-debugging (95%)
    │
    ▼
Claude Code 读取: skills/systematic-debugging/SKILL.md
    │  (这个文件由 vibe install 生成/链接)
    │
    ▼
Claude Code 按照 SKILL.md 的指令执行
    - 用 Read 工具读代码
    - 用 Grep 搜索错误模式
    - 用 Bash 跑测试
    - ...
```

---

## 六、技术架构

```
┌──────────────────────────────────────────────────┐
│                    CLI Layer                      │
│  vibe route / vibe skills / vibe install / ...   │
├──────────────────────────────────────────────────┤
│                 Routing Engine                    │
│  ┌─────────┐ ┌──────────┐ ┌───────────────────┐  │
│  │Matching │ │Conflict  │ │Preference Learning│  │
│  │Pipeline │ │Resolution│ │(instinct/memory)  │  │
│  └─────────┘ └──────────┘ └───────────────────┘  │
├──────────────────────────────────────────────────┤
│               Skill Management                    │
│  ┌──────────┐ ┌───────────┐ ┌────────────────┐   │
│  │Discovery │ │Lifecycle  │ │Health Check    │   │
│  │& Loading │ │Management │ │& Versioning    │   │
│  └──────────┘ └───────────┘ └────────────────┘   │
├──────────────────────────────────────────────────┤
│              Integration Layer                    │
│  ┌──────────┐ ┌───────────┐ ┌────────────────┐   │
│  │Installer │ │Detector   │ │Security Audit  │   │
│  │(智能分析) │ │& Verifier │ │& Path Safety   │   │
│  └──────────┘ └───────────┘ └────────────────┘   │
├──────────────────────────────────────────────────┤
│              Adapter Layer                        │
│  ┌──────────┐ ┌───────────┐ ┌────────────────┐   │
│  │Claude    │ │OpenCode   │ │Future Platforms│   │
│  │Code      │ │           │ │                │   │
│  └──────────┘ └───────────┘ └────────────────┘   │
└──────────────────────────────────────────────────┘
```

### 安装器架构

```
┌────────────────────────────────────────────────┐
│              SmartInstaller                     │
│                                                 │
│  ┌─────────────┐  ┌──────────────────────────┐  │
│  │KnownPack    │  │URLAnalyzer               │  │
│  │Installer    │  │                          │  │
│  │             │  │ • Clone to temp          │  │
│  │• registry   │  │ • Scan SKILL.md          │  │
│  │  lookup     │  │ • Parse README           │  │
│  │• predefined │  │ • Find setup scripts     │  │
│  │  rules      │  │ • Generate install plan  │  │
│  └─────────────┘  └──────────────────────────┘  │
│                                                 │
│  ┌─────────────┐  ┌──────────────────────────┐  │
│  │SingleFile   │  │LocalDir                  │  │
│  │Installer    │  │Installer                 │  │
│  │             │  │                          │  │
│  │• Download   │  │• Scan SKILL.md           │  │
│  │• Audit      │  │• Copy to target          │  │
│  │• Install    │  │• Create symlinks         │  │
│  └─────────────┘  └──────────────────────────┘  │
│                                                 │
│  ┌────────────────────────────────────────────┐  │
│  │              PostInstall                   │  │
│  │                                            │  │
│  │ • Security audit each skill                │  │
│  │ • Create platform symlinks                 │  │
│  │ • Update registry                          │  │
│  │ • Verify installation                      │  │
│  │ • Report to user                           │  │
│  └────────────────────────────────────────────┘  │
└────────────────────────────────────────────────┘
```

---

## 七、omx 的特殊处理：算法库 + Builtin Fallback

omx 与 superpowers/gstack 有本质区别：**部分技能包含可计算算法**，不能仅靠 SKILL.md 提示词实现。

### 区分三类代码

| 类型 | 示例 | 处理 |
|---|---|---|
| **纯算法** | `ambiguity.py`（数学公式）、`deslop.py`（slop 检测） | 保留为 `core/algorithms/` |
| **执行逻辑** | `loop.py`（循环状态）、`verifier.py`（subprocess 跑测试） | 移除 — 这是技能执行 |
| **SKILL.md** | omx 的 7 个技能定义 | 保留为 builtin fallback |

### 算法库（保留并重构）

```
core/
├── algorithms/          # 新增：可复用算法库
│   ├── interview/       # ambiguity scoring（数学公式，可复用）
│   └── ralph/           # deslop detection（AI slop 检测，可复用）
├── routing/             # 路由引擎（核心）
├── matching/            # 匹配算法
└── optimization/        # 偏好学习
```

**设计原则**：
- 算法库是**可选的** — 纯 SKILL.md 的技能无需依赖
- 算法库是**可复用的** — 任何技能都可以调用（不限于 omx）
- 算法库是**稳定的** — 版本化管理，向后兼容

> **文档**: 详见 [algorithms-guide.md](algorithms-guide.md) 获取完整使用指南和示例。

### omx 的双重存在

```
┌─────────────────┐          ┌─────────────────┐
│  Builtin        │          │  External       │
│  (内置 fallback)│          │  (vibe install) │
│                 │          │                 │
│  • SKILL.md     │          │  • SKILL.md     │
│  • algorithms/  │          │  • 最新功能     │
│  • 版本锁定     │          │  • 独立更新     │
└────────┬────────┘          └────────┬────────┘
         │                            │
         │    优先级                   │
         └────────────────────────────┼─────────────────→
                          外部 > 内置
```

| 存在形式 | 用途 | 更新方式 |
|---|---|---|
| **Builtin SKILL.md** | 用户没装外部 omx 时的 fallback | 随 VibeSOP 版本更新 |
| **外部 omx 包** | 用户 `vibe install omx` 获取最新版本 | 独立更新 |

当外部 omx 已安装时，优先使用外部版本；未安装时使用内置 SKILL.md + 算法库。

### 算法库调用方式

SKILL.md 中可以通过代码块引用算法库（可选的高级功能）：

````markdown
## Deep Interview

1. 计算初始 ambiguity:
   ```python
   from vibesop.algorithms.interview import compute_ambiguity
   result = compute_ambiguity(intent, outcome, scope, constraints, success)
   print(f"Ambiguity: {result.ambiguity:.2f}, Weakest: {result.weakest_dimension()}")
   ```

2. 根据 weakest_dimension 提问...
````

**注意**：这是可选的高级功能。纯 SKILL.md 的技能可以不使用算法库。

### 算法库 vs 技能包

| 维度 | algorithms/ | 技能包 (superpowers/omx/gstack) |
|------|-------------|--------------------------------|
| 安装方式 | 随 VibeSOP 安装 | `vibe install <pack>` |
| 更新方式 | 随 VibeSOP 更新 | `vibe update <pack>` |
| 位置 | `core/algorithms/` | `~/.config/skills/<pack>/` |
| 依赖 | 无外部依赖 | 可能依赖 algorithms/ |
| 用途 | 可复用计算算法 | 技能定义（SKILL.md） |

### 算法库版本策略

| 算法库 | 版本策略 | 破坏性更新 |
|--------|----------|-----------|
| `interview` | 跟随 VibeSOP 主版本 | V4.0 → V5.0 时可能 |
| `ralph` | 跟随 VibeSOP 主版本 | V4.0 → V5.0 时可能 |

**保证**：同一主版本内，算法库 API 向后兼容。

### omx 清理清单

| 文件 | 动作 | 原因 |
|---|---|---|
| `core/interview/ambiguity.py` | → `core/algorithms/interview/` | 纯数学公式，可复用 |
| `core/ralph/deslop.py` | → `core/algorithms/ralph/` | AI slop 检测，可复用 |
| `core/interview/pressure.py` | 删除 | 提示词模板，不需要 Python |
| `core/interview/crystallizer.py` | 删除 | 写文件，执行逻辑 |
| `core/interview/stages.py` | 删除 | 面试状态，执行逻辑 |
| `core/ralph/loop.py` | 删除 | 循环状态管理，执行逻辑 |
| `core/ralph/verifier.py` | 删除 | subprocess 跑测试，执行逻辑 |
| `core/skills/omx/*/SKILL.md` | 保留 | builtin fallback |
| `core/experiment/` | 删除 | 不是路由引擎职责 |
| `core/pipeline/` | 删除 | 执行逻辑 |
| `core/plan/` | 删除 | 执行逻辑 |
| `core/team/` | 删除 | 执行逻辑 |
| `cli/commands/omx.py` | 删除 | omx 快捷命令，外部包后不需要 |

---

## 八、清理计划

### 立即删除（v4.0）

| 模块 | 原因 |
|---|---|
| `triggers/` | 已废弃，功能被 `core/matching/` 替代 |
| `semantic/` | 已废弃，功能被 `core/matching/` 替代 |
| `cli/commands/auto.py` | 已废弃命令 |
| `core/config_module.py` | 已废弃，被 ConfigManager 替代 |
| `core/routing/engine.py` | 已废弃，被 UnifiedRouter 替代 |
| `core/experiment/` | karpathy/autoresearch evaluator，不是路由引擎职责 |
| `workflow/` | 路由引擎不执行工作流 |
| `workflow/experiment.py` | A/B 测试不是路由引擎职责 |

### 重构（v4.0）

| 模块 | 动作 | 原因 |
|---|---|---|
| `core/interview/ambiguity.py` | → `core/algorithms/interview/` | 纯算法，可复用 |
| `core/ralph/deslop.py` | → `core/algorithms/ralph/` | 纯算法，可复用 |
| `core/interview/` 其余 | 删除 | 执行逻辑 |
| `core/ralph/` 其余 | 删除 | 执行逻辑 |
| `core/pipeline/` | 删除 | 执行逻辑 |
| `core/plan/` | 删除 | 执行逻辑 |
| `core/team/` | 删除 | 执行逻辑 |
| `cli/commands/omx.py` | 删除 | omx 快捷命令 |

### 强化（持续）

| 模块 | 方向 |
|---|---|
| `core/routing/` | 路由准确性、性能优化 |
| `core/matching/` | 匹配算法优化、CJK 支持 |
| `core/optimization/` | 偏好学习精度、聚类效果 |
| `core/instinct/` | 从路由结果中学习，自动调整权重 |
| `core/memory/` | 会话上下文感知，路由决策参考 |
| `core/session_analyzer.py` | 模式发现是路由的输入信号 |
| `core/algorithms/` | **新增**：可复用算法库（ambiguity、deslop 等） |
| `installer/` | **智能安装器**：URL 分析、README 解析、安装计划生成 |
| `integrations/` | 技能健康监控、依赖检查 |
| `security/` | 外部技能审计完善 |

---

## 九、成功指标

| 指标 | 目标 | 当前 |
|---|---|---|
| 路由准确率 | >90% | ~85% (TODO.md 记录) |
| 路由延迟 P95 | <50ms | 待测量 |
| 技能发现覆盖率 | 100% 已安装技能 | 待验证 |
| 安装包分析准确率 | >95% 项目能正确识别技能位置 | 未实现 |
| 测试覆盖率 | >55% | 65.73% ✓ |
| Lint 错误 | 0 | 0 ✓ |
| 外部技能健康检查 | 100% 可检测 | 部分实现 |

---

*本文档是 VibeSOP-Py 项目的定位基准，所有开发决策应符合此定位。*
