# SOP：多 Agent 场景化验证（Scenario Validation）

> **版本**: 1.0（2026-07-19）
> **适用**: 验证 vibesop 对各编程 Agent（Claude Code / Kimi Code / Grok Build / Pi / OpenCode / Cursor / Zed / Codex）的优化效果
> **前置阅读**: `docs/dev/agent-scenario-validation-2026-07-19.md`（首轮验证报告，含 7 轮踩坑记录）

---

## 1. 目的与原则

在受控 Docker 容器中，以**可自动判定的客观指标**（测试脚本/ground-truth 比对，零 LLM 裁判）度量 Agent **接入 vibesop 前后**的行为差异。三原则：

1. **容器即真相**：一切结论必须有容器内运行证据（transcript + git diff + 产物文件）
2. **对照才有效**：同一场景必须同时跑 baseline（无 vibesop）与 with-vibesop，差值才是 vibesop 的贡献
3. **模型是混杂变量**：所有报告必须标注 Agent 版本 + 后端模型 + harness（CLI 代际），三者任一变化结果不可直接对比

## 2. 环境

### 2.1 验证镜像

基础镜像 `vibesop-val-base:py3.12`（`docker/val-base.Dockerfile`），按需要叠加 Agent CLI：

| Agent | 安装方式 | headless 调用 | 后端 LLM 配置 |
|---|---|---|---|
| Claude Code | `npm i -g @anthropic-ai/claude-code@<pin>` | `claude -p "<prompt>" --dangerously-skip-permissions --output-format json` | env：`ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic`、`ANTHROPIC_AUTH_TOKEN`、`ANTHROPIC_MODEL` |
| Kimi Code | 官方 install.sh（**PyPI kimi-cli 是旧代，勿用**） | `kimi -p "<prompt>"`（与 --yolo/--auto/--output-format **互斥**） | `~/.kimi-code/config.toml`：`[providers.deepseek] type="openai"` + `[models."<alias>"] provider/model/max_context_size` |
| Grok Build | `curl -fsSL https://x.ai/cli/install.sh \| bash`（支持 linux-aarch64） | `grok -p "<prompt>" -m <alias> --yolo --output-format json` | `~/.grok/config.toml`：`[model.<alias>] model/base_url/env_key`（chat_completions 默认） |
| Codex CLI | `npm i -g @openai/codex` | `codex exec` | **当前不可直连 DeepSeek**：Codex 已硬移除 `wire_api="chat"`，DeepSeek 无 `/responses` 端点。需 Responses→Chat 代理（暂缓） |

**通用约束（踩坑沉淀）**：
- 建非 root 用户 `val` 跑 Agent（claude skip-permissions 拒绝 root；二进制注意 `/root` 700 不可穿越——用 `cp -L` 拷实体文件到 `/usr/local/bin`）
- vibesop 必须以 `uv tool install` 装到 Agent 用户环境（`~/.local/share/uv/tools/vibesop/`），否则 route hook **静默失败**（`ModuleNotFoundError`，Agent 无感知）
- prompt 一律走文件传递（`"$(cat /tmp/prompt.txt)"`），内联引号会被 shell 截断
- 演示项目必须 `git init`（grok/codex 依赖 .git 发现项目根）

### 2.2 模型分层策略（调研结论，见 §7）

- **vibesop 路由/triage 端**：`deepseek-v4-flash`——单调用 JSON 输出场景 Flash 与 Pro 差距最小（1-3 分），成本低 3 倍
- **Agent 执行端**：多意图/长程场景用 `deepseek-v4-pro`——Terminal-Bench 2.0 Pro 67.9 vs Flash 56.9（+11），且避免 reasoning loop 超时
- **模型别名**：`deepseek-chat`/`deepseek-reasoner` 2026-07-24 退役，一律显式写 `deepseek-v4-flash` / `deepseek-v4-pro`

## 3. 场景库（8 类）

每个场景定义为一个目录：`prompt.txt`（任务）、`setup.sh`（环境）、`verify.sh`（客观判定，exit 0/1）、`meta.yaml`（能力点/期望技能/评价指标）。

| # | 场景类 | 测什么能力 | 客观判定 | 推荐案例来源 |
|---|---|---|---|---|
| 1 | Bug 修复 | 根因定位、最小修复 | FAIL_TO_PASS 测试通过 | [QuixBugs](https://github.com/jkoppel/QuixBugs)、[BugsInPy](https://github.com/soarsmu/BugsInPy) |
| 2 | 安全审查与修复 | 漏洞发现/修复、误报控制 | ground-truth recall/precision + exploit 脚本失效 | [Real-Vuln-Benchmark](https://github.com/kolega-ai/Real-Vuln-Benchmark)、[PyGoat](https://github.com/adeyosemanputra/pygoat) |
| 3 | 重构 | 行为保持的结构改善 | 测试全绿 + 复杂度指标下降 | 自种子仓库 |
| 4 | 多文件特性开发 | 跨文件实现 | 预写验收测试通过 | SWE-rebench 样本 |
| 5 | 测试编写 | 生成有效测试 | buggy 版失败/fixed 版通过 + 覆盖率增量 | [TDD-Bench](https://arxiv.org/pdf/2412.02883v1) 方法 |
| 6 | DevOps/终端任务 | 环境装配、排障 | 任务 verify 脚本二值 | [Terminal-Bench tasks](https://github.com/laude-institute/terminal-bench) cherry-pick |
| 7 | 代码理解问答 | 有据回答 | 事实断言清单 | 对验证仓库预设问题 |
| 8 | **Routing 准确率**（横切） | query→技能匹配 | top-1 命中 / Recall@3 / 混淆矩阵 / pass^k | 自建评测集（§5） |

**判定总则**：1-6 类零 LLM 裁判；7 类 rubric 仅辅助；8 类用信息检索标准指标（参考 [arXiv:2503.01763 工具检索协议](https://arxiv.org/pdf/2503.01763)）。

## 4. 执行流程

```
build image (§2.1) → smoke（每 agent 一句 OK）→
for scenario in 场景库:
  for agent in agents:
    baseline: setup → run → snapshot(transcript+diff+产物)
    with-vibesop: setup → deploy(vibe build <target> + AGENTS.md) → run → snapshot
  verify.sh 判定两组结果 → 记录三层指标
```

**部署方式**（with-vibesop 组）：
- hook 型平台（claude-code / kimi-cli）：`vibe build <target> -o ~/.<agent-home>` → hook 注入是主通道
- 无 adapter 平台（grok/zed 等）：仅项目根 `AGENTS.md` 引导（已知弱通道——模型不保证遵从，如实记录）
- 项目级技能：`vibe market install <repo> --scope project`

**证据采集**（每 run 必落）：`<run>.log`（stdout）、`<run>.transcript`（claude: `~/.claude/projects/**/*.jsonl`；kimi: `~/.kimi-code/sessions/`；grok: `--output-format json`）、`<run>.diff`（git diff）、`<run>.vibe.tgz`（demo 内 .vibe 产物——**baseline 必须为空**）。

## 5. 评价指标体系（三层）

### L1 任务成功率
`verify.sh` 二值 + pass^k（同一场景 k 次运行全成功比例，度量一致性，参考 τ-bench）

### L2 Routing 指标（vibesop 核心增值）
- hook 注入证据：transcript 中 `hook_system_message` / `additionalContext` 存在与否
- 路由准确性：§6 评测集（top-1 命中率、Recall@3、混淆矩阵）
- 消融对比：with-vibesop vs baseline 的任务成功率差、轮数/token 差

### L3 效率
轮数（tool calls 计数）、wall time、token 消耗（transcript usage 字段）、路由成本（triage ≈ $0.0007/次）

## 6. Routing 准确率评测集与经验闭环

### 6.1 评测集设计
`tests/benchmark/routing_eval.yaml`（新建）：
```yaml
- query: "帮我审查这个 PR 的安全问题"
  expect: [builtin/deep-diagnosis-optimization, builtin/code-review]
  reject: [builtin/slash-help]
  category: security_review
- query: ...
```
覆盖：每个内置技能 ≥3 条（中英混合、长短句、含噪声词如"帮我/请"）+ 对抗样本（易混淆技能对）。

### 6.2 运行与指标
`vibe route "<query>" --json` 离线批量跑 → top-1 命中率 / Recall@3 / 混淆矩阵；CI 门禁：命中率不回退（基线入库，降 >2% 报警）。

### 6.3 错误→经验闭环
识别错误时的处置流（对齐既有 instinct 学习）：
1. **记录**：错误样本追加到 `memory/routing-errors.jsonl`（query、期望、实际、层、置信度）
2. **归因**：人工/对抗 agent 分析错因类别（技能描述歧义 / 关键词污染 / 层优先级 / 训练数据缺失）
3. **教训入库**：可复用教训写入 `memory/project-knowledge.md`（Technical Pitfalls）；技能元数据问题修正对应 SKILL.md 的 description/trigger_when
4. **回归**：错误样本必须进入评测集（防复发），命中率趋势按周跟踪
5. **自动化增强**（后续）：高频混淆对可产出「路由提示」进 `.vibe/skill-routing.yaml`；instinct `record_outcome` 接显式反馈（`vibe feedback record` 已存在）

## 7. 已知失效模式与对策

| 失效模式 | 表现 | 根因（调研证据） | 对策 |
|---|---|---|---|
| Reasoning loop | Agent 反复重读文件直至超时 | 弱模型负反馈整合+上下文保持不足（SimpleQA Flash 34.1 vs Pro 57.9）；harness 无 compaction 补偿 | 执行端换 Pro；harness 加 todo/压缩；超时熔断 |
| Hook 静默失败 | 无注入、无 .vibe 产物 | vibesop 未 uv tool 安装到用户环境 | `vibe doctor` 检测（待办）+ 文档置顶 |
| 文本协议不遵从 | AGENTS.md「MANDATORY」被无视 | 模型对文本指令无强制遵从 | hook 为主通道；AGENTS.md 仅兜底 |
| 工具调用格式不兼容 | Agent 报工具错误 | 后端模型 function calling 兼容性 | 冒烟先行；换模型或 harness |

## 8. 新 Agent 接入 Checklist

1. 官方 CLI 是否支持 linux-aarch64 + headless（`-p`/`exec`）+ 权限跳过
2. BYOK：能否配置 OpenAI/Anthropic 兼容端点（写清配置文件字段）
3. root 限制、自更新开关、项目根发现机制
4. hook 体系是否存在（UserPromptSubmit 等价物）；vibesop 是否需要新 adapter
5. 一句 OK 冒烟 → 单场景试跑 → 纳入矩阵

## 9. 报告模板

每轮验证产出 `docs/dev/agent-scenario-validation-<date>.md`：矩阵表（run×退出码×产出）、三层指标、与上轮的 delta、发现的部署问题、原始证据路径（`~/Projects/vibesop-val-artifacts/<date>/`，不入 git）。
