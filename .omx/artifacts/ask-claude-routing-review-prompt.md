# 复审请求:VibeSOP 路由系统重设计方案

你是一位资深分布式系统 + 开发者工具产品架构师。请对以下设计方案做**对抗性复审**:找出逻辑漏洞、被高估的收益、被低估的成本、实施顺序错误,以及我们集体盲区。不要客套,不要复述方案,只给判断和论据。用中文回答。

## 背景

VibeSOP 是 AI 编码助手的 skill 路由系统(Python,仓库 vibesop-py):用户说一句自然语言,`vibe route` 从 110+ 个 skill 中选出最合适的。生产部署案例是 cmspark(浏览器 agent),有 1897 条真实路由日志。

当前路由级联(unified.py `_try_layers`):
- Layer 0: EXPLICIT(@skill 语法)→ Layer 0.5: session-end 检测
- Step 1: 短查询走 SCENARIO + Semantic Index best-of;长查询只走 Index
- Step 2: AI_TRIAGE(LLM 语义层)
- Step 3: Matcher pipeline(keyword/tfidf/embedding/levenshtein 并行)

## 已核实的代码/数据事实(经 5 路 subagent 交叉验证)

1. Semantic Index 名为语义实为 Jaccard token 重叠;embedding 生成代码存在(indexer.py:394-427)但索引自 7-24 未重建,110 个 profile 0 embedding,`_try_embedding_fallback` 是死代码。
2. SCENARIO 层是纯关键词正则,命中固定 0.9 置信度,与 index(上限 ~0.65)best-of 时恒胜并短路,排在 LLM triage 前。但 cmspark 1903 条路由中 scenario 层只被访问 41 次(低频确定性错误源)。
3. `enable_embedding=false` 是安装默认,但只 gate matcher pipeline,不 gate 索引 embedding。
4. 短查询盲区:`keyword_match_max_chars=15` + `ai_triage_short_query_bypass_chars=15`;"提交代码"类查询完全由字面匹配决定。cmspark 真实 query 中 30% ≤15 字符。
5. unified.py:627 把 Semantic Index 命中记为 AI_TRIAGE 写入 routing_path,analytics 里 85.5% 的 "ai_triage" 高估 LLM 参与度。
6. cmspark:3047 次 LLM triage(deepseek-v4-flash),31 天共 $2.77,单次 $0.0009,input p50=538 tokens。端到端路由 p50=1000ms,p99=15.3s。
7. 熔断器(circuit_breaker.py)纯内存态,`vibe route` 是 CLI 每次新进程 → 熔断器恒 CLOSED,是死代码;延迟阈值 500ms vs 实测 p50 1000ms,校准脱节。
8. `user_satisfied` 1896/1897 为 None,`user_modified` 1903/1903 为 False——反馈回路完全缺失。eval 集仅 34 条手工标注。
9. 70% 流量是上游 agent 包的 `<user_query>` 转发,61 条 system-reminder 垃圾也进了路由。
10. 32 条 routing-errors 是 eval 脚本产物(非线上):fallback_llm 16、scenario 8、levenshtein 4、semantic_index 3。

## 待复审的设计方案

**核心主张**:级联是为省 $3/月设计的过早优化;真正缺陷是 (1) 无反馈回路,所有阈值(0.20/0.45/0.9/15字符/min_confidence=0.3)都是猜的;(2) 字面匹配层拥有不可否决的短路权威,架空了唯一的语义层。

**目标架构**:
```
EXPLICIT → session-end → 垃圾过滤
  → 快速放行:scenario 与 index 命中一致且具体 → 直接通过(零成本)
  → 不一致或无命中 → LLM triage 仲裁(默认路径)
  → 降级/离线:本地 embedding 召回 + margin 决策(AUTO/SUGGEST/弃权)
```
- scenario 删除短路权威(置信度 cap 或降为候选来源)
- embedding 定位为 triage 的召回器 + 离线备份,不与 LLM 平级竞争
- "不选 skill"是一等公民决策,fallback_llm 重分类为"主动弃权"
- 短查询用历史命中记忆(query→skill,从用户纠正学习)

**分阶段**:
- P0:修 627 mislabel;scenario 短路降级;eval 扩到 130+ 并做 CI 门禁;triage 日志补 latency/outcome。验收:mislabel 归零,eval top-1 +10pp。
- P1:熔断器持久化 + EMA + 按时因冷却;短查询按词数计量 + 历史记忆层;cmspark 埋 👍/👎 反馈。验收:离线 p99 <200ms,反馈非空率 >30%。
- P2:重建索引生成真 embedding 做召回;阈值用 eval 标定。验收:recall@3 +5pp,p99 不劣化。

## 复审要求

1. 这个"LLM-first"方向本身对吗?有没有我们没考虑的第三种架构?
2. P0/P1/P2 的顺序和验收指标有没有问题?
3. 哪些"已核实事实"其实支撑不了我们赋予它的结论?
4. 最大的实施风险和被低估的成本是什么?
5. 如果你只能保留方案里的一件事、砍掉一件事,各是什么?
