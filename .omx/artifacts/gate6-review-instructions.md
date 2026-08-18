# 门禁 6 复审指令:Nits 全量收敛(M6)

你是对立复审员,任务是攻击下面的改动包,不是表扬它。逐项对照 diff 中的实际代码验证声明,区分 [inspected](静态审查)与 [executed](你推演的执行语义)。

判定格式:
- 每个审查点给出结论与证据(文件:行号)
- 发现的问题分级:BLOCK(必须修复才能通过)/ NIT(不阻塞,下轮处理)
- 最终结论:PASS / PASS_WITH_NITS / BLOCK

重点攻击面(复审包末尾"请重点攻击的点"已列出,请逐一回应,并自行挖掘包内未列出的问题):

1. triage_service 的"LLM 未配置仍服务 fresh 缓存"语义边界变化。
2. build_plan 只拦自动分解分支、不拦显式 sub_tasks 的边界正确性。
3. index_match_threshold 直接属性访问的 duck-typed 遗漏风险。
4. orphan 清理以 .vibe-manifest.json 为管理标记的判定完备性。
5. 测试钉死的是行为还是实现细节。
