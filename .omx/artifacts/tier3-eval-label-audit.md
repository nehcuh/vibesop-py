# Tier-3 标注审计报告 — `tests/benchmark/routing_eval_extended.yaml`（130 条）

> 审计日期： 2026-08-19 ｜ 审计方式： 只读人工初审（未修改任何文件）
> 目的： 在 `--merge` 进主 eval 集之前，供人工确认的弱标注一审。

## 结论摘要

**这批标签大部分不能直接作为 ground truth。** 130 条中：

| Bucket | 数量 | 占比 |
|---|---|---|
| CORRECT（标签明确正确且可在本仓库解析） | 15 | 12% |
| AMBIGUOUS（语义尚可但不可解析 / 泛 workflow 归属存疑） | 43 | 33% |
| WRONG（标签与 query 语义矛盾 / 垃圾标签 / 不可能产出的 id） | 59 | 45% |
| LOW-VALUE（上下文残句/选项答复，无路由信号） | 13 | 10% |

注意 CORRECT 的构成：15 条里 13 条是 `expect: []`（无标注，语义上确实该 no-match），真正"正标签明确正确"的只有 2 条：L246（`builtin/deep-diagnosis-optimization`）和 L438（`builtin/session-end`）。也就是说 **116 条弱标注里只有 ~2 条可以原样确认**。

## A. 系统性问题（影响整批，先于逐条确认处理）

1. **外源技能目录污染（根因）。** 弱标签来自 `scripts/build_eval_from_logs.py` 用*源项目*（CMspark）的 `ai_triage_log.jsonl` 里 `selected_skill` 做的 join。源项目的候选集 ≠ 本仓库目录。约 **62 条**标签引用了本仓库路由器不可能产出的 skill id：`mattpocock/*`(13)、`git-guardrails-claude-code`(9)、`improve-codebase-architecture`(8)、`diagnose`(7)、`grill-with-docs`(4)、`project/omx/*`(3)、`ui-ux-pro-max-skill/*`(3)、`design-an-interface`(2)、`analyze`(2)、`omx/*`(2)、及 `review`/`triage`/`ask-claude`/`writing-shape`/`verification-before-completion`/`requesting-code-review` 等单次项。证据：`core/registry.yaml` 的 namespaces 只有 builtin/superpowers/omx/project，`vibe install` 仅支持 gstack/superpowers/omx——没有 mattpocock pack。这些条目若按原样 merge，是**永久性的假错误**。
2. **垃圾标签。** L464 `清理吧` 的 expect 就是 query 原文 `清理吧`——LLM triage 复读失败产物。
3. **`expect: []`（14 条）的语义不是"期望 no-match"。** `build_entries` 里 `skill = labels.get(q)`，空列表只表示 triage 日志里没 join 上。而 `eval_routing.py` 对空 expect 的判定是 `primary not in reject`（reject 也空）→ **永远通过**。这些条目合并时会被 `merge_confirmed` 跳过（要求 expect 非空），所以它们留在文件里只是文档，不提供任何度量信号。若想要负例测试，需要 harness 支持 no-match 断言或填 `reject`。
4. **同义 query 标注互相矛盾（弱标注噪声的直接证据）：**
   - 进展查询：`检查下当前项目进展`(L24)→`[]`、`项目当前进展如何？`(L422)→`[]`、`当前进展如何，还有未完成工作么？`(L828)→`builtin/riper-workflow`、`当前项目整体进展如何了？`(L840)→`triage`。同义句四种标法。
   - 截图权限问题：L639→`builtin/session-end`、L385→`builtin/deep-diagnosis-optimization`、L511/L655→`diagnose`。
   - DMG 重编译：L404/L671 近似重复条目（差一个"吧"），同标 `improve-codebase-architecture`（构建任务标架构优化，语义也不对）。
5. **id 格式五种并存**：`builtin/x`、裸 id（`diagnose`/`analyze`/`review`…）、`mattpocock/x`、`omx/x`、`project/omx/ci` 三层路径。两个消费者对命名空间的容忍度不同：`eval_routing.py` 精确匹配 `primary in expect`，`calibrate_index_threshold.py` 只比最后一段（`_is_hit` 注释自述"weak labels often drop the namespace"）。确认时应统一为 canonical `namespace/name`。
6. **RIPER 标签过度扩张。** 27 条 `builtin/riper-workflow` 里绝大多数是"使用 workflow"/"继续 X"/"做 D1c"这类。该 skill 自述："Use ONLY when the user explicitly requests the RIPER structured 5-phase development workflow. **Not for generic analysis, planning, or review tasks.**" 按此标准，绝大多数 riper 标签应为 `[]`。
7. **schema 无 expected layer 字段**（任务书里提到 layer 维度——实际 schema 只有 query/expect/category/needs_review/weak_label）；所有条目 `category: production_log`，无区分度；无一条使用 `reject`。
8. **~10 条巨型子代理提示词**（SKEPTIC 审计、UX 验收、WORKTREE 验证等）是 agent-to-agent prompt，不是代表性用户路由 query，建议单独成类或剔除出用户路由 eval。
9. **下游已受影响：** `scripts/calibrate_index_threshold.py` 已用这批弱标签（`needs_review && weak_label`）标定 M3 的 `index_match_threshold`——**当前生产阈值是被这些标签污染过的**，重标后应重新标定。

## B. 处理建议（按优先级）

1. 先修 label-space：决定 eval 目录 = 本仓库可产出 skill 集合；外源 id 统一改 `[]`（或在 eval 环境装对应 pack 后再保留 `using-git-worktrees`/`requesting-code-review` 这类语义正确的 superpowers 标签）。
2. 修 L464 垃圾标签；去重 L404/L671。
3. 统一 id 为 canonical 形式。
4. 按 D/E 节逐条确认；LOW-VALUE 除 `[Image #1]` 等 1-2 条负例外建议 drop。
5. 全部确认后重跑 `calibrate_index_threshold.py`。

## C. 逐条明细

### CORRECT（15 条，其中 13 条为 `expect: []`）

| 行 | query | 标签 | 说明 |
|---|---|---|---|

| 24 | 检查下当前项目进展 | `[]` | 状态查询，目录内无对应 skill |
| 28 | 会议只能 / 输入 meeting…5 点产品反馈 | `[]` | 产品反馈汇总，无可路由 skill |
| 81 | push到远程 | `[]` | 目录内无 git skill；可作负例 |
| 117 | PI REVIEWER gate for CMspark UIUX v2 node PR6… | `[]` | 评审请求，目录内无 review skill |
| 127 | INDEPENDENT adversarial TEST/QA reviewer… | `[]` | 子代理 QA 提示词 |
| 156 | Implement M1 Task 6 ONLY on branch feat/voice-local-stt-m1 | `[]` | 实现任务，无 skill |
| 179 | Do not re-implement code. Dual external review P1-1 | `[]` | 评审指令 |
| 246 | 首先我需要你使用 fanout 对项目做多维度，深度的体检和审查 | `builtin/deep-diagnosis-optimization` | 『深度体检和审查』命中 ddo 触发词『深度诊断/审查』 |
| 422 | 项目当前进展如何？ | `[]` | 状态查询（对比 L828→riper、L840→triage，标注不一致） |
| 438 | 我先离开了 | `builtin/session-end` | 命中 session-end 触发词『离开』 |
| 482 | P1-3 evaluate post-approval code integrity… | `[]` | 工作项速记 |
| 645 | Verify CONDITIONAL GO acceptance A1-A5… | `[]` | 验收核对 |
| 661 | Batch 2 (Correctness P0s) Implementation Brief — for Grok Review | `[]` | 评审简报 |
| 677 | ❌ 安全阻断: Security Block: Access to cookie… | `[]` | 错误消息粘贴 |
| 816 | Code review for a focus-preservation fix in a Swift tray binary… | `[]` | 评审请求，目录内无 review skill |

### WRONG（59 条，按置信度排列：语义矛盾在前，外源不可解析在后）

| 行 | query | 现标签 | 建议改为 | 一句话证据 |
|---|---|---|---|---|

| 111 | 使用独立多路对抗的方式，将所有分歧收敛 | `builtin/deep-diagnosis-optimization` | [] | ddo=代码库诊断→批量优化→CI 绿；这是分歧收敛，非代码诊断 |
| 132 | commit 三批改动 | `builtin/session-end` | [] | 提交请求；session-end 触发词是『离开/收工/再见』类退出信号 |
| 167 | 这块也可以作为后续优化的一个方向 | `builtin/deep-diagnosis-optimization` | [] | 感叹/备注，非诊断请求 |
| 216 | 我们当前项目集成的文档解析器是什么？效果如何…？ | `builtin/deep-diagnosis-optimization` | [] | 事实性提问，非『深度诊断/优化项目』 |
| 222 | PI REVIEWER gate for CMspark UIUX v2 node PR7 | `builtin/riper-workflow` | [] | 评审请求；RIPER 自述『ONLY when user explicitly requests RIPER』 |
| 234 | P1-1 God-mode / dangerous flag…security arm | `builtin/session-end` | [] | 工作项速记，非会话结束 |
| 252 | A->可以打开微信…E->APP 常藏后台（实测反馈汇总） | `builtin/session-end` | [] | 测试反馈汇总，无退出信号 |
| 273 | 1./code 弹窗没反应…独立对抗多 agent 产品重思考 | `builtin/riper-workflow` | [] | 产品重思考+bug 反馈混合，非 RIPER |
| 282 | 本机转写：麦克风音频经鉴权通道…（隐私说明文案） | `builtin/autonomous-experiment` | [] | 粘贴的说明文案；experiment 需 .vibe/experiment.yaml 的实验循环 |
| 309 | P1-2 MCP + navigate L2 originWs binding…confirmations | `builtin/riper-workflow` | [] | 工作项速记 |
| 347 | full-autonomy 之前做的，也要提交 | `builtin/riper-workflow` | [] | 提交请求 |
| 359 | …模块 shell 和 netsec 未启用…还没进行实现么？ | `builtin/riper-workflow` | [] | 实现状态提问 |
| 365 | 有个问题，为什么语音识别只能识别几句话，然后就停了 | `builtin/session-end` | [] | bug 提问被标成会话结束——弱标注噪声的典型案例 |
| 476 | God Mode就是需要全自动巡航…无人值守是硬需求 | `builtin/riper-workflow` | [] | 产品理念陈述 |
| 499 | PR5 — Hide/remove BottomBar strip behind flag | `builtin/riper-workflow` | [] | 任务标题 |
| 580 | 对话 #l74du8…报 url and expression required 错误 | `builtin/skill-craft` | [] | 错误报告；skill-craft 是『从会话历史提炼生成新技能』 |
| 599 | 我运行的是 /Application/CMspark.app | `builtin/deep-diagnosis-optimization` | [] | 陈述句 |
| 639 | 不对啊，我都已经给了截图权限，怎么还是弹窗问我要权限？ | `builtin/session-end` | [] | bug 提问被标成会话结束 |
| 683 | 使用 Claude + Pi 的双路评审 | `builtin/deep-diagnosis-optimization` | [] | 评审请求 |
| 689 | WORKTREE: …npx tsc --noEmit…run tests…ok=true only if… | `builtin/riper-workflow` | [] | 验证子代理提示词 |
| 730 | Implement W4+W5 for CMspark Side Panel design debt | `builtin/deep-diagnosis-optimization` | [] | 实现任务 |
| 736 | 帮我创建 PR，然后个饼 | `builtin/riper-workflow` | [] | PR 请求+乱码 |
| 742 | 你要不也看下 zed 这个项目，他们的 acp 是如何实现的… | `builtin/deep-diagnosis-optimization` | [] | 调研/产品讨论 |
| 749 | 当前 /Applications/CMspark.app 是否是最新代码编译出来的 | `builtin/deep-diagnosis-optimization` | [] | 状态提问 |
| 773 | 我设想…新增会议记录场景…按照目前的设计，做不到么？ | `builtin/skill-craft` | [] | 产品能力提问；skill-craft 是生成新技能 |
| 822 | 帮我合 130 吧 | `builtin/riper-workflow` | [] | 合并 PR |
| 828 | 当前进展如何，还有未完成工作么？ | `builtin/riper-workflow` | [] | 状态提问；与 L24/L422([]) 标注自相矛盾 |
| 33 | 继续做 URL/cookie admission | `improve-codebase-architecture` | [] | 续作任务；该 id 不在本仓库目录 |
| 45 | 我看 PR87 失败了，其他都成功了 | `mattpocock/review` | [] | CI 失败通报 ≠ review；外源 id |
| 63 | 对了，当前项目的文档是否更新了？ | `grill-with-docs` | [] | 外源 id；目录内无文档问答 skill |
| 75 | 似乎有其他进程没有关闭，帮我先关闭了 | `diagnose` | [] | 杀进程请求 ≠ 诊断；外源 id |
| 85 | CI 绿了以后帮我合并到 main | `project/omx/ci` | [] | project/* 是源项目本地 skill，本仓库不可能产出 |
| 97 | You are an independent PRODUCT/UX acceptance agent… | `design-an-interface` | [] | 验收评审提示词 ≠ 界面设计；外源 id |
| 150 | 那么在提示上是不是可以更加浅显易懂…？ | `analyze` | [] | UX 文案讨论；外源 id |
| 173 | docs reorg Phase 1 factual corrections README… | `improve-codebase-architecture` | [] | 文档修订任务；外源 id |
| 183 | 本地也帮我切到main…其他分支都清理干净 | `mattpocock/review` | [] | git 清理 ≠ review |
| 195 | 我们在文档中是否说明了这些？ | `grill-with-docs` | [] | 外源 id |
| 201 | src/tabs/voice-spike.tsx:256 error TS2339… | `mattpocock/review` | [] | 编译错误粘贴 ≠ review |
| 290 | 几个优化点：1.设置选项太多…3.自动压缩 | `ui-ux-pro-max-skill/design` | [] | 外源 id |
| 392 | 用户实测 A微信反复批准前台失败 C邮箱… | `project/ui-ux-pro-max-skill/feature_request` | [] | 外源 project-local id |
| 404 | 帮我重新编译 DMG 并替换当前运行的程序吧 | `improve-codebase-architecture` | [] | 构建任务；与 L671 近似重复 |
| 456 | Harden companion/src/acp/open-local-terminal.ts…unit tests | `verification-before-completion` | [] | 加固实现任务 ≠ 完成前验证；外源 id |
| 464 | 清理吧 | `清理吧` | drop 或 [] | 数据 bug：label 是 query 原文复读，无此 skill |
| 470 | 使用 pi 进行复审，并没有发 PR | `project/omx/pr-check` | [] | 源项目本地 id |
| 486 | 我记得之前出现过类似的问题…推特禁止 CSP 注入… | `omx/analyze` | [] | 外源 id；复发 bug 排查 |
| 536 | 帮我找找看中文视觉模型…百度阿里腾讯智谱… | `analyze` | [] | 调研请求；外源 id |
| 574 | 文档是否有记录这块内容？ | `grill-with-docs` | [] | 外源 id |
| 593 | 帮我把 /Applications 下面备份的其他文件都清理了吧 | `improve-codebase-architecture` | [] | 文件清理 |
| 627 | grill N1-N10, 使用 pi agent 和 claude code 一起讨论… | `grill-with-docs` | [] | 外源 id |
| 649 | 可以，开始吧 Daily Content Loop 场景 brief | `mattpocock/grill-me` | [] | 外源 id |
| 671 | 帮我重新编译 DMG 并替换当前运行的程序 | `improve-codebase-architecture` | [] | L404 近似重复 |
| 717 | 补 HTTP e2e | `improve-codebase-architecture` | [] | 补测试任务 |
| 755 | 按批次拆 commit | `mattpocock/request-refactor-plan` | [] | 拆 commit ≠ refactor plan；外源 id |
| 767 | 继续拆 WS lifecycle / confirm response | `mattpocock/grill-with-docs` | [] | 外源 id |
| 785 | 当前项目的 tinyclick 点击下载模型没有反映 | `project/ui-ux-pro-max-skill/bug_report` | [] | 外源 id |
| 791 | 盯 CI / 自动合并 | `project/omx/ci` | [] | 外源 id |
| 797 | 帮我热更新下，我使用的是 dist-package 下面的 | `diagnose` | [] | 热更新请求 ≠ 诊断 |
| 803 | 帮我判断下还有哪些没有合并进来的…都帮我删除了吧… | `improve-codebase-architecture` | [] | git 分支清理 |
| 840 | 当前项目整体进展如何了？ | `triage` | [] | 状态提问；无 triage skill；同义句三种标法 |

### AMBIGUOUS（43 条，需人工裁决）

| 行 | query | 现标签 | 建议 | 说明 |
|---|---|---|---|---|

| 3 | You are an adversarial SKEPTIC…refute finding TEST-3 | `builtin/deep-diagnosis-optimization` | keep ddo 或 drop | 子代理 finding 验证提示词，非用户路由请求；ddo 的『深度诊断/审查』是目录内最近似项 |
| 39 | 很棒，帮我合并到主分支并提交吧 | `git-guardrails-claude-code` | []（除非 eval 环境装该 pack） | 语义合理但 id 不可解析（非 builtin/superpowers/omx） |
| 91 | 先合 #177 再合 #178 | `git-guardrails-claude-code` | [] | git 合并，语义对但 id 不可解析 |
| 121 | 创建并打开 PR，没问题就帮我合并到 main | `mattpocock/review` | [] | 外源 id；PR 创建+合并 |
| 144 | 拉取最新变更并进行评审 | `mattpocock/review` | [] | 语义对（评审），外源 id |
| 161 | 删掉 mission-pack-p0 worktree 并清理远程分 | `using-git-worktrees` | []（若 eval 环境装 superpowers 则保留） | 语义正确（superpowers skill，registry 引用了它），但条件性可解析 |
| 189 | 当前代码是否保存并提交远程了？ | `git-guardrails-claude-code` | [] | git 状态问题，外源 id |
| 210 | 保存并提交远程 | `git-guardrails-claude-code` | [] | git 提交，外源 id |
| 228 | 做一轮 dual-review | `mattpocock/review` | [] | 语义对，外源 id |
| 240 | 可以，使用 workflow 的方式开始吧…pi 介入复审 | `builtin/riper-workflow` | [] | 泛『workflow』≠ 显式 RIPER；按 skill 自述应为 no-match |
| 261 | 先让 pi 和 claude 进入评审…双路复审后再开发 | `mattpocock/review` | [] | 语义对，外源 id |
| 267 | 清 worktree/stash | `using-git-worktrees` | []（或装 superpowers 保留） | 语义正确，条件性可解析 |
| 297 | commit 修订后开始按照我们之前设定的开发方式进行开发吧 | `builtin/riper-workflow` | [] | 『之前的开发方式』未指明 RIPER |
| 303 | 现在我想你帮我重新思考我们的APP，界面如何设计… | `design-an-interface` | [] | 语义对，外源 id |
| 315 | 帮我合并到 main 吧 | `git-guardrails-claude-code` | [] | 外源 id |
| 321 | Computer-Use Mechanism Research — Review Request… | `mattpocock/review` | [] | 语义对，外源 id |
| 328 | …使用对抗验证的方式，使用 workflow 来针对这里的 feature 深入探讨 | `builtin/riper-workflow` | [] | 泛 workflow |
| 335 | 帮我合并到主分支吧 | `git-guardrails-claude-code` | [] | 外源 id |
| 341 | 直接按「P0 + P3 模板」开一版实现计划… | `builtin/riper-workflow` | [] | 计划请求，非显式 RIPER |
| 371 | 1.拉取最新代码编译替换 CMspark.app 2.多路对抗代码评审… | `builtin/deep-diagnosis-optimization` | [] | 混合意图（构建+评审） |
| 377 | 对话 #mhwofh 提示 400 tool_calls 错误 | `builtin/deep-diagnosis-optimization` | [] | 单错误调试 vs ddo 的批量诊断工作流；目录内无 debug skill |
| 385 | 现在更差了，再次弹窗说 CMspark.app 需要授权… | `builtin/deep-diagnosis-optimization` | [] | 同上 |
| 410 | 帮我 commit 并发起 PR | `mattpocock/review` | [] | 外源 id |
| 416 | 模拟点击全部失败 前台切换和截图正常… | `builtin/deep-diagnosis-optimization` | [] | 同 L377 |
| 426 | 模型文件缺失 Qwen3-VL…点击下载提示失败 | `diagnose` | 改 builtin/deep-diagnosis-optimization 或 [] | 真实诊断诉求；外源 id，目录内最近似为 ddo |
| 432 | 然后帮我合并到主分支吧 | `git-guardrails-claude-code` | [] | 外源 id |
| 444 | 走一遍 dual-review 对 diff 再 | `requesting-code-review` | []（或装 superpowers 保留） | 语义对（superpowers skill） |
| 450 | 先让 pi 和 claude 进行双路复审 | `omx/ask-claude` | [] | 双路复审 ≠ ask-claude 单点调用；omx 条件性安装 |
| 493 | 将所有未完成事项使用 workflow 合适方式进行收敛 | `builtin/riper-workflow` | [] | 泛 workflow |
| 505 | 可以的，来修复吧，另外，提示词也帮我优化下 | `builtin/deep-diagnosis-optimization` | [] | 续答+优化请求，弱信号 |
| 511 | 现在先让我们关注另外一个问题…无法截图查看… | `diagnose` | 改 ddo 或 [] | 真实诊断诉求，外源 id |
| 524 | Write ship note for P0 Anthropic protocol | `writing-shape` | [] | 语义尚可，外源 id |
| 542 | 单独 PR，没问题了帮我合并到 main 上面 | `git-guardrails-claude-code` | [] | 外源 id |
| 548 | You are an adversarial SKEPTIC…PERS-1… | `builtin/deep-diagnosis-optimization` | keep ddo 或 drop | 同 L3 |
| 587 | 当前是否还有代码没有提交的？ | `git-guardrails-claude-code` | [] | 外源 id |
| 605 | Deep-dive analysis of CMspark Computer Use failures macOS vs Windows… | `improve-codebase-architecture` | 改 builtin/deep-diagnosis-optimization | 深度根因分析契合 ddo『深度诊断』；现标外源 id |
| 655 | 插件操作外部程序时无法截图查看，设置里已授权，反复出现 | `diagnose` | 改 ddo 或 [] | 真实诊断诉求 |
| 665 | 继续按照之前的流程，把所有其他工作都完成 | `builtin/riper-workflow` | [] | 泛流程续作 |
| 704 | Verify UIUX node PR3 on CMspark. | `review` | [] | 裸 id，外源 |
| 710 | 根据评审意见，使用 workflow 进行完整优化…双路复审… | `builtin/deep-diagnosis-optimization` | keep ddo | 『完整优化』接近 ddo 触发词『优化项目』，但混有 workflow/复审 |
| 723 | …当前会话未挂载 cmspark MCP 工具…这是怎么回事呢？ | `diagnose` | 改 ddo 或 [] | 诊断提问，外源 id |
| 779 | 现在，我们项目暂时稳定，帮我更新下文档和版本号吧 | `builtin/session-end` | keep session-end | 收尾杂务，接近 wrap-up（handoff+commit），可辩护 |
| 809 | 使用合适的 workflow 在独立的 worktree 上进行开发吧…我去睡觉了… | `builtin/riper-workflow` | [] | 泛 workflow |

### LOW-VALUE（13 条，建议：除注明外 drop 或改 `[]` 作负例）

| 行 | query | 现标签 | 建议 | 说明 |
|---|---|---|---|---|

| 51 | 加吧 | `builtin/riper-workflow` | [] 或 drop | 纯续答 token，文本无路由信号 |
| 57 | B+C | `builtin/riper-workflow` | [] 或 drop | 选项答复，无信号 |
| 69 | 我用的是 dist-package 下面的 chrome-extension | `mattpocock/diagnose` | [] 或 drop | 陈述句，无请求 |
| 138 | 我看下恢复了 | `diagnose` | [] 或 drop | 残句，无信号 |
| 353 | reply with exactly: claude-ok | `ask-claude` | drop 或 [] | 连通性探针 |
| 398 | 开始 M1 | `builtin/riper-workflow` | [] 或 drop | 上下文 token |
| 518 | 1. 接受 C′ 2. D | `builtin/riper-workflow` | drop | 选项答复 |
| 530 | 1. 互斥 2. 不禁 evaluate 3. 并发最多到 5 吧… | `builtin/riper-workflow` | drop | 逐条答复 |
| 633 | 继续往后做吧 | `builtin/riper-workflow` | [] 或 drop | 续答 token |
| 761 | 继续 Phase2b 和 Phase3 | `builtin/riper-workflow` | [] 或 drop | 续作 token |
| 834 | 做 D1c | `builtin/riper-workflow` | [] 或 drop | 上下文 token |
| 846 | 继续 P2 抛光 | `builtin/riper-workflow` | [] 或 drop | 续作 token |
| 852 | [Image #1] | `[]` | 保留作负例 | 纯图片占位 |

---

*审计依据：`core/skills/*/SKILL.md`（builtin 目录与触发词）、`core/registry.yaml`（namespace/pack 清单）、`scripts/build_eval_from_logs.py`（弱标注生成逻辑）、`scripts/eval_routing.py` 与 `scripts/calibrate_index_threshold.py`（标签消费语义）、`src/vibesop/core/models.py` RoutingLayer。*
