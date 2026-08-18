# 门禁 7 复审报告：M7 Tier1

**结论:PASS_WITH_NITS**(0 BLOCK / 8 NIT,其中 2 个强烈建议合入前顺手修)

验证基础：切片相关 7 个测试文件 193 passed [executed];全量 `-m "not benchmark and not slow"` **5440 passed, 14 skipped** [executed](注：与包内"1775 passed, 2 skipped"口径不符，树是绿的但数字来源需澄清)；OSA/正则/闸门另做 3 组活性探针 [executed];replay“11 条决策不变”未独立复跑，记 [assumed]。

---

## 一、声明逐项核验

| 声明 | 证据 | 判定 |
|---|---|---|
| A1 分母修复 | strategies.py:527-549,未过 0.7 的 meaningful token 记 0 入分母；约定与 KeywordMatcher:140-145 逐字一致 [inspected];test_strategies.py:357-389 [executed] | ✓ |
| A2 OSA 偏差 | strategies.py:586-626;探针 [executed]:`reivew/review=1`、`ab/ba=1`、`abcd/badc=2`(非相邻交换不误降)、`kitten/sitting=3`——是**标准 OSA**,无三角违规 | ✓ 接受(见攻击点1) |
| A3 两遍制 | unified.py:738-777;`_pipeline.run_matcher_pipeline` → `router._matcher_pipeline.try_matcher_pipeline`(_pipeline.py:29)——换列表的对象与执行对象同一，机制成立 [inspected];19 tests [executed] | ✓ 但副作用声明措辞有误(NIT-3) |
| A4 slash 前置未改 | explicit_layer.py:40-55 原样 [inspected];6 个 slash 测试 [executed] | ✓ |
| A5 unwrap | unified.py:104-110、1009-1013,位于 junk 守卫(:1007)后、匹配前 [inspected];探针：全包裹解包、部分包裹不动 [executed] | ✓(病态边界见 NIT-4) |
| B1 闸门 | routing_pending.py:70-90;`tokenize` 复用，判据本地复制 [inspected];探针 [executed]:可以/✓//review 拦，review my code 等放行 | ✓ 但有边界误伤(NIT-2) |
| B2 no_match 不双计 | unified.py:1023-1027 同一事件先 `_record_route_miss`(:1153-1160,iff `not has_match`)后 enqueue;`should_enqueue_from_route`(routing_pending.py:498-499)iff `not has_match`→`"no_match"`——**两判据严格同构**;`try_enqueue` 生产调用方全仓仅 unified.py:1208 [executed grep] | ✓ 完备 |
| B3 去重/配额 | routing_pending.py:209-233(按 distinct hash 计)、340-352(hash-only 去重，空 hash 回落) [inspected];tests [executed] | ✓ |
| B4 文件锁 | routing_pending.py:298-320、405-436;锁内 `_load()` 重读(:165-181 整表替换)→合并→原子写;`CouldNotLock`⊂`OSError`(file_lock.py:40)与捕获兼容；threading→file 顺序两处一致 [inspected];跨实例并发测试 [executed] | ✓ |
| C 拆 boost | instinct_cmd.py:809-883:分支/参数/输出全拆，early-stop 双端保留(:853),watermark 仅 decayed 时保存(:867-874);`boost_threshold` 全仓 0 命中 [executed grep];`RoutingMetadata.boosted` 是 preference_boost 的无关字段 | ✓ |
| D1 增量索引 | 私有方法签名全部真实匹配:`_analyze_skill(loaded, llm)`(indexer.py:451)、`_compute_embeddings` **原位写** `profiles[skill_id].embedding`(:421-425,落盘含 embedding)、`_save_index(profiles, scope)`(:505-506)、`_load_single_index`(:541)、路径属性(:132-140)、构造器(:118-129);`SkillLoader.get_skill` 真实存在(loader.py:244)、`create_provider(provider, api_key, base_url)` 参数名匹配(factory.py:34-38)、`logger` 存在(skill_commands.py:35) | ✓ 但有 NIT-1 |
| D2/D3/D4 | draft 名/净化/promote 文案 tests [executed] | ✓ |

## 二、六个攻击点回应

**1. OSA 转置——接受。** 新误匹配面精确刻画 [executed]:相邻转置使 ≥4 字符词对入场(`form/from`=0.75、`causal/casual`=0.833、CJK 4 字"蜜蜂养殖/蜂蜜养殖"=0.75);2-3 字符词对仍低于 0.7(CJK 2 字转置“蜜蜂/蜂蜜”=0.5 被拦)，恰好保护了汉语里语义翻转最高的双字转置类。兜底：levenshtein 已降为末位，首遍有果时根本不参与聚合，误匹配只在 keyword/tfidf/embedding 全空的查询上才可能落地。NIT-5:包内"OSA 后 0.917"实为查询级均值 (0.833+1.0)/2,token 级是 0.833——数字张冠李戴，结论不受影响。

**2. 两遍制——异常恢复 ✓,并发有一处真实缺口。** 第一遍抛异常时 `finally` 复原列表(unified.py:771-772) [inspected];`_route_lock` 全仓无其他持有者(仅 ：325 定义 + :765 使用)，**无重入死锁** [executed grep]。但 **pass 2(unified.py:775-777)不在锁内**：它经 `_pipeline`→`router._matcher_pipeline`(:29)读的是**活的** `_matchers` 属性，若另一线程正在 pass 1(列表已被换成 calibrated),本线程的“全量”第二遍静默缺少 levenshtein→瞬时 no_match。失败模式是降级不是损坏、`vibe route` hook 是进程级无共享实例，故定 NIT;修法便宜：pass 2 同样进锁，或给 `try_matcher_pipeline` 加 matchers 覆盖参数(免共享状态可变)。性能：首遍 miss 时全 matcher 含 embedding query encode 跑两遍;`_finalize_no_match` silent 模式的第三次全跑(unified.py:931)是先于本切片的既有行为。**副作用声明写反了**:第二遍是全量管线，levenshtein 结果恰恰**是**与其他 matcher 结果一起进 `apply_optimizations`(matcher_pipeline.py:133);真正的语境收窄发生在**第一遍**(有果时 levenshtein 不进 merged_matches)。行为符合意图，声明文字错位——NIT-3,改注释即可。

**3. no_match 协同——完备。** 判据同构 + 唯一生产调用方 + `record_telemetry=False` 路径两写同skip(unified.py:1023-1027)+ orchestrate 路径两写皆不经过。`_WEAK_MATCH_LAYERS` 高置信弱层命中→`low_confidence`→闸门补记，与 router(has_match=true 不记)不重叠 ✓。一处注脚：闸门补记的是 redact 后 query,router 记原 query——不同事件不构成双计，仅 redaction 改写且两次路由结局不同时会产生两个 cluster,可忽略。

**4. token 判据漂移——零防御，NIT-6。** 判据现存**三副本**(strategies.py:140-145、:534-540、routing_pending.py:53-58),无任何契约测试钉住。“闭包不可导入”理由成立但结论不必是复制：提为 strategies.py 模块级函数 + 一行 import 即可；不愿跨模块依赖就加契约测试断言三处对固定语料一致。二选一，现在是裸奔。

**5. 私有 API 脆弱性——可接受，已声明。** 签名当前全匹配 [inspected];整段 try/except 降级不会砸 install;真实损坏路径退化为 False + 黄字提示。比签名漂移更要紧的是 **NIT-1(见下)**。

**6. decay 注释——准确** [inspected]:“iterate ALL instincts + early-stop 双端”与 instinct_cmd.py:843-853 实现一致；watermark 语义与改前等价(boost 死后 `if decayed` 与 `if decayed or boosted` 恒同)。

## 三、自行挖掘的问题(包外)

- **NIT-1(本包最重)：增量索引 RMW 无跨进程锁。** `_index_newly_added_skill` 对 index 文件做 load→merge→save(skill_commands.py:1086-1090),无 `cross_process_lock`。并发 `skill add`×2 或 add×`skills index` → 后写者覆盖，**静默丢条目**——与切片 B 在同一改动包内为同型 RMW 刚建立了锁标准，双标。同型问题在 W5.2 曾被评审定为 CRITICAL。因失败可自愈(下次全量 index 修复)且全量 build 本就无锁(非本切片引入的类)，定 NIT 而非 BLOCK,但强烈建议合入前补 sidecar 锁。
- **NIT-2:闸门误伤真实短意图** [executed]:"调试"、"修 bug"(1 个 meaningful token)被拦出人工审核队列；反向“帮我看下”(纯寒暄)因 CJK bigram 数量放行。幸而 no_match 仍进 MissCounter,频繁信号不灭，丢的只是人审入口。这是“计数启发式”的固有边界，需在文档点名并留校准余地。
- **NIT-7:数字声明口径不明。** 包称 1775 passed / 2 skipped,实测全量 5440 / 14 [executed];replay 结论未独立复跑 [assumed]。
- **NIT-4:unwrap 病态输入** [executed]:`<user_query>fix</user_query> mid </user_query>` → `fix</user_query> mid`,违背“仅全包裹才解包”的字面声明；现实不可达，记录在案。

## 四、裁决

三处主动声明:OSA 转置(**接受**，风险面已量化且被末位两遍制兜底)、两遍制副作用(**机制成立但声明写反了 pass**,NIT-3)、no_match 不双计(**协同完备**，判据同构验证)。无 BLOCK 项：所有缺口的失败模式均为降级/瞬态/可自愈，正确路径与测试全绿。**PASS_WITH_NITS**——NIT-1(索引锁)与 pass-2 竞态建议顺手修，其余按队列处理。
