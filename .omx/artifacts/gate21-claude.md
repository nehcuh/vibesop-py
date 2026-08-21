# gate21 复审结论

**verdict: PASS_WITH_NITS**(无 BLOCK)

证据基础:`[executed]` 115 tests passed(4 个受影响测试文件)、ruff 全过;其余为 `[inspected]` 逐行核对(skill_promote.py / clustering.py / skill_commands.py / recall.py)。

## F-a 语义正确性 — 通过

- **分类计数/准入**:`_do_locked_upsert`(skill_promote.py:513-555)按 `is_unstable == candidate.is_unstable` 过滤同类、同类内比较(unstable 比 span_count、stable 比 gold_rate),逻辑完备。`min()` 无空序列风险(`class_rows ≥ cap ≥ 1`)。
- **组合覆盖**:stable 满拒新(test_skill_promote_store.py:199)、stable 满驱逐同类最低(164)、unstable 满驱逐 span_count 最低且不碰 stable(242)、unstable 满不堵 miss 准入(store 级 285 + scan 级 test_miss_recurrence_admission.py:339)——“stable 满 + unstable 未满”与反向组合均有测试锁定。
- **legacy 文件**:`from_dict` 走 dataclass 默认 `is_unstable=False` → 归 stable,test_legacy_rows_without_class_fields_load_as_stable(test_skill_promote_store.py:321)锁住。真实 dogfood 池的行自 M12 M2 起就带该键,分类正确。
- **gate17b 保护**:同 cluster_id gold-pending 行防覆盖逻辑在 scan_candidates:1297-1308,本次未触碰,TestGoldPendingCollision 通过。
- **unstable 按 span_count 驱逐**:与准入比较指标一致(证据量=诊断价值),并列 FIFO 与 stable 类对齐,合理。
- **口径**:`capped` 语义收窄为 stable 类(skill_promote.py:1256 用 stable-only `pending_count()`),docstring、CLI、不稳定桶独立行(skill_commands.py:1476-1481)三处一致;与双锁/坏行跳过/原子重写的防御式风格对齐。

## F-b 安全性 — 通过

- **误判面**:仅整串 JSON 数组且每块严格 `{"type":"text","text":str}` 才拆(clustering.py:371-395);用户真贴 JSON 数组当 query 时，text 字段即语义主体，拆出反而正确聚类；task_id 由 producer 在写侧派生，读取侧解包不影响身份。单块 `[{"type":"text","text":…}]` 正是 kimi/grok producer 形状，是本库常见合法输入。
- **顺序**：信封优先、信封内容不解二遍(单遍，测试 test_clustering.py:498 锁定)；畸形/非 text/混合/内嵌放行均有测试。
- **附带修复**:`[{"type":"text","text":"继续"}]` 这类包裹退化 query 此前能绕过 `_is_low_information_query` 精确匹配，F-b 后先拆再过滤(scan_candidates:1143),堵了一个过滤器旁路。
- **空文本块**:`""` 拆出为 falsy,cluster_queries:272 `if query:` 跳过、miss 过滤按空串拦下，边界安全。

## Findings

**BLOCK**:无。

**NIT**:

1. **skill_promote.py:1247-1255** — `unstable_refused_count` 的递增路径(桶满 + 弱 unstable 候选 → count≥1)无任何测试驱动，现有测试只断言 `== 0`。建议补一条 scan 级用例，否则该计数器的行为只靠 WARNING 日志间接保证。
2. **recall.py:403-404** — 本地拷贝的注释 "Same shape as clustering._extract_query" 进一步失真：F-b 后 clustering 有信封+content-block 两层解包，recall 连 metadata 回退都没有(分歧先于本次存在，本次扩大)。行为无回归，但建议改注释或抽公共 helper,否则下一个改 clustering 的人还会漏同步。
3. **skill_commands.py:1498-1500** — `pending_count(include_unstable=True) - pending_count()` 是两次无锁读相减，并发写者介入时理论上渲染出负数 unstable 计数。纯展示、概率极低，可不修。
4. **skill_promote.py:507-511** — refresh 路径整行替换(含 `is_unstable`),cluster 的 gold_rate 跨扫描漂移导致类翻转时可绕过插入时 cap 检查使某类超预算(cap 仅插入时强制)。罕见、有界、仅诊断桶，记录即可。

## Residual risks

1. **存量池不自愈**：真实 dogfood 池的 50 条 unstable 行部署后维持 50 条直至 TTL(30 天)或人工 dismiss;不影响 M2 出口(miss 走 stable 类，当前 stable 计数为 0),但 CLI 会显示 "50 unstable (cap 20)" 数周。
2. **stable 池被 prior miss 行占满仍拒新 miss**:同类 gold_rate=0.0 <= 0.0 恒拒，由 `miss_rejected_count` + WARNING 呈现——文档化残余，非回归。
3. **信封内嵌数组不解二遍**：若未来某 producer 既包 `<user_query>` 又包 content-block 数组，该形状仍带 JSON;当前无此 producer。
4. **旧候选行 queries 字段**仍存 F-b 前的 JSON 包裹文本，直至该 cluster 被 rescan refresh;仅展示层。
