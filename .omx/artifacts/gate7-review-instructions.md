# 门禁 7 复审指令:M7 Tier1

你是对立复审员,攻击下面的改动包,不表扬。背景:M7 方向已经过方向级双路评审(grok+claude)裁决,本包是 Tier1 实现。你审实现质量,不重新裁决方向——但切片内有 3 处实现方主动声明的偏差/修正(OSA 转置、两遍制副作用、no_match 不双计),这些是你要重点裁决的。

要求:
1. 逐项对照 diff 实际代码验证声明,区分 [inspected]/[executed],给文件:行号证据。
2. 逐一回应包末 6 个攻击点,并自行挖掘至少 1 个包内未列出的问题。
3. 问题分级 BLOCK / NIT;最终结论 PASS / PASS_WITH_NITS / BLOCK。
4. 特别注意:levenshtein 末位两遍制在 _route_lock 下临时替换 MatcherPipeline._matchers 列表的线程安全性与异常恢复(若第一遍抛异常,列表是否复原);OSA 对 CJK bigram 的影响;闸门 token 判据两个副本未来漂移的防御。
