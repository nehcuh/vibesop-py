# 2026-10-09 优化开发验收

15 个已确认问题按 8 批修复，并追加 W1 Windows 验证补充。实际 Kimi 负责技术裁决，实际 Grok 与 Claude Code（GLM-5.3）参与开发和交叉复审；B1/B3/B7 在原生 Claude 鉴权不可用阶段由 Kimi 临时代写，后续用户明确授权 GLM。原生 Claude 模型未参与，身份依据为客户端配置、真实会话 init/modelUsage 与工具往返，未声称供应商服务端证明。

原始诊断见[冻结报告](../../archive/reviews/diagnosis/2026-10-09-deep-diagnosis/REPORT.md)，优化方向与后续路线见[执行计划](../../plans/2026-10-09-diagnosis-optimization.md)。

| 批次 | 实际实现 | 最终源提交 | 完整补丁 SHA-256 | 收批 |
| --- | --- | --- | --- | --- |
| B1 | Kimi | `ed8227dc` | `e57a62a80ca56e8083303aa3d74d23cd0492ff2787f7c0892fc01afeb5c3d366` | [Kimi 批准](gates/B1-kimi-closure-report.md) |
| B2 | Grok | `7d1160f0` | `cc3a9539572b64c827d0033516f35f81e869a0aea358034ea4f44385333021df` | [Kimi 批准](gates/B2-kimi-closure-report.md) |
| B3 | Kimi | `d9d7804f` | `98e69209f0a6fcbb847b813b5a814a46557e8c5885c1b4cae1876b1f3f2ec96b` | [Kimi 批准](gates/B3-kimi-final-closure-report.md) |
| B4 | Grok | `3305bcc9` | `1dd4a88029e4600e0e42f66bca0aff7abc2a17a7fe2b999bab7c999b4af77429` | [Kimi 批准](gates/B4-kimi-closure-report.md) |
| B5 | Claude Code (GLM-5.3) | `e0b83a05` | `759baff7b4fad44b9e92af0694104571f43b336a06e50fdd2f2d81a7b53f1d38` | [Kimi 批准](gates/B5-kimi-closure-report.md) |
| B6 | Grok | `74f41862` | `f82e80c7d1556a771571ebf3552ed2394bf695c77ff96e1708144cfef0fa8fad` | [Kimi 批准](gates/B6-kimi-closure-report.md) |
| B7 | Kimi | `df927f42` | `b83ed66c5d0bb0c0529abeda465e2d8038c8b3a9e2ea44deff49ebbfbe9176f0` | [Kimi 批准](gates/B7-kimi-closure-report.md) |
| B8 | Grok | `beda9953` | `009f0fc3d7caf952749a1d4937c13161bd741871c19af0f30f4dec39073ee157` | [Kimi 批准](gates/B8-kimi-closure-report.md) |
| W1 | Claude Code (GLM-5.3) | `bb0d1147` | `60813ebd5d2e08db36329a2fbf4771527ab2c4372a0e949d98682686185a33d5` | [Kimi 批准](gates/W1-kimi-closure-report.md) |

B3 初始提交 `57b6169d` 的 Grok 复审拒绝已保留；补充提交 `d9d7804f` 修复默认 adapter 丢失 blocked 事实，最终按补充补丁收批。每批均保留完整 diff、提交收据、实际模型预审、提交后独立 Grok 复审和 Kimi 收批。正式裁决原文在 gates/；[文件校验清单](formal-gates-manifest.json)绑定原字节。

## 机器验证

| 环境／入口 | 结果 |
| --- | --- |
| Linux Docker，Python 3.12／Node 24，全量非 slow/benchmark | 7,829 passed，26 skipped，20 deselected；覆盖率 80.95%（门槛 73%） |
| macOS，Python 3.12／Node 24，同一冻结源 | 7,839 passed，16 skipped，20 deselected |
| ruff／格式／basedpyright | 全部通过，805 个 Python 文件格式符合，0 errors／0 warnings／0 notes |
| hermetic 路由基线 | 59 项，0 新失败、0 漂移，6 个已知失败保留 |
| 独立 wheel 工具环境 | 两个平台 quickstart、部署后的 Claude hook、Grok hook、工具环境导入来源全部通过；安装依赖允许网络，路由演示不传密钥 |
| 真实沙箱 BUILD.sh | 成功产物发布及 required 非零退出合同通过；实际 Linux 容器，非 Windows 宿主证明 |

冻结集成候选的生产源码、批次测试与 workflow 字节均与最终源提交一致；文档整理另更新引用统计断言的计数，并单独复验引用门禁与对应测试，原 stale 基线不变。初次全量运行退出 3 未取得 pytest 结果，后续有 88 个文本断言失败：父执行器设置的 FORCE_COLOR=0 仍触发 Rich ANSI。保留所有失败记录，移除该变量、校正容器 .venv 类型检查环境后，同源全量回归通过。未通过改源码或下调门槛取得绿灯。

手写探针计数与实际 PASS 行数、补丁行数存在少量表述偏差，Kimi 已在 B4 收批登记并核对原始记录，本表使用实际 pytest 汇总。B6 收批时 Kimi 额外复跑了一次同源 Docker 112 项测试，与预设的该复审只读不运行 Docker 指令不一致；原报告和完整日志保留，未修改源文件或用户全局状态，该重复运行不被当作额外质量指标。

## Windows 验收边界

此记录是创建 PR 前的本地冻结检查点，原生 Windows 远程终验随后执行；最终同 HEAD 的结果以交付 PR 的实际 checks、PR 正文和库外冷归档的原始 CI/JUnit 收据为准。Linux／macOS 与旧 main 的绿灯不能替代新提交的 Windows 证明。W1 增加两版本边界／全量 JUnit 和部署 hook 的 Git Bash／LF／CRLF 原始字节观测。JUnit 记录逐 ID 最终结果，-ra 与默认 JUnit 不保证逐 ID 重试历史；若总重试非零且不可归属，必须保留该不确定性，不能当作无重试通过。17 项 B1 反例中，强制无 symlink 能力时实际 1 passed／16 skipped；4 项真实复制回退测试通过，但不能替代 16 项链接攻击反例。原生验收将逐 ID 核对这些案例与 B6 LOCK_HELD→CONTENDED→RELEASE→ACQUIRED 的实际 msvcrt 分支。

旧 Windows 基线只取得 job 成功 metadata，逐用例与重试记录不可得；本次做当前提交的单边证明，不制造基线差值。Windows Docker Desktop 的 Linux 容器宿主尚未验证，不能据此标为不支持；保留名、ADS、junction 等静态候选尚无原生确认，未纳入本轮修复结论。

## 实测限制与后续路线

DeepSeek 真接口运行保留 6/7、退出 1：T4 捕获到负缓存行，明确 PRECONDITION_MISSING。受控真实 producer 测试 7/7 已验证衰减数学及接受／拒绝／等值分支；线上正缓存命中分支仍未证明，未调整生产阈值、置信度或响应以伪造通过。

后续优先处理已有边界债务：B3 串行普通 dict 与跳过状态／事件桥的一致性；B5 单步 async、async callable 与自定义 Awaitable 的 API 范围；B6 clear-first／prune 与旧写者的边界及 set_instinct 增量语义；B4 全文件构建索引的内存上限；B2 内容深检查成本。独立评审中的低级别发现和未复现环境现象均保留在对应正式报告，不虚称已全部修复。

价值路线按顺序推进：真实宿主任务的合同与可重放验收 → 路由误注入／人工接管／耗时和成本指标 → 用真实用户任务比较收益 → 达到预设指标后再做跨宿主扩展与性能优化。现有创新主要是跨宿主 SOP 编译、路由与反馈闭环的工程组合；PMF、节省工时和算法新颖性仍需要实证，不凭测试数量或模型意见下结论。

## 整理与恢复

诊断 59 份原件逐字节可恢复：57 份小文本与报告按主题入 Git，2 份大数据在库外冷归档，见[迁移说明](../../maintenance/cleanup-migration-2026-10-09.md)。本轮模型日志、原始输出和历史失败另存库外精确成员归档，完成后记录 SHA 与恢复映射。原主目录 9 个用户未提交文件保持不变；未知实验、已有 worktree、分支、stash、共享容器／镜像和全局鉴权均保留。合并与发版尚未执行。
