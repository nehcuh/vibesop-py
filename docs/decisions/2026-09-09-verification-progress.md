# 验证器优化进度

## 当前状态

**8.3.0 候选的本机/锁定依赖 Docker 验收已完成；真实 Windows 验收发现跨平台问题，现重新进入修复。**四个真实 Grok / Kimi / Claude / Pi CLI 按 spec 执行，主控负责跟踪、审阅、集成、验收与推送。

已验收代码为 `b5057d6`；本记录后续仅作验收文档整理，应用与测试输入由下方 SHA256 清单固定。[PR #119](https://github.com/nehcuh/vibesop-py/pull/119) 汇总最终交付与[最新远程检查](https://github.com/nehcuh/vibesop-py/pull/119/checks)；[代码 CI](https://github.com/nehcuh/vibesop-py/actions/runs/34344829654) 提供各平台 job 的实时结果。

## 节点日志

| 节点 | 状态 | 证据 / 说明 |
|---|---|---|
| M0：上一轮远程基线 | 完成 | `codex/practice-next-20260909` 已推送；基线 `efa616a` |
| M1：明确 spec | 完成 | [验证合同](../specs/2026-09-09-verification-contract.md)，固定文件归属与验收 |
| M2：四路实现 | 完成 | Claude 计划生成；Grok 内置技能；Kimi 正文拒绝；Pi 版本/文档/集成合同；均从 `99185be` 的独立工作树启动 |
| M3：审阅及分批集成 | 完成 | B、A/E、C、F/G 及 GitHub 输出修正均获独立 Kimi APPROVE；退回项已修 |
| M4：整体验收 | 本机 / 容器通过 | 主机 7008 passed；锁定依赖离线 Linux 6998 passed；远程平台结果见 PR 检查页 |
| M5：版本与远程收口 | 已推送 | 8.3.0 包元数据 / CLI / 当前文档一致，PR #119；不打发布标签 |

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

### 最终回归发现与修正

- `1267f3d` 已推送版本与文档收口；Docker 在源码目录之外实际安装 wheel，确认 `verify-result` 与 registry 随包包含。
- 旧远程开发提交的 Ubuntu 3.12 完整日志回收后发现第二个失败：`GITHUB_ACTIONS=true` 会触发 basedpyright 的另一种输出模式，仅 warning 项目即使 `--level error` 仍返回 1。主控在本机亲证 F/G 两个 warning 用例均失败；显式 `PYRIGHT_DISABLE_GITHUB_ACTIONS_OUTPUT=1` 可恢复普通文本语义。已追加有界修复给 Pi，统一真实入口并覆盖该环境分支，不放宽错误/配置错误拒绝。
- `1267f3d` 离线 Linux 常规测试 **6993 passed / 25 skipped / 17 deselected**；随后的类型检查正确拒绝了验证容器中缺少 `/work/.venv` 的配置（退出 3），因此整条凭据保留为 **failed**。这是容器将依赖放在 `/opt/venv`、项目配置期望 `.venv` 的环境差异；下一次验证在可写副本补齐环境链接，不更改产品配置。

- `1267f3d` 主机完整常规回归 **7003 passed / 15 skipped / 17 deselected**（143.89s），凭据 `host-final/acceptance.json` 为 passed。后续变化仅 F/G 工具入口与门禁测试，应用源码保持不变；原有输入清单与失败凭据保留，下一轮使用独立 v2 验证材料。

- Pi 已统一 CI、Makefile、两份脚本的普通文本输出设置；主控退回并修正 warning 断言过宽、普通环境继承 GitHub 标记两处测试问题。独立 Kimi 对当前文件 **APPROVE**，亲跑 **16 passed**；主控在 `GITHUB_ACTIONS=true` 下 **16 passed**，真实类型脚本 **0 errors**。新旧输入比较确认仅 5 个工具/测试文件变化，应用源码与待测 wheel 不变。

### 8.3.0 最终机器验收（代码 `b5057d6`）

| 环境 / 检查 | 结果 | 证据 |
|---|---|---|
| 主机 macOS / Python 3.12，`GITHUB_ACTIONS=true` | **7008 passed / 15 skipped / 17 deselected**；150.89s | `host-final-v2/acceptance.json`，passed，运行前工作树干净 |
| 离线 Linux ARM64 / Python 3.12，锁定依赖、`GITHUB_ACTIONS=true` | **6998 passed / 25 skipped / 17 deselected**；87.50s；后续实际类型脚本与路由检查通过 | `linux-final-locked/acceptance.json`，passed，运行前工作树干净 |
| wheel 独立安装 | 8.3.0；内置验收技能与 registry 在 site-packages 中存在 | 容器在 `/tmp`、无源码导入路径时检查 |
| Docker 依赖 | 69 个适用依赖逐项符合 `uv.lock` 导出版本；NumPy 2.5.2 | `docker-locked-requirements.txt`；镜像 `vibesop-verify-830:locked` |
| 类型 / 格式 | 错误级诊断 **0 errors**；ruff check / 770 文件 format 检查通过 | 警告仍按既有规则非阻断，不声称清除了所有 warning |
| 固定路由 | 39 条与基线匹配；0 新失败 / 0 漂移 | 35/39 正确，4 个已知失败、2 个环境跳过，未改答案 |
| 远程 Ubuntu Python 3.12 / 3.13 | 各 **7008 passed / 15 skipped / 17 deselected**；覆盖率均 **80.00%** | [代码 CI](https://github.com/nehcuh/vibesop-py/actions/runs/34344829654) |
| 远程 Quickstart | Ubuntu / Windows 均 success | [Quickstart E2E](https://github.com/nehcuh/vibesop-py/actions/runs/34344829709) |

输入清单 `final-inputs-v2.json`（SHA256 `0a7556764907f03a48d20d9b7477b747c425d5a53f54f4a700810e33da4ad71e`）覆盖 1426 个文件，验收后复核无漂移。测试过滤器与 CI 相同：`not benchmark and not slow`；性能和路由基准另由远程 job 检查。

Docker 环境失败也保留：v1 缺 `.venv` 映射导致类型配置被拒；v2 类型脚本自动同步时试图下载锁定 NumPy，禁网导致失败（`docker-sync-probe.log` 亲证）。补齐映射、明确 `UV_NO_SYNC=1` 与离线运行后，兼容快照 v3 通过；随后构建阶段按锁文件准备依赖，最终锁定镜像也通过。未把这些失败凭据覆盖或改写成通过。

### 交付边界与后续

- 本轮代码按节点持续推送到 `codex/verification-contract-20260909`，最终文档提交只补验收事实，不改变上述代码 / 测试输入。PR 的检查页是远程状态的实时来源，PR 描述在矩阵结束后更新最终结果，避免为抄录每次 CI 状态反复制造新一轮相同代码的检查。
- 未创建 release tag、未发布 PyPI、未合并 main。后续发布可复用本次 spec、机器凭据与独立评审，但须针对实际发布提交执行发布流程。
- 剩余范围明确：固定题集的 4 个既有无匹配案例另设改进实验；历史 Windows 报告及两个 benchmark fixture 的版本号保留，文档版本扫描的这 3 个原有提示不当成本轮失败或强行改写。发布脚本的 post/local 版本支持与临时目录并发隔离是已有低优先级维护项。未将本轮结果当作多代理优于单代理的实验结论。

### Windows 门禁失败与重新分工

代码 CI Windows 3.12 最终为 **41 failed / 6950 passed / 32 skipped / 17 deselected / 82 rerun**（1193.20s）。与此前的单机通过不矛盾：CRLF、Windows ESM 路径/实际可执行文件、序列化路径断言、WSL 启动器误识别在 Windows 才触发。已按[四路 Windows spec](../specs/2026-09-09-windows-verification.md)分别交 Claude、Pi、Kimi、Grok 修复，保留所有原语义断言及 Windows 必需检查。PR 继续为草稿；先前本机/容器通过不宣称整个项目已经完成跨平台交付。

Windows 3.13 同样 41 failed / 6950 passed / 32 skipped / 82 rerun（1259.20s），七个失败文件与 3.12 完全相同：Kimi 配置 19、Pi 扩展 3、进程边界 8、计划可用性 3、正文安全 2、conformance 1、Bash 发布测试 5。已启动四个真实 CLI；额外 Claude 会话只在 Windows 完整回归前增加边界测试步骤，完整矩阵不变。取消代码完全相同的文档提交重复 CI，避免再次消耗同一组已知失败的运行。

W3 路径合同已由 Kimi 实现，主控读 diff：保留完整权威路径比较，unsafe 来源断言从尾部匹配加强为完整 Path 相等，未删业务断言；本机 57 passed。W5 CI 配置由额外 Claude 完成，主控解析 YAML 亲证仅插入边界测试步骤，移除该新增步骤后配置与原 CI 完全相同。

W1 初稿被主控退回：仅 rstrip 块尾 CR 虽能解析，但生产 `write_file_atomic` 使用 `write_text`，Windows 会把保留的 CRLF 再写成 CRCRLF。主控用 `write_text(newline="\r\n")` 亲证二次合并失败（`windows-crlf-review-roundtrip.json`）；要求实现者修完整文本往返，不用 `write_bytes` 测试绕开生产写入。Pi 的全盘 find 卡住 4 分钟已停止，指定现有 distlib 包的准确资源路径继续，不需新依赖。
