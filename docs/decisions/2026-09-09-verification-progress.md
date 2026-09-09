# 验证器优化进度

## 当前状态

四路主体已进入集成，当前开发版本 **`8.3.0.dev1`**（CLI 与包元数据已核对），目标收口版本 `8.3.0`。[PR #119](https://github.com/nehcuh/vibesop-py/pull/119) 为草稿，随节点推送检查。主控负责 spec、跟踪、审阅、集成和远程同步，具体实现交给真实 Grok / Kimi / Claude / Pi CLI。

## 节点日志

| 节点 | 状态 | 证据 / 说明 |
|---|---|---|
| M0：上一轮远程基线 | 完成 | `codex/practice-next-20260909` 已推送；基线 `efa616a` |
| M1：明确 spec | 完成 | [验证合同](../specs/2026-09-09-verification-contract.md)，固定文件归属与验收 |
| M2：四路实现 | 进行中 | Claude 计划生成；Grok 内置技能；Kimi 正文拒绝；Pi 版本/文档/集成合同；均从 `99185be` 的独立工作树启动 |
| M3：审阅及分批集成 | 进行中 | Grok B、Claude A/E、Pi F 均获独立 Kimi APPROVE；C 修正实读后状态后待终审；G 本地门禁实现中 |
| M4：整体验收 | 待开始 | 主机、Docker、固定路由及源码指纹 |
| M5：版本与远程收口 | 待开始 | 版本一致、PR/CI、最终提交 |

本机过程材料：`.omx/artifacts/verification-20260909/`。失败与未完成结果保留，不以代理自述作为验收通过。

启动纠正：Kimi 当前 CLI 不接受 `--auto` 与 `--prompt` 同用；已改用非交互 prompt 模式重启，首个失败保留在日志中。Grok 禁用上一轮故障的 `list_dir`，直接使用已知源码路径与 shell 检索。

主控复现：`before-contract.json` 记录了默认验证器为 `gstack/investigate`，不安全正文情况下 `execution_ready=true` 且 manifest 仍生成。静态检查另发现基线 29 个 error、119 个 warning；追加独立 Claude 类型修复会话，文件与 A/B/C/D 隔离，未放宽检查标准。

门禁问题：远程 Type Check 为绿但本机有 29 个 error。主控亲读锁定工具源码、用小文件实测，确认退出 3 表示配置错误，被现有 CI 错当“只有 warning”放行。追加 F 段给 Pi 在版本任务后串行修复，保留原始反例，最终必须验证有类型错误/无效配置都不能变绿。

### M2/M3 路线进展

- Grok：已实际创建两个指定文件；主控复跑真实加载/扫描测试 **4 passed**，Docker 同样 **4 passed**，ruff 通过；独立 Kimi 只读复审 **APPROVE**，集成提交 `ac7f37a` 已推送。`read_file` 曾报工具错误，但执行器恢复并完成写入，本轮有真实代码产出。新增技能导致路由题集输入指纹变化，刷新只增加该文件及总指纹；39 道题的结果记录完全未变。
- Claude A：主控退回显式 `None` 被当默认、测试 helper 把空列表换成默认数据两处问题；Claude 已修正，另清除该文件未绑定变量错误。报告定向 **46 passed**、组合 **570 passed**；独立 Kimi 复审进行中。
- Kimi C：已复现 unsafe 仍生成 manifest，正在实现统一阻断。
- Pi D：开发版本及当前版本文档已完成初稿；3 个集成测试因 A/B/C 尚未合流而真实失败，保留失败结果。现已串行交办 F 门禁修复及两处文档表述纠正。
- Claude E：独立类型错误修复进行中。

远程队列维护：取消已被新提交替代的旧 CI 运行，保留最新提交的 CI；已完成的旧运行不重启。

Kimi C 主控初审：`kimi-swap-review.json` 亲证检查后改文件时 manifest 抛错却留 `execution_ready=true`；准备退回实际读取后拒绝路径，要求同步 blocked 状态和原因，相邻缺失/空内容路径一起核对，仍由 Kimi 修正。

### 集成检查点

- `a7b66cd`：Claude A 默认/显式验证器，独立 Kimi APPROVE；主控本机 **50 passed**（含 B）、Docker **50 passed**。主控仅运行统一 formatter 修正两文件格式，再跑 A 的 **46 passed**，未替代理编写实现。
- `a7dcfe6`：Claude E 类型错误修复，独立 Kimi APPROVE；主控 Docker 相关套件 **436 passed / 10 skipped**。有效类型规则没有降低。
- Pi D/F：开发版本、配置修正、真实类型门禁测试已集成，独立 Kimi APPROVE（一个非阻塞脚本提示分支 NIT，交回 Pi 清理）。主控 A/B/F 定向 **55 passed**。
- C 合流后，主控真实 A/B/C/D 集成合同、磁盘交换及类型门禁 **16 passed**；`uv run basedpyright --level error` **0 errors**。C 的报告为 runtime **196 passed**、相关组合 **1192 passed**，独立复审进行中。
- G：`release-gate-before.json` 记录真实 pytest **1 failed / 1 passed、exit 1**，旧发布流水线却 **exit 0**。同类入口已交 Grok 修复，避免只修云端门禁而保留本地假通过。
