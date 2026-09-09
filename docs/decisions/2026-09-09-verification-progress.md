# 验证器优化进度

## 当前状态

四路主体已集成，当前版本候选 **`8.3.0`**，正在收口登记一致性与最终验收。[PR #119](https://github.com/nehcuh/vibesop-py/pull/119) 为草稿，随节点推送检查。主控负责 spec、跟踪、审阅、集成和远程同步，具体实现交给真实 Grok / Kimi / Claude / Pi CLI。

## 节点日志

| 节点 | 状态 | 证据 / 说明 |
|---|---|---|
| M0：上一轮远程基线 | 完成 | `codex/practice-next-20260909` 已推送；基线 `efa616a` |
| M1：明确 spec | 完成 | [验证合同](../specs/2026-09-09-verification-contract.md)，固定文件归属与验收 |
| M2：四路实现 | 主体完成 | Claude 计划生成；Grok 内置技能；Kimi 正文拒绝；Pi 版本/文档/集成合同；均从 `99185be` 的独立工作树启动 |
| M3：审阅及分批集成 | 进行中 | Grok B、Claude A/E、Pi F 均获独立 Kimi APPROVE；C 修正实读后状态后获 APPROVE；G 本地门禁待终审 |
| M4：整体验收 | 进行中 | 主体开发版本已启动主机常规回归；最终版本与 G 合流后冻结输入做最终验证 |
| M5：版本与远程收口 | 进行中 | 版本一致、PR/CI、最终提交 |

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

`029186e` 已将 A/E 与 Pi 的开发版本/类型门禁推送远程。C 已获独立 Kimi **APPROVE**，主控 Docker 的 C/D/F 相关测试 **26 passed**；评审指出的一处旧测试说明随集成修正为“阻断 manifest”。默认验证器、内容拒绝、真实集成合同至此均已通过定向验收。

G 初稿测试被主控退回：手写第二套 pytest 验收 if 不能证明生产脚本行为，改为提取并执行实际脚本阶段/Makefile 命令。Pi 正在准备 `8.3.0` 版本候选，处理 F 的脚本提示 NIT、删除不必要且不准确的 JSON 模式说明，并整理当前文档和 CHANGELOG。

### 最终版本候选验收

- `7c1fe66` 已推送 C 与集成合同；远程 Type Check / Lint / Security / Performance / Routing Benchmark 均实际通过，整套测试仍运行。
- 开发版常规回归为 **1 failed / 6996 passed / 15 skipped / 17 deselected**（144.55s）。唯一失败是新增 `verify-result` 未登记 `core/registry.yaml`；交 Grok 补齐注册，保留清单一致性断言，不通过放宽测试消除失败。完整失败凭据在 `host-dev/acceptance.json`。
- Grok G 返工完成，主控实跑发布阶段测试 + 类型门禁测试 **11 passed**；ruff check / format 全仓通过，最终候选严格类型检查 **0 errors**。独立 Kimi 正在复审 G。
- Pi 完成 `8.3.0` 版本及当前文档收口、F 提示分支 NIT；主控已集成。文档版本检查中历史 Windows 报告和两个 benchmark fixture 的原有版本继续保留，不改历史以追求形式全绿。

- G 获独立 Kimi **APPROVE**，主控复跑 **6 passed**，提交 `a29ff01`。Kimi 随后只为测试补充 Bash/grep 缺失时的明确 skip，主控复审并在 Bash 可用环境确认 6 项实际执行；不按 Windows 整体跳过。评审的“CI 只有 Linux”判断不准确，本项目有 Windows 3.12/3.13 必需检查，以远程实跑为准。既有 post/local 版本正则限制与共享 `/tmp/vibesop-build` 目录列为后续本地发布脚本维护项，不影响此次不打标签的代码交付。
- Grok 清单补登已合流，主控 RegistrySync + 内置技能 **20 passed**；固定路由检查 **39 题匹配、0 新失败、0 漂移**（保留 4 个已知失败与 2 个环境跳过）。仅更新注册文件输入指纹，所有非指纹数据逐项相等。
- 最终版本固定为 **8.3.0**（包元数据/CLI 一致），开始冻结输入做主机和离线 Linux 完整常规回归。
