# 优化方向评审包:oneshot-web-spec 经验整合(M7 方向裁决)

## 背景

外部技能 oneshot-web-spec(~/.cmspark-agent/skills/)验证了"验收前置/反模式/数值化/拒软措辞"四原则。外部评审(deepseek)指出 vibesop 的 skill promote 草稿违背这些原则,并提出 F1-F9 修复清单。我提出 P0(装技能进池)/P1(修 description+模板占位节+消毒+稳健性)/P2 暂缓(query 侧低信息密度检测)。随后 4 路独立对抗评估(plan agent,只读)完成,证据与分歧如下,请裁决最终优化方向。

## 四路评估的关键事实(全部有代码/数据证据)

### 推翻或修正 deepseek 的事实
- F1(zip strict, gold_detection.py:75):生产不可达——task_ids/queries 同源投影恒等长(clustering.py:328-331)。4 行防御可做可不做。
- F2(assert, skill_promote.py:798):属实但低危。一路认为 assert 是刻意 fail-loud(注释明说抓手工 fixture),改静默容错是反设计;另一路指出项目有把 python -O 当真威胁的先例(dashboard/server.py:477-482 已改过同类),建议显式守卫+跳过。
- F3(description 噪音):属实但定性被修正——description 在 keyword/TF-IDF/embedding 各层是**中性稀释**而非有害吸引;真正的匹配磁铁是 name=原始 query 截断(strategies.py:160-174,substring bonus +0.25、互含 bonus +0.4)和 When-to-Apply 节的真实 query(会被 LLM indexer 提炼成强 profile)。空壳内容+强匹配 profile="糖衣炮弹"。
- F6(query 未消毒):span 落盘前已 redact_sensitive,frontmatter 已消毒;真实缺口仅 queries_block 原文多行 query 会渲烂 markdown 结构并可藏伪指令块。修复=单行折叠+截断 200。
- deepseek 编造的:algorithms/interview/compute_ambiguity.py 不存在;F10 基于旧快照。

### 四路一致同意做
1. F3 description 改为从代表性 query 派生(选项:前两条不同 query 拼接截断 140;留空违反 spec v3 必填)
2. F5 routing_pending.py 补 cross_process_lock(兄弟存储全有;unified.py:1139 每路由新建实例读-改-全量重写,并发丢更新;日上限 3 条故后果轻微)
3. F6 queries_block 折叠+截断
4. P0 装 oneshot-web-spec 进池——但注意:~/.cmspark-agent/skills 不在任何发现路径(candidate_manager.py:234-248),需 copy+重建索引;且应用 scripts/eval_routing.py 对真实 query 做 before/after 验证是否抢流量,不盲装

### 分歧点 1:F4-lite 模板占位节——做还是砍?
- 砍方:spans 里不存在推导"验收条款/反模式"的信号,前置验收嫁接到事后归纳是范畴错误;.vibe/observability/ 在本项目不存在,promote 从未产出真实草稿,加结构违反"无投机通用性";现有 "(no core steps identified)" 已是有数据源仍退化的先例。
- 做方:人审成本与决策粒度成正比,当前草稿等于让人从零创作(50 倍于 instinct accept/dismiss 的成本),占位节把创作降为填空;但剂量控制在 5-8 行。
- 折中设计(评估3):不加领域占位节,加 "## Review Checklist (delete before activating)" 节,条目引用草稿具体数据(改写 name/description、确认 queries 是单一工作流、把 span 埋点名改写成指令步骤、填空"何时不该用本技能:____"),填空横线比占位段落更难橡皮图章。

### 分歧点 2:P2(query 侧低信息密度检测)——暂缓、砍掉、还是变形为本轮主线?
- 变形方(证据最强):.vibe/instincts/routing_pending.jsonl 全量 7 行逐条读完,7/7 垃圾("可以"/"/review"/"使用 review"/"/debug"/"review my code"x2/"route my query"),全部 levenshtein@1.0 或 no-match 入队,0 accept/0 dismiss——评审队列死于告警疲劳。memory/project-knowledge.md:201 早记录"nonsense queries still matched via LEVENSHTEIN conf≈0.9-1.0",当时修法(_WEAK_MATCH_LAYERS)只标记没修路由。正确修法在 matcher 侧:LevenshteinMatcher 对短/低信息 query 加门限,错误路由和队列噪音一起消失。
- 砍方:人审闸门已存在,机器打分是重复判断。
- 注意:门限设计需谨慎——不能误杀合法短 query(如真实短指令)。

### 新发现(评估4,不在原提案)
- **feedback-collect 自动 boost**(instinct_cmd.py:874-883):success_rate≥0.8 且应用≤2 的 instinct 自动 record_outcome(success=True)——无新信息自增强,把 gold_rate 推向 promote 阈值。评估4 评为全链路最高性价比干预:success_count 只应来自显式人确认。
- **vibe skill add 不重建语义索引**(Phase 6 只冒烟测试):新注入技能在 SEMANTIC_INDEX 层不可见直到手动 vibe skills index——激活断点,promote 成功文案也没提示。
- **triage_recall 无相似度阈值**(triage_recall.py:177-188):壳技能文本永不为空→必进 triage 窗口;加最低余弦阈值是最便宜加固。
- **疑似 global 安装路径不在发现路径**(skill_installer.py:59/93 → ~/.vibe/.vibe/skills/,CandidateManager 搜索路径无此项)——需先验证。
- **auto-config.yaml 被当技能进了索引**(.vibe/skill-index.json 实证)——发现路径污染先例。
- **当前暴露面为零**:无 auto-draft 产物在路由,gold 信号池为空(instincts.jsonl 9 条 success_count 全 0),负循环第一圈转不起来。

### 我的综合方向(待裁决)
- Tier1:levenshtein 低信息门限(P2 变形)、F3、F6、F5、feedback-boost 拆除、promote 文案补"重建索引+3行人审checklist"
- Tier2:Review Checklist 节(折中设计)、F2 显式守卫、triage_recall 最低余弦阈值
- Tier3:验证 global 路径问题、P0 装池+before/after eval、auto-config.yaml 污染
- 砍:F1、完整占位节、P2 原案(query 侧规则进 pending)、索引层过滤、skill-craft profile 机制

## 请裁决的问题
1. 分歧点 1:Review Checklist 节(折中设计)是否通过了"僵尸结构"反驳?还是仍应砍?
2. 分歧点 2:levenshtein 门限作为本轮主线是否成立?门限形态的建议(最小字符/token?置信度 cap?)及误杀风险如何控制?
3. feedback-collect 自动 boost:拆除还是改形(只调 confidence 不加 success_count)?
4. Tier 划分是否合理?有没有被高估/低估的项?
5. 三路未覆盖的盲区。
