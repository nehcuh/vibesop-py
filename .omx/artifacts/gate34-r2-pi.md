Usage: vibe route [OPTIONS] {query}
Try 'vibe route --help' for help.
╭─ Error ──────────────────────────────────────────────────────────────────────╮
│ Got unexpected extra argument(s) (prompt 回声是合法池成员，bd1bc217          │
│ 就是从这类簇 promote 成功的\——那是全系统**唯一**真实 promote 成功案例。Lane  │
│ A/B 提议的 intake 过滤会亲手掐死自己的训练信号，且 Lane B 自己指出           │
│ `_AGENT_PROMPT_MAX_LEN=150` 在 intake 侧是数据丢失方向的误杀。  但 Lane A    │
│ 的痛点判断（队列认知负荷）和 Lane B 的度量建议仍然成立，折中方案：  -        │
│ **做**：发现队列（CLI + 看板）展示层——agent-prompt 形状的行打 `shape:        │
│ agent-echo` 标签、默认折叠到分组末尾、支持批量 dismiss；每列含义自解释（并入 │
│ N1）。 - **做（一次性测量，半小时）**：离线脚本量两个数——(a) miss 池中       │
│ agent-prompt 形状占比；(b) \ 字符且非 agent 形状\的 miss 占比。结果存        │
│ `.omx/artifacts/gate35-echo-measure.md`。**若未来回声率继续恶化或有新证据，  │
│ 凭这份基线重议 intake 过滤**。 - **不做**：`scan_candidates` intake          │
│ 加形状过滤；簇内 Jaccard>0.8 折叠（落在 gate30 标定的 0.41–0.88 无人区，Lane │
│ C 反驳 3 成立）。 - **谓词保护**：`_is_agent_prompt_shape`                   │
│ 本体一字不动（replay 基线 import 它，改了 gate32 基线失去可比性）。  ###     │
│ 裁决 2：D1 做 shadow-only verifier，永不硬阻断 —— 三路交集                   │
│ 三路在这个形态上实际一致：Lane A 要\建议性徽章\，Lane B 要\shadow verdict    │
│ 只记录不 gate\，Lane C 的最小版是\trigger lint 只警告不 FAIL\。Lane C        │
│ 的统计批评（n=3 簇上捕获率无区分度）成立，因此：  - verifier                 │
│ 产出**描述性明细**（接住哪几条、没接住哪几条、各自最近邻、会抢哪几条现存命中 │
│ ），徽章只用 PASS/WARN 两级，**不设 FAIL 硬阻断**；激活路径永远不需要        │
│ `--force`。 - 静态部分吸收 Lane C 的 trigger lint：triggers                  │
│ 非空、不全是卫生形状、对簇内 ≥1 条代表 query recall                          │
│ 过阈值——不通过只打印警告。 - 结果落                                          │
│ `.vibe/observability/promote_verdicts.jsonl`（新 store，双锁+坏行跳过），攒  │
│ ≥30 条 verdict 后才允许讨论阈值固化（沿用代码库自己的 ≥30 再校准纪律）。 -   │
│ embedding 侧 fail-open 降级（docker/无模型环境标 `embedding:                 │
│ unavailable`），e2e 65/65 不许红。 - Lane C 反驳 2（verifier                 │
│ 给空壳发假阳性通行证）部分成立 →                                             │
│ 徽章文案必须写清它测的是\触发召回\，不是\内容质量\；内容质量的解法（core_ste │
│ ps 预填骨架）作为同阶段交付物，但标注为 best-effort。  ### 裁决 3：D3        │
│ 只加只读描述统计列 —— 三路一致  `source ∈ {gold, miss_recurrence}`           │
│ 早已分闸（Lane C 反驳 1），细分桶 n≈4 是伪科学（Lane B                       │
│ 统计功效分析）。只做：发现队列/看板加 per-source 累计 success/dismiss        │
│ 只读计数。任一 source 攒到 ≥30                                               │
│ 样本再议阈值（代码库自带纪律，`skill_promote.py:164-165`）。  ### 裁决 4：D4 │
│ 否决立项 —— 采纳 Lane C，记录 Lane B 的 sealer 备选  Lane C                  │
│ 的三条致命伤无法回避：威胁模型为空（本机 dogfood 文件）、hand-edit JSONL     │
│ 是明示支持的用法（chain 会把合法操作变告警）、与 prune/留存池 purge          │
│ 生命周期冲突。Lane B 的离线 sealer                                           │
│ 架构虽解决了热路径问题，但解决不了\无人受益\——**不立项**，本裁决写入         │
│ `docs/decisions/2026-08-22-d4-immutable-records-rejected.md`，附 Lane B 的   │
│ sealer 设计作为未来若出现\标定结论需第三方采信\场景时的备选方案存档。  ## 3. │
│ 最终实施路线（gate35 起）  ### 阶段一（gate35，1–2 天）：队列可读性 +        │
│ 展示层去噪  1. **N1 可解释性**（`skill_commands.py` discover                 │
│ 表格、`dashboard/_discoveries.py`）：    - 列头自解释化（Pattern→`模式（代表 │
│ query)`、Source→`来源（gold=成功簇 /                                         │
│ miss×复现=未命中复现）`、Score→`评分`、Behavior→`行为一致性`），`vibe skill  │
│ discover --help` 加 ≤5 行词汇表；    -                                       │
│ 每张卡片加\为什么在这里\行（入池原因从 ClusterCandidate                      │
│ 字段直译：gold_rate≥0.6 / miss 跨 N 天复现 M 次）；    - 看板卡片同口径      │
│ tooltip。 2. **D2 展示层**：agent-echo 打标（复用 `_is_agent_prompt_shape`   │
│ 只读调用）+ 回声行默认折叠/沉底 + `vibe skill discover dismiss --shape       │
│ agent-echo` 批量否决；scan summary 加\队列含 N 条机器形状（已沉底）\计数。   │
│ 3. **D3 描述统计列**：per-source success/dismiss 只读计数进 CLI 表格与看板。 │
│ 4. **回声基线测量脚本**：`scripts/measure_echo_share.py`，产出落 artifacts。 │
│ 5. 验收：20                                                                  │
│ 张卡片肉眼检查回声沉底且可展开；列含义无文档可懂；\为什么在这里\与           │
│ ClusterCandidate 字段一致（防文案说谎的测试）。  ### 阶段二（gate36，3–4     │
│ 天）：promote shadow verifier  1. `replay_routing_baseline.py` 的 trigger    │
│ 侧逻辑抽成可注入 draft 技能的函数（保持脚本行为不变，纯重构+测试钉住）。 2.  │
│ `skill_promote.py` 新增 `verify_draft()`：trigger lint（静态）+ shadow       │
│ 回放（动态，embedding fail-open）→ verdict 写 `promote_verdicts.jsonl`。 3.  │
│ `promote_cmd` 挂接：promote                                                  │
│ 后自动跑，输出徽章+明细；`_activate_promoted_draft` 打印最近 verdict         │
│ 摘要（不阻断）。 4. 看板 payload 加 `verdicts` 段（按 cluster_id 平铺，因    │
│ promoted 行不在 list_pending）。 5. 草稿骨架用 `core_steps`                  │
│ 预填（best-effort，标注生成来源）。 6. 验收：已知良好簇 → PASS；回声簇 →     │
│ WARN 且明细列出未捕获 query+最近邻；docker 内降级路径不红；全量 pytest 6041+ │
│ 绿。  ### 不做清单（显式记录，防复活）  - intake 形状过滤（维持 gate32       │
│ 裁决；除非 gate35 基线测量显示回声率 >80% 且长 query 误杀率 <1%，才可重议）  │
│ - 簇内 Jaccard 0.8 折叠（0.41–0.88 无人区，无标定证据） - verifier 硬阻断 /  │
│ 自动激活（Lane C 反驳 5：防自动化滑坡） - D3 阈值工程（≥30 样本/桶 之前） -  │
│ D4 hash chain / sealer（决策记录存档）  ## 4. 与既有触发器的关系  -          │
│ 本路线不动 P0-lite、M3、留存池、probe 任何触发器，全部并行等数据。 -         │
│ 阶段二的 verdict 流恰好是未来 P0-lite 护栏仲裁设施的 rehearsal（同一套       │
│ shadow 机制），但两者显式不合并、不互相阻塞。 - cmspark 首批 promote/dismiss │
│ 的发现精度基线仍是用户侧待办，不受本路线影响。  ## 5. 一句话                 │
│ 三路对抗的真实收获：把\EvoTrace 风格自动化\的野心（D1                        │
│ 完整版、D4）裁掉，把共识收敛到\先让队列可读可信（阶段一），再给 promote      │
│ 装一盏不挡路的灯（阶段二）\。  ---  ## 6. 三路评审收敛（claude / pi / grok   │
│ 均 PASS_WITH_NITS，0 BLOCK）  评审产物：gate34-claude.md / gate34-pi.md /    │
│ gate34-grok.md。9 个 MAJOR 全部吸收为以下设计修订（A–K），NIT                │
│ 逐条处置见末节。  ### 修订 A：verdict 时效性（pi-MAJOR-1） verify_draft 在   │
│ promote 时跑只是初诊；**activate 路径重跑一次**（离线、廉价）——因为 M5       │
│ 强制激活前手改 draft，promote 时的 verdict 描述的是已不存在的技能。verdict   │
│ 行内嵌 `draft_sha256` + trigger 集哈希；看板/CLI 仅在与当前 draft            │
│ 匹配时展示，否则显示 \stale\ 并由 activate 自动重跑。修复后 Lane A           │
│ 验收目标\激活前不再开盲盒\才真正成立。  ### 修订 B：shadow                   │
│ 口径必须对齐生产，禁止复用 p0_shadow 谓词（pi-MAJOR-2 / grok-MAJOR-3）       │
│ `p0_shadow`（replay_routing_baseline.py:151-175）刻意偏离生产                │
│ `explicit_guarded_skill_match`（triage_service.py:541-566：空白折叠/撇号/≥6  │
│ 字 containment/全记录 vs                                                     │
│ first-hit-wins），脚本自评\是信号存在性探测，不是激活数据集\。**verifier 的  │
│ trigger 侧必须包装生产匹配器**，p0_shadow 只留在 replay 脚本。embedding      │
│ 侧**双线分测**：recall 线（triage_recall `_candidate_text`,floor 0.25）与    │
│ index 线（`_compute_profile_text` + 0.45 门 + margin)，各自 fail-open 标     │
│ `unavailable`。verdict schema 记录 `ruleset_version` + 实测管线清单 +        │
│ 分线结果——攒 ≥30 条后的阈值讨论才不吃非生产数字。  ### 修订                  │
│ C：展示层打标另立前缀谓词（pi-MAJOR-3 / grok-MAJOR-1）                       │
│ `_is_agent_prompt_shape` **冻结不动**（replay 基线 import 它）。新增展示专用 │
│ `_has_agent_prompt_prefix`（仅前缀黑名单，**无 150 字符长度规则**）——粘      │
│ traceback/长 spec 的合法长 query 不会被误标沉底。  ### 修订 D：verdict store │
│ 隐私边界（claude-MAJOR-1 / grok-MAJOR-4） verdict 只落发起 promote 的项目    │
│ `.vibe/observability/promote_verdicts.jsonl`；**global scope 草稿的 verdict  │
│ 只存计数 + query 哈希，不存原始 query**（对齐 M5                             │
│ 边界，skill_promote.py:1954-1959）；文本字段一律过                           │
│ `sanitize_body_text`（:1814-1825）。看板改动是 `_discoveries.py` payload（按 │
│ scope 过滤明细）+ `dashboard/templates/index.html:659-725`                   │
│ 渲染，CLI/看板去重 lockstep（_discoveries.py:101-105）。  ### 修订 E：批量   │
│ dismiss 走池状态翻转，不走指纹负名单（claude-MAJOR-2 / grok-MAJOR-1）        │
│ `discover dismiss` 的指纹负名单会污染 `threshold_suggestion` 的 dismiss      │
│ 计数（且占 MAX_PENDING 容量到 TTL）。批量 shape dismiss 改走**候选行 status  │
│ 翻转**（`vibe skill dismiss` 机制）：释放容量、**豁免计入**                  │
│ threshold_suggestion 输入（dismiss_reason=shape-batch                        │
│ 单列）。粒度=候选卡片（cluster），非单条 query；需显式 `--yes`，确认文案点名 │
│ bd1bc217 先例（\回声簇也曾 promote 成功\）。  ### 修订                       │
│ F：\为什么在这里\只写真实字段（claude-NIT / grok-MAJOR-2） ClusterCandidate  │
│ 无 recurrence pairs/days 字段（miss upsert                                   │
│ 不落，skill_promote.py:1574-1590；discovery.py:22-24                         │
│ 声明在案）。文案只从实存字段直译：`source` / `gold_rate` / `span_count` /    │
│ `len(task_ids)` / `first_seen`。加字段=schema                                │
│ 变更，**显式排除在阶段一之外**（否则违背\纯展示层\承诺）。  ### 修订         │
│ G：回声测量口径与重议门槛（grok-NIT / claude-NIT） `measure_echo_share.py`   │
│ 同时报**池子占比**与**已入队卡片占比**（64% 是池子不是卡片；ScanSummary      │
│ 当前不落盘，_discoveries.py:23-27）。重议门槛改为：**队列卡片回声率 >80%     │
│ 且长 query 风险人口占比 <1%**（(b) 是风险人口，不是\误杀率\，措辞修正）。    │
│ ### 修订 H：基线与 e2e 验收措辞（pi-NIT / grok-NIT） 动工时重新钉 pytest     │
│ 基线（pi 实测 collect-only 已 6055，仓内记载漂移）。e2e 验收 =               │
│ 现有套件零回归 + **新增一条 promote 降级 smoke**（embedding unavailable      │
│ 路径）；不再宣称\65/65\静态数字。  ### 修订 I：D3 统计列口径写死（pi-NIT /   │
│ grok-NIT） success = promoted→activated→`count_skill_route_hits` ≥           │
│ HISTORY_HIT_THRESHOLD(5)（discovery.py:550）；dismiss =                      │
│ 池状态翻转计数（不含指纹负名单，与修订 E 一致）；口径写进 `--help` 词汇表。  │
│ ### 修订 J：分组键与 WARN 条件定义（grok-NIT） 展示分组键 =                  │
│ `cluster_fingerprint`（discovery.py:107，现成）。徽章两级定义：PASS =        │
│ trigger lint 全过 且 shadow 捕获簇内全部 query；WARN = 任一不满足（无 FAIL   │
│ 级，描述性呈现明细）。  ### 修订 K：core_steps 预填减量（claude-NIT /        │
│ grok-NIT） 阶段二 step 5 大部分已 ship（gate31 +                             │
│ skill_promote.py:2036-2052）。剩余增量仅\标注生成来源\；**空 core_steps      │
│ 簇保持 TODO，禁止编造 HOW**（Lane C 反驳 2 仍成立：trigger 召回通行证 ≠      │
│ 内容质量）。  ### NIT 处置（已吸收不再单列） - verdict store                 │
│ 加容量策略（保最近 200 条或 90 天，沿用仓内轮转惯例）。 - 决策记录（D4       │
│ 否决）写一句\池构成代价由 gate32 A1 裁决承担\（pi-NIT）。 -                  │
│ 引用勘误入档：indexer 实际路径 `src/vibesop/core/skills/indexer.py`（0.45    │
│ 门注释 :462-463）；conftest stub setitem 在 :326。 - 批量 dismiss 是新 CLI   │
│ 面，help 文案与确认流按修订 E 定义。                                         │
│ **收敛后路线不变**：阶段一（可读性+展示层去噪+统计列+测量脚本）→             │
│ 阶段二（shadow verifier，按修订 A/B/D/J 实施）。 /bin/sh: -c: line 0: syntax │
│ error near unexpected token `(' /bin/sh: -c: line 0: `vibe route --json      │
│ --yes \# Gate34 三路评审任务书 你是独立高级评审，复审 VibeSOP 项目 gate34    │
│ 的综合设计稿。项目根：/Users/huchen/Projects/vibesop-py（Python，src/vibesop │
│ /）。)                                                                       │
╰──────────────────────────────────────────────────────────────────────────────╯
复核完成。对照代码事实逐条核查了修订 A–K 与交叉一致性（含 6055 测试基线实跑验证）。

## Verdict

PASS_WITH_NITS

## Findings

- [MAJOR] **修订 B 的 trigger 侧指令按字面实现即空转**。`explicit_guarded_skill_match`（triage_service.py:541-566）是 **guarded 技能专用**：`guarded_skill_name`（:491-496）只认 `_GUARDED_SKILL_EXTRA_TOKENS`/`_GUARDED_SKILL_FALLBACK_TRIGGERS`（:474-477）表内 id，草稿技能 id 是 `draft-<cluster>` slug（skill_promote.py 渲染段），永远不落入 guarded 表 → `short is None → continue` → 返回 None。通用技能的 trigger 生产匹配实际走三条路：index 嵌入 0.45 门（indexer.py:455,463）、recall 嵌入 0.25 底（triage_recall.py:51,206）、unified.py:458-469 的 token containment（嵌套于 `_build_decomposition_skills`:408 的 fallback prompt 预筛）。B 说"必须包装生产匹配器"却只锚定 guarded-only 函数——草稿验证的 trigger 侧会静默产出全空结果，仍记录"已跑 trigger 侧"，污染攒 ≥30 条的阈值讨论。修订需加一句：把该生产语义（lowercase+撇号剥离、无空白折叠、containment 无长度下限、first-hit-wins）**泛化包装**用于任意草稿 trigger，或明示以 embedding 双线为唯一 trigger 召回口径（triage_service 引用只作语义锚点）。

- [NIT] **修订 A 与 B 的成本张力**（任务书点名示例）。A 断言 activate 重跑"离线、廉价"；B 要求双线 embedding 分测。而 replay 的 `load_embedding_model`（replay_routing_baseline.py:297）每次调用构造 `SentenceTransformer`，无模块级缓存——模型可用环境下每次 activate 重跑是秒级加载，"廉价"只在 fail-open（无模型）路径成立。需一句约束：模型句柄模块级单例，且 draft 未变时复用 promote 时 embedding 分线结果。

- [NIT] **修订 E 与 I 的 dismiss 口径不一致**。事实：`threshold_suggestion` 输入只读指纹负名单（skill_commands.py:2559,2661 → `DiscoverySignalStore.dismiss_count`），池状态翻转本就不进该输入，E 的"豁免"天然成立（无错）；但 I 定义 D3 列 = "池状态翻转计数"，**按字面包含 shape-batch 翻转**，per-source dismiss 列会被回声簇批量否决灌水，且 §裁决 3 的"≥30 样本再议阈值"若计入 dismiss 则被污染。"与修订 E 一致"需落到字面：D3 列排除 `dismiss_reason=shape-batch`。

- [NIT] **修订 C 与 E 未点名同一谓词**。C 的展示标签用 `_has_agent_prompt_prefix`（无 150 规则），但 E 的批量 `dismiss --shape agent-echo` 未指定选择谓词——若实现者用 `_is_agent_prompt_shape`（含 150 上限，skill_promote.py:360-378），长合法 query 会被标为可沉底却又被批量否决，标集与否决集错位。E 应写明复用 C 的前缀谓词。

- [NIT] **正文残留与修订 H 未同步**：§3 阶段二 step 6 仍写"全量 pytest 6041+ 绿"、§裁决 2 仍写"e2e 65/65"——H 已用 6055（实跑 `pytest --collect-only` 确证 6055）与"零回归+降级 smoke"取代；正文未改只留文档噪音，e2e 的 65 在 `e2e_command_smoke.py` 仅有 11 处字面 `record(` 调用，撤销静态数字判断正确。

**吸收核查（其余全过）**：A 正确吸收（`draft_sha256` 字段 :453-460、M5 守卫 skill_commands.py:2064/2087、activate 路径 :2024 均在案）；C 正确（展示层已 import skill_promote，_discoveries.py:48，新前缀谓词可注入）；D 正确（M5 隐私边界 :1954-1959、`sanitize_body_text` :1814-1825、index.html:659-725 渲染区、_discoveries.py:101-105 lockstep 均核实）；E 正确（池翻转=dismiss_cmd :2144-2185，bd1bc217 先例 :342-349 在案）；F 正确（ClusterCandidate 确无 recurrence 字段，discovery.py:22-24 声明在案）；G 正确（_discoveries.py:23-27 ScanSummary 不落盘属实）；I/J/K 引用（discovery.py:92/550、:107、skill_promote.py:2036-2052）全部核实。交叉矛盾仅上述 A/B 成本与 E/I 计数两处，均为实现前一句话可修，无设计级冲突。
