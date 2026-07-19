# Agent 场景验证报告：Claude Code / Kimi Code × vibesop × 场景矩阵

> **日期**: 2026-07-19
> **验证人**: Kimi（编排）+ DeepSeek（被测 LLM）
> **环境**: Docker `vibesop-agent-val:py3.12-v2`（val-base + claude-code 2.1.153 + kimi-code 官方单二进制，与宿主机同代）
> **原始证据**: `~/Projects/vibesop-val-artifacts/agent-2026-07-19/`（10MB，8 个 run 的 transcript、diff、.vibe 产物、部署日志；未入 git）

---

## 1. 验证设计

**被测矩阵**：2 个 Agent × {基线（无 vibesop）, 接入 vibesop} × 2 个场景 = **8 个 run**，全部 headless 非交互。

**演示项目**（每个 run 前重置）：
- `calc.py` — `divide()` 无除零处理（普通场景目标）
- `app.py` — `eval(user_expr)` RCE + `subprocess(shell=True)` 命令注入（动态场景目标）

**场景**：
- **普通场景（单意图）**：「修复 calc.py 里 divide 函数的除零错误……改完后运行 pytest 确认」
- **动态工作流场景（多意图）**：「审查这个项目：找出其中的安全和质量问题，修复它们，并补充 pytest 测试验证修复有效。」

**LLM 配置**（全部使用 `$DEEPSEEK_API_KEY`）：
- Claude Code → `ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic`（DeepSeek 的 Anthropic 兼容端点，实测可用）
- Kimi Code → `config.toml` 自定义 `openai` 类型 provider（`[models."deepseek-chat"] provider="deepseek"`）
- vibesop 路由/AI triage → 自动探测 `DEEPSEEK_API_KEY`（deepseek-v4-flash）

**接入方式（with-vibesop 组）**：`vibe build claude-code -o ~/.claude` / `vibe build kimi-cli -o ~/.kimi-code`（CLAUDE.md/AGENTS.md + hooks + settings.json）+ vibesop 以 `uv tool install` 安装到 agent 用户环境。

---

## 2. 结果总表

| Run | 退出码 | 代码产出（不含 .vibe） | 关键行为 |
|---|---|---|---|
| baseline-claude-normal | 0 | calc.py 修复 + 测试（36 行 diff） | 直接修复 |
| vibesop-claude-normal | 0 | 同上（754 行 diff 含 .vibe 产物） | hook 触发，triage 记录落盘 |
| baseline-claude-dynamic | 0 | app.py+calc.py 修复 + 2 测试文件 + requirements-dev.txt | **自发用 TaskCreate 分解 5 个子任务**，34 次工具调用 |
| vibesop-claude-dynamic | 0 | app.py+calc.py 修复 + 2 测试文件 | **收到注入的执行计划**，流程更精简 |
| baseline-kimi-normal | 0 | calc.py 修复 + 测试 | 直接修复 |
| vibesop-kimi-normal | 0 | 同上 | hook 触发 |
| baseline-kimi-dynamic | **124（超时）** | app.py+calc.py 修复 + 2 测试文件（未完成收尾） | 反复重读文件循环 |
| vibesop-kimi-dynamic | **124（超时）** | 仅 calc.py 修复 | **收到完整 squad 计划注入**，但仍陷入阅读循环 |

---

## 3. 核心发现

### 3.1 vibesop hook 注入链路在两个 Agent 上真实工作 ✅

**Claude Code**（transcript 证据，`b0d90f70….jsonl`）：
- `UserPromptSubmit` hook 触发 → vibesop AI triage 调用 deepseek-v4-flash（725 tokens，$0.0007）→ 选中 `builtin/deep-diagnosis-optimization`
- 注入系统消息：`🔀 VibeSOP detected multiple intents. Execution plan injected.`
- 项目目录生成完整 .vibe 产物（ai_triage_log.jsonl、sequences、session state、cache）

**Kimi Code**（stdout 证据）：
- Kimi 的 hook 同样触发并注入**完整 squad 执行计划**（原样照录）：

```json
[VibeSOP Execution Plan]
plan_id: 789f354f-681
steps:
  1. red_team  → builtin/slash-evaluate
  2. reviewer  → builtin/deep-diagnosis-optimization
  3. tester    → superpowers/debug
detected_intents: [learn_understand, type_checking, code_review, security_audit, test]
reasoning: Step 1: 'red_team' → builtin/slash-evaluate [+1 more] (squad); ...
```

→ **动态工作流的多意图识别 + 按角色选技能，在两个 Agent 上端到端成立。** baseline 组 4 个 run 全部无此产物（.vibe.tgz 为空）。

### 3.2 验证过程抓出 5 个真实部署问题（已全部定位）

| # | 问题 | 根因 | 处置 |
|---|---|---|---|
| 1 | `claude --dangerously-skip-permissions` 拒绝运行 | root 用户安全限制 | 容器内建非 root 用户 `val` |
| 2 | `kimi provider`/`--output-format` 不存在 | PyPI `kimi-cli` 是旧代 CLI；宿主机是官方单二进制 | 改用官方 install.sh（与宿主机同代） |
| 3 | `Model "deepseek/deepseek-chat" is not configured` | config.toml 需要 `[models.<alias>]` 独立条目（provider/model/max_context_size） | 查官方文档修正（见下方引用） |
| 4 | **hook 静默失败** `ModuleNotFoundError: No module named 'vibesop'` | route hook 只通过「能 import vibesop 的 python」解析运行环境：vibesop 项目检出 / uv run / **`~/.local/share/uv/tools/vibesop/bin/python`**。验证容器里三者皆无 → hook 退出码 1（non-blocking，Agent 无感知） | `uv tool install /repo` 到 agent 用户环境（= 真实用户安装形态）后修复 |
| 5 | `vibe` 命令 symlink 无效 | hook 不查 PATH 上的 vibe 二进制，只查 python | 随 #4 一并解决 |

> **#4 是最重要的产品发现**：`uv tool install vibesop` 是 hook 可用的事实前提。建议 `vibe doctor` 增加对该路径的检测与修复引导（当前是静默失败，用户无感知）。

### 3.3 Agent 行为差异（接入 vs 不接入）

**Claude Code**：
- **基线**：读到 AGENTS.md 后未使用 vibe；自发用 `TaskCreate` 拆出 5 个子任务（修复 calc / 修 eval / 修注入 / 两组测试），34 次工具调用，41 个测试通过，流程完整。
- **接入**：hook 注入执行计划后，未再创建任务列表，直接按「诊断 → 修复 → 验证」流推进，工具调用更精简；额外表现出更工程化的依赖处理（写 requirements-dev.txt、先验证 pytest 可用性）。
- **注意**：即使 CLAUDE.md 写明 `MANDATORY: Call vibe route`，Claude 在两次 run 中**均未自发调用 `vibe route`**——文本引导对模型不具备强制力，**hook 才是可靠通道**（vibesop 的架构设计正好如此）。

**Kimi Code**：
- **基线**：能完成普通场景；动态场景陷入「重读文件」循环（DeepSeek 模型倾向），420s 超时但已完成主要修复与测试文件。
- **接入**：收到了完整的 squad 计划注入（§3.1），但模型未按计划角色执行，仍陷入阅读循环，420s 超时，产出反而更少（仅 calc.py 修复）。
- **结论**：**注入成功 ≠ 执行遵从**。计划遵从度强依赖模型能力；DeepSeek（flash 级）在动态场景上两轮都超时，与是否接入 vibesop 无关。

### 3.4 代码产出对比

| 场景 | baseline | vibesop | 差异说明 |
|---|---|---|---|
| claude-normal | calc+test（36 行） | calc+test | 产出等价；vibesop 组多了 .vibe 遥测落盘 |
| claude-dynamic | 5 文件全修复 + 41 tests | 4 文件全修复 + tests | 均完成；vibesop 组流程更精简 |
| kimi-dynamic | 4 文件（超时） | 1 文件（超时） | 模型瓶颈主导，接入组还承担了路由开销 |

---

## 4. 结论

1. **核心机制验证通过**：vibesop 的 hook 注入（多意图识别 + 角色级技能选择 + 执行计划注入）在 Claude Code 与 Kimi Code 上端到端真实工作，且两个平台的 hook 配置（settings.json / config.toml + hooks 目录）均由 `vibe build` 正确部署。
2. **部署前提必须显性化**：hook 依赖 `uv tool install vibesop` 在用户环境（`~/.local/share/uv/tools/vibesop/`），否则静默失效。建议：① `vibe doctor` 增加该项检测 ② 安装文档置顶该前提。
3. **文本协议（AGENTS.md「MANDATORY」）不可依赖**：两个 Agent 都没有自发遵守「先 vibe route」的文本指令。当前架构以 hook 为主通道是正确的；AGENTS.md 应视为 hook 失效时的兜底提示。
4. **模型是动态工作流遵从度的最大变量**：DeepSeek-flash 级模型在动态场景循环严重（两轮均超时）。生产建议：动态/多角色场景的路由与执行使用更强模型；vibesop 侧的 triage 调用成本极低（$0.0007/次），无瓶颈。
5. **副产品**：vibesop 组的项目目录会多出 `.vibe/` 遥测产物（triager 日志、cache、session）——属预期设计，但用户首次见到可能困惑，建议在文档中说明。

## 5. 原始证据索引（`~/Projects/vibesop-val-artifacts/agent-2026-07-19/`）

- `<run>.log` — agent stdout（kimi 含完整 hook 注入文本；claude 为 JSON）
- `<run>.transcript.tgz` — Claude Code 完整会话 jsonl（含 hook attachment、全部 tool_use）
- `<run>.kimihome.tgz` — Kimi 的 `~/.kimi-code`（含 sessions/wire.jsonl、logs）
- `<run>.diff` / `.status` — 演示项目的 git 变更
- `<run>.vibe.tgz` — 演示项目内 vibesop 产物（baseline 组均为空）
- `deploy-*.log`、`deploy-layout.log`、`CLAUDE.md.sample`、`AGENTS.md.sample` — 部署证据

## 6. 环境踩坑记录（复现指南）

- Claude Code headless：`claude -p "..." --dangerously-skip-permissions --output-format json`（json 输出含 tool 调用），**不能以 root 运行 skip-permissions**
- DeepSeek Anthropic 兼容端点：`https://api.deepseek.com/anthropic` + `ANTHROPIC_AUTH_TOKEN` + `ANTHROPIC_MODEL=deepseek-chat`，实测可用
- Kimi Code：官方 install.sh 安装（PyPI 包是旧代）；`kimi -p` 单独使用（与 --yolo/--auto/--output-format 均互斥）；provider 配置格式见 [Kimi Code Providers 文档](https://www.kimi.com/code/docs/en/kimi-code-cli/configuration/providers.html)
- 验证迭代共 7 轮（v1 参数错误 → v2 非 root + 新代 kimi → v3 `-p` 互斥 → v4/v5 config 格式 → v6 prompt 引号断裂 + 证据采集 → v7 uv tool install 修复 hook）
