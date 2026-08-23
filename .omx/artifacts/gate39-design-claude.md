核查完毕。以下为评审结论。

## Verdict
PASS_WITH_NITS

## Findings

- [MAJOR] 主项脚注“与 Fire 30d 列总体不相交”是事实错误。fire 列（skill_health.py:50-57）明文计入 CLI 命中（"CLI-path hits count too"），hit outcomes 仅 hook 命中——两总体是**子集关系**（30d 窗口内重叠非空），不是不相交。gate38 原文（tool_call_bridge.py:63-67）写的是 "The populations differ in coverage"，综合稿 §1.2 错抄成“不相交”。防误读纪律里放一个可被轻易证伪的陈述（reask 列数字 ≤ fire 列即可反证），会连累整段警示的可信度。改为“fire 含 CLI、outcomes 仅 hook，口径不同，禁止拼比率”。
- [MAJOR] join 落空“跳过不计”无任何可见性要求。当前高命中是**按构造**成立（outcome 行 span_id 源自同一 append-only spans.jsonl 的加载扫描，tool_call_bridge.py:230/:523），但本稿 §4 记档 3 自认 spans.jsonl 无轮转无界增长——一旦 gate40 做轮转，历史 outcome 行 span_id 将系统性落空，outcomes 表静默缩水成“看起来没数据”，且与“最近活动”语义无法区分。要求：输出带 unjoined 原始计数（是计数不是比率，不违 raw-count 纪律），测试覆盖混合 fixture（部分 join 失败）且断言 unjoined 计数可见——设计只测了“跳过”行为，没测“落空可察觉”。
- [MAJOR] RetentionPolicy 删除的引用清单不完备。除三处代码引用（candidate_manager.py:265 ✓、feedback_loop.py:122 ✓、evaluator.py:86 ✓）外，GOALS.md:48/:105 仍把 RetentionPolicy 当活功能宣传（“按时效/使用频率排序”），docs/architecture/skill-runtime-interface.md:265 更给出 "Trigger `RetentionPolicy.analyze_all()` weekly" 的运维建议、:341 架构表行在列。§3 有“全仓 grep 含 docs 兜底”条款，但 §5 文档同步清单只列 CLI_REFERENCE/CHANGELOG——按 gate38 §4 自己树立的“文档不许撒谎”纪律（当时专门清了 GOALS/ARCHITECTURE 的过时宣传），这四处应点名进删除 commit 的文档清单，不能只靠实施时 grep 兜底。
- [NIT] last_outcome_at 未钉数据源。回灌行的 recorded_at 全是回灌当天（gate38 §1.2），当“最近活动”展示即撒谎；必须钉 outcome 行的 span_ts（缺失则该字段空），否则首版表格在 cmspark 这类回灌主导的项目里全部显示同一天。同理排序未定义（建议 total 降序或 skill_id 字典序钉死，测试可复现）；--json 行为未声明（若提供，schema 必须 raw counts only，与 must-NOT 测试同口径）。
- [NIT] span_id→skill_id 映射构建细节缺失：(a) SpanWriter 将 metadata 序列化为 JSON 字符串（span_writer.py:97-100），join 侧必须镜像 `_route_hit_skill_id`（skill_health.py:68-75）的 str→json.loads 容错，照字面 `span["metadata"]["skill_id"]` 会全量漏 join；(b) 映射应只收 route hit span。建议直接复用 `_route_hit_skill_id` 谓词而非新写解析。
- [NIT] reask 低估未披露。task_id 是 query 全文派生（同任务改述即换 task_id），reask 是下界计数——“reask 少”不等于“没重问”。防“reask 多=技能差”误读的脚注应补一句三列均为下界的说明。
- [NIT] 搭车项 A 只镜像 SPANS_FILENAME，OUTCOMES_FILENAME（tool_call_bridge.py:129）无 dev 变体：dev 语境下派生的 outcome 行与 prod 行混写同一文件，skill_outcomes 读侧 spans 走 dev 文件、outcomes 走共享文件，跨侧行落空被静默跳过（与 unjoined 发现叠加）。skill_health 的 execution_feedback.jsonl 有同样不对称（先例），首版可接受，但应在设计里记一句已知不对称，防 gate40+ 误当 bug 修。
- [NIT] cmspark 实测数字（3068/2437/1268/1167/2、join 2437/2437）未独立复核——跨项目读取被权限拦截 [assumed]。内部自洽（1268/2437=52.0% ✓）；join 高命中有上述结构性论证支撑，且设计成立性不依赖该数字（skip 规则兜底）。建议实施时在验收输出里留一次实测计数快照。

核查通过的关键证据（抽查 20+ 处，摘录）：promote_verifier.py:11-15 verdict=触发召回非内容质量 ✓；backfill 砍除理由 (b) 的 RULESET_VERSION 第二总体论证与 promote_verifier.py:50-53 schema 相符 ✓；性能记档更正成立（每 run 实际是 new_hits×spans 线性，“平方”仅首跑回灌一次性）✓；薄样本推迟的“F 规则唯一燃料”属实（feedback_loop.py:60 F_MIN_ROUTES=3 + :143-148，gate38 后 total_routes=0→"?"，F∧<3 仅剩 1≤total_routes<3 可燃）✓；bridge fixture churn 属实且改造成本低估得保守——硬编码集中于单一 helper（test_tool_call_bridge.py:32-33/:72），实改一处即可 ✓；dashboard 五处硬编码 :137/:195/:296/:330/:344 精确 ✓；evaluator 三读 :172/:204/:205 ✓；`vibe skills health`=pack 完整性（_health.py:75-81）、`vibe skill` 单数组装载于 subcommands/\_\_init\_\_.py:84-86，命名无冲突 ✓；gate38 §5 六项记档全部有对应处置（做/推迟/砍+永久否决），偏离合理 ✓。主项非换皮：gate37 §4 不做清单禁的是比率/记分卡/衰减列，outcomes 是 raw counts 可视化，零写路径 ✓。CLI 形态（独立子命令 vs list 加列）在评审层定死恰当：list 表已 8 列 3 脚注且行集不同域（安装技能 vs 有 outcome 技能），维持独立子命令。
