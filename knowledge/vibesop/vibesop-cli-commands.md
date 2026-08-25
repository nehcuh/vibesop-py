---
name: vibesop-cli-commands
description: VibeSOP CLI 命令地图 — 路由与编排（route/orchestrate/decompose）、技能管理（install/skill/skills）、任务记忆与观测（recall/trace/instinct/pool）、工作流与反馈
type: domain_knowledge
tags:
  - vibesop
  - cli
  - commands
  - reference
---

# VibeSOP CLI 命令地图

VibeSOP 的 CLI 入口是 `vibe`（Typer + Rich 构建），共 60+ 命令。按用途分组如下。

## 路由与编排（最常用）

```bash
# 语义路由：query → 最佳技能
vibe route "<query>"

# 编排复杂多意图 query → 执行计划
vibe orchestrate "<query>"

# 只分解子任务，不路由
vibe decompose "<query>"

# 临时跳过确认
vibe route "<query>" --yes

# 指定编排模式 / 启用对抗验证
vibe route --pattern fan_out "分析架构并优化性能"
vibe route --verify "重构认证模块"
```

## 技能管理

```bash
vibe install <name-or-url>     # 安装技能包（带安全审计+自动配置）
vibe skills list               # 列出已装技能
vibe skills info <skill-id>    # 技能详情
vibe skills sync claude-code   # 同步到平台
vibe skill enable/disable <id> # 启用/禁用
vibe skill stale               # 检测过时/低效技能
vibe skill cleanup             # 交互式清理低质量技能
vibe skill lint <id>           # 技能静态检查
vibe skill outcomes            # 命中-结果原始计数（只读）
vibe skill end-check           # 会话收尾检查：保留建议+技能建议
```

## 任务记忆与观测（v8.0+）

```bash
# 语义检索过往任务轨迹（embedding 相似度）
vibe recall "<query>"
vibe recall "<query>" --cross-project   # 跨可信项目池召回

# 路由观测：span 指标与回放
vibe trace metrics
vibe trace replay <trace-id>

# 本能学习：工具序列挖掘与晋升
vibe analyze session          # 分析当前会话工具序列
vibe instinct eval            # 晋升成熟候选（≥5 次出现且 ≥80% 成功率）
vibe instinct status          # 本能清单

# 技能蒸馏队列：候选簇 → 人工 promote/dismiss
vibe skill scan-candidates    # 聚类近期 spans → 候选池
vibe skill candidates         # 列出待审候选
vibe skill promote <id>       # 候选 → SKILL.md 草稿（附 shadow verifier 徽章）
vibe skill dismiss <id>       # 否决候选

# 跨项目可信池
vibe pool add / list / remove / status
```

## 跨域工作流（v7.0+）

```bash
vibe workflows list-workflows
vibe prompt-chain run "为项目增加 Multi-Agent 能力"   # 诊断→生成分阶段提示词→容器验证
vibe prompt-chain generate "<topic>" --output ./prompts
vibe prompt-chain validate --container orbstack --json
```

`prompt-chain generate` 输出 7 个 `.md` 提示词文件（Phase 0 扇出诊断 → Phase 1-5 分阶段实现 → Final 端到端验证），每个文件可独立喂给 Claude Code 等编程 Agent。

## 反馈与偏好学习

```bash
vibe feedback record "<query>" "<skill>" --correct
vibe feedback record "<query>" "<skill>" --wrong "<actual-skill>"
vibe feedback report
vibe preferences / top-skills / route-stats
vibe record "<query>" "<skill>"   # 记录偏好选择
```

## 会话智能路由

```bash
vibe session enable-tracking
vibe session record-tool --tool "read" --skill "systematic-debugging"
vibe session check-reroute "<query>" --skill <id>
vibe session summary
```

会话追踪默认开启（`routing.session_aware: true`），支持多轮对话重路由；可用 `vibe config set routing.session_aware false` 关闭（性能/隐私/控制考虑）。

## 环境与维护

```bash
vibe doctor          # 环境体检（LLM/平台/hooks）
vibe status          # 技能生态统一快照
vibe quickstart      # 交互式初始化向导
vibe onboard         # 新手引导
vibe dashboard       # Web 可视化面板
vibe inspect / verify / targets / switch / snapshot
vibe trust           # 技能包信任名单管理
vibe market          # 公共技能生态搜索与安装
vibe skill-craft     # 从会话历史提炼个人技能
vibe import-rules    # 导入外部遗留规则（实验性）
```

完整参考：`docs/user/CLI_REFERENCE.md`。任何命令加 `--help` 看详情。
