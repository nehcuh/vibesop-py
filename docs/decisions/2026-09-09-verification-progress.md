# 验证器优化进度

## 当前状态

SPEC 已推送（`99185be`），四路实现进行中。[PR #119](https://github.com/nehcuh/vibesop-py/pull/119) 已建为草稿，CI 开始检查分支。目标版本：开发阶段 `8.3.0.dev1`，验收后 `8.3.0`。主控负责 spec、跟踪、审阅、集成和远程同步，具体实现交给真实 Grok / Kimi / Claude / Pi CLI。

## 节点日志

| 节点 | 状态 | 证据 / 说明 |
|---|---|---|
| M0：上一轮远程基线 | 完成 | `codex/practice-next-20260909` 已推送；基线 `efa616a` |
| M1：明确 spec | 完成 | [验证合同](../specs/2026-09-09-verification-contract.md)，固定文件归属与验收 |
| M2：四路实现 | 进行中 | Claude 计划生成；Grok 内置技能；Kimi 正文拒绝；Pi 版本/文档/集成合同；均从 `99185be` 的独立工作树启动 |
| M3：审阅及分批集成 | 待开始 | 每批记录提交、实际测试、退回原因与远程结果 |
| M4：整体验收 | 待开始 | 主机、Docker、固定路由及源码指纹 |
| M5：版本与远程收口 | 待开始 | 版本一致、PR/CI、最终提交 |

本机过程材料：`.omx/artifacts/verification-20260909/`。失败与未完成结果保留，不以代理自述作为验收通过。

启动纠正：Kimi 当前 CLI 不接受 `--auto` 与 `--prompt` 同用；已改用非交互 prompt 模式重启，首个失败保留在日志中。Grok 禁用上一轮故障的 `list_dir`，直接使用已知源码路径与 shell 检索。

主控复现：`before-contract.json` 记录了默认验证器为 `gstack/investigate`，不安全正文情况下 `execution_ready=true` 且 manifest 仍生成。静态检查另发现基线 29 个 error、119 个 warning；追加独立 Claude 类型修复会话，文件与 A/B/C/D 隔离，未放宽检查标准。

门禁问题：远程 Type Check 为绿但本机有 29 个 error。主控亲读锁定工具源码、用小文件实测，确认退出 3 表示配置错误，被现有 CI 错当“只有 warning”放行。追加 F 段给 Pi 在版本任务后串行修复，保留原始反例，最终必须验证有类型错误/无效配置都不能变绿。
