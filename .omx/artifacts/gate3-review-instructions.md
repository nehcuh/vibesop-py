你是资深代码 reviewer,对 VibeSOP 路由系统 M3 做门禁 3 复审。用中文,只给判断和论据,不要客套,700 字内。

## M3 内容(四个子项)

1. **embedding 召回替换 KeywordMatcher 预筛**(triage_recall.py 新增 + triage_service.py 接入):LLM triage 的候选窗口改由 EmbeddingRecall(懒加载 sentence-transformers MiniLM-L12,候选 embedding 持久化 .vibe/skill_embeddings.json,content_hash 失效,任何失败返回 None 回退 KeywordMatcher 原路径)。metadata 标 recall_method。
2. **scenario 短路权威废除**(unified.py):early best-of 中 SCENARIO 胜出不再直接返回,存为 scenario_candidate 继续走 triage;triage 有效则用 triage,否则在 matcher pipeline 前回退 scenario(metadata scenario_fallback: true)。SEMANTIC_INDEX 短路行为不变。
3. **CJK bigram**(_layers.py _tokenize_query):连续 CJK 段取相邻两字 bigram,段长 1 保留单字。
4. **垃圾过滤**(unified.py route 入口):query 含 `<system-reminder` 直接返回 no-match,不写任何遥测。

## 已知声明(请裁决)

- M3a:模型加载失败在 CLI 每次进程重试(毫秒级);锁竞争时当次全量重编码;缓存无模型版本字段,换模型会静默回退 keyword。
- M3b:triage 失效时 scenario 误命中仍原样返回(与改动前错误率相同,只是不再挡 triage);垃圾过滤只挡 route() 入口,orchestrate() 路径绕过;bigram 后极短 CJK query 得分分布轻微上移,阈值未重新标定。

## 复审要求

1. 逐文件审:正确性、回退路径完备性(embedding 失败的每一层)、scenario 降级与 triage bypass/低置信的交互、bigram 边界(空段/混合文本)、垃圾过滤的返回形状与遥测跳过。
2. 专门攻击:embedding 回退 keyword 后 recall_method 标记是否真实;scenario_fallback 路径会不会把"短查询 triage 被 bypass"变成 scenario 实际仍恒胜,使权威废除落空。
3. 结论:PASS / PASS_WITH_NITS / BLOCK;BLOCK 列必修项。

## 复审包

