完成最后交付，不再增加任何模型实验。主360应全部完成；敏感性144应已按固定协议结算（其中8次被Grok headless600秒后台清理中断，不冒充完成）。

先读 /Users/huchen/Projects/vibesop-py/.experiment/final-editorial-review.md 的具体审阅意见并逐条落实。再读取 /Users/huchen/Projects/vibesop-py/.experiment/ 下 supervisor-final-*.json、sensitivity-start-audit.json、sensitivity-guard-audit.json 和 phase4-supervision-notes.md；与最终报告核对。仅修报告/展示/归档问题，不改已冻结实验源或原始结果。

只做交付收尾：不要重新全面阅读执行器、遍历打印海量runs目录树、重新校准或重跑模型。用manifest/已有audit定位必要案例；已通过且未变的gold/运行测试不重复。

交付要求：
1. 主 REPORT.md 是中文、可独立阅读的完整报告。开头清楚呈现两轮分别的结果、阶段终止机制、局限与可执行建议。严格区分原360的预固定主分析和受诊断启发的探索性144；D_soft必须对同批A。不把区间跨阈值说成无效，不把小样本任务/规格的天花板效应包装成普遍能力判断。费用注明仅参与模型推理估算，不是含Grok/Codex/计算/人力的总成本。
2. 至少两个合适Mermaid图：五组流程概览、硬阶段终止与soft_continue差异（2400内部额度未增加、全局与final仍硬限制）。嵌入关键PNG/SVG图而不只是‘图见目录’。至少覆盖真实中止/所有权案例及新D_soft从soft_close到产物/验收的轨迹，链接实际记录。若没有代码隐验反例，明确没有，不造例子。所有图中文可读、图例不挡数据；按需修展示层后重画。
3. 将必要过程记录归档到 docs/experiments/multi-expert-formal/report/provenance/：外部supervision.md、results.tsv、beliefs.md、sensitivity-decision.md、supervisor-progress.jsonl、独立audit JSON、supervisor_audit.py，以及grok-phase1/grok-correction1/grok-phase2-start/grok-phase3-complete/grok-phase4-sensitivity任务指令md。写PROCESS.md串起准备、校准75、原360、纠偏和补充144。无需复制Grok streaming thought日志，保留其本机路径索引即可。不要复制任何凭据。
4. 更新非冻结的顶层执行索引和 multi-expert-e2e-protocol.md 状态，注明这是原始设计与执行后的差异；不可改冻结prereg/源码。修复Markdown相对链接（包括run目录REPORT副本与主报告目录不同导致路径错误的问题）。记录最后验证结果。
5. 最后将两个完整新实验目录复制到主项目 /Users/huchen/Projects/vibesop-py/docs/experiments/ 下同名目录，使用户无需进入隐藏worktree就能读报告和日志。当前应不存在；先检查，如已有不同内容则先比对，不能覆盖无关用户修改。复制排除__pycache__/.pyc，不删除任何主项目现有文件；同步此次维护的协议/执行索引即可。此次明确授权主项目文档交付，覆盖早期‘主目录只写metadata’的阶段限制。生产src/core/tests仍不动，不merge、不push。复制前提交实验branch，复制后核对两个目录文件hash一致（排除缓存）。

完成后返回：两个报告绝对路径、主结论与完整样本数、最终审计、commit、主目录交付核验。若任何报告描述与数据不符，修正报告；不要以修改数据解决。完成后结束本轮headless。

补充中断事件必须纳入正文、表格和过程档案：144分配=136执行完+8中断（最终核对），8按预定规则计0但不是模型能力失败。7或实测未返回HTTP的用量/账单未知，派生统计是已保存用量下界，不可声称全部请求响应完整；单独给未知中断结局的D_soft-A点估计最坏/最好界限，不代替预定CI。归档 sensitivity-infrastructure-interruption.json 与grok-phase4-recovery.md，并索引stderr中03:46:53的超时证据。不要追加或重跑样本来掩盖事故。
