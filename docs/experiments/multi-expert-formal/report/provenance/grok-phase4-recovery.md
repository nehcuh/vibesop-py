发生实际执行层中断，继续完成，不再从头检查/重构。原144来源是同一目录 docs/experiments/multi-expert-sensitivity/runs/20260913T033401Z。

证据：/Users/huchen/Projects/vibesop-py/.experiment/grok-phase4.stderr 在2026-09-13T03:46:53记录 `headless: background wait timed out, exiting timeout_secs=600` 和 `killing background work still pending`。123已terminal、8状态running但进程已被Grok工具终止、13未开始。监督已确认ps无runner。见 /Users/huchen/Projects/vibesop-py/.experiment/sensitivity-infrastructure-interruption.json。不是DeepSeek API失败，不是模型能力失败。

立即执行既有恢复协议：先保留8个result.json原始running快照（另文件/审计归档，不覆写原始请求响应），然后用原未变冻结runner --phase sensitivity --resume 原run_root --max-new 144。它会将8个孤立running标interrupted并只选13个未开始项，不重跑任何已启动分配。不要改冻结源码/预算/任务/统计。之前123个终态完整留存。不得重开cohort或偷偷补8个以变好分数。

这次务必用明确的get_command_or_subagent_output阻塞等待，每次<=60秒，在本轮内持续取回原runner输出直到COMPLETE和144terminal。不要发一句‘等它完成’就结束headless回合；那会进入600秒后台退出清理。剩余13预计不长。不要再启用只会打印状态却不能完成报告的watcher来代替真实等待。

完成后继续上一阶段的完整报告工作。但必须纠正中断计量：这些running初始result.json没有最终ledger，不能在report当成实际用量0，也不能宣称全部调用都有response。保持raw结果；从已持久化response.usage和tools.jsonl派生独立的interruption-audit/derived-usage文件，标记这是已知用量下界。7个或实际数目的未返回HTTP响应可能已收费，使用量未知，不能编造为0。逐个核对，不假设全部8都缺最后response；可能有response已保存但尚未来得及更新result。报告全量对账应列预期缺失和未知量，不能伪造144/144日志完美。

按冻结方案，interrupted在敏感性主表仍计0，分母144；单独分解过程失效与模型失效。额外给中断结果未知时 D_soft-A点估计的最坏/最好界限（把中断D成功/A失败作为有利极端，反向为不利极端），清楚标注是事故后的不确定性分析，不能替代预固定统计。中断不随机，别拿complete-case率声称无偏。不要把Grok控制器终止的7个D_soft/1个A或实测组别数当成该编排自身能力缺陷。

完成主360+敏感性144的两份中文报告、图表与审计，保留主结论边界与阶段机制解释，提交实验branch后结束本轮。无需再增加任何实验。主目录文档交付下一步由监督确认，不merge/push。
