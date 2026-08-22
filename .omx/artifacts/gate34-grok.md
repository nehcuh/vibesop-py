先读完整任务书并走路由，再只读核对裁决稿引用的代码事实。路由还在跑，我先把完整任务书和三路原文读完，再对代码引用做只读核对。路由把 UI/UX 等无关技能也拉进来了，这份任务是设计裁决复审，我按 `review` 的只读核查来核对代码引用。`review` skill 面向 diff/PR，不适合这份设计稿复审。我继续只读抽查关键代码位置。## Verdict
PASS_WITH_NITS

## Findings
- [MAJOR] 阶段一把 `_is_agent_prompt_shape` 原样用于打标/沉底，并加 `vibe skill discover dismiss --shape agent-echo`。该谓词对 `len>150` 一律 True（`skill_promote.py:363-377`），且 `discover dismiss` 写的是粘性否定列表（`skill_commands.py:2627-2653`，`--all` 才见）。这会把合法长 query 和 gate32 明确保留给人审的回声簇（含 bd1bc217 那类）一次性藏起来，效果接近被否决的 intake 过滤。展示层必须另立前缀谓词；批量 dismiss 要确认，且粒度写清是卡还是 query。裁决稿 §2 裁决 1 / §3 阶段一.2
- [MAJOR] N1「为什么在这里」写「miss 跨 N 天复现 M 次」无法从 `ClusterCandidate` 直译：miss upsert 不落 pairs/days（`skill_promote.py:1574-1590`），`discovery.py:22-24` 已声明「候选行不存跨日数」。按现稿写文案，阶段一自带的「防文案说谎」测试会红。只许写已存字段（`source` / `gold_rate` / `span_count` / `len(task_ids)`），或显式立项加字段（那就不是纯展示层）。裁决稿 §3 阶段一.1
- [MAJOR] 阶段二把 `replay_routing_baseline.py` 的 trigger 逻辑抽成 verifier。`p0_shadow`（`:151-164`）刻意偏离生产 `explicit_guarded_skill_match`（`triage_service.py:541-566`：空白折叠、撇号、≥6 字 containment、全记录 vs first-hit-wins）。脚本自评是「信号存在性，不是激活数据集」。用它给 promote 打「接得住」会系统性说错生产行为。应包生产匹配器；`p0_shadow` 只留在 replay 脚本。裁决稿 §3 阶段二.1
- [MAJOR] 阶段二验收要「未捕获 query + 最近邻」，但没写双 embedding 分测（recall `_candidate_text` floor 0.25，`triage_recall.py:51,206`；index `_compute_profile_text` 0.45 门，`indexer.py:455-467`）。verdicts 落 `.vibe/observability/promote_verdicts.jsonl` 未分 project/global，也未对标 M12 全局草稿禁止落原始 query（`skill_promote.py:1978-2004`）。看板只改 `_discoveries.py` 不够，真实 UI 在 `dashboard/templates/index.html:659-725`，且 CLI/看板去重必须 lockstep（`_discoveries.py:101-105`）。裁决稿 §3 阶段二
- [NIT] 「6041 测试基线」仓库内无此数；最近落盘是 5964 passed / 14 skipped（`memory/session.md`、`PROJECT_CONTEXT.md`）。e2e 65/65 有记载，但 `e2e_command_smoke.py` 只跑 `skill discover`、不跑 `promote`。不新增 smoke 则 docker fail-open 未测；新增则不再是 65/65。验收应写「现网套件零回归 + 补一条 promote 降级 smoke」。裁决稿 §3 阶段二.6
- [NIT] 「草稿骨架用 `core_steps` 预填」已在 `skill_promote.py:2036-2052` 落地；无 ≥70% 步骤时只能 TODO。阶段二.5 不是新活，禁止在空簇上编造 HOW。Lane C 反驳 2 仍然成立：trigger 召回通行证 ≠ 内容质量。
- [NIT] 回声测量只量 miss 池，重议门槛却写「回声率 >80%」（裁决稿「不做清单」）。64% 是池子不是队列卡片；`ScanSummary` 还不落盘（`_discoveries.py:23-27`）。脚本必须同时报已入队卡片的 echo 占比，重议门槛跟这个数，不跟池子。
- [NIT] D3 计数未声明用哪套 dismiss：`vibe skill dismiss`（翻候选 status）vs `discover dismiss`（指纹否定列表）。`--history` 已有未分源合计（`skill_commands.py:2477-2487`）。列口径必须写死，且 `DiscoverySignal` 本身不存 `source`。
- [NIT] 当前 CLI 表无 fingerprint 分组（`skill_commands.py:2417-2445`），「折叠到分组末尾」分组键未定义。PASS/WARN 切分只写了 lint 的「≥1 条代表 query」，shadow 回放的 WARN 条件空缺。
- [NIT] `tests/conftest.py` embedding stub 在 fixture `:281`，真正 `setitem(..., None)` 在 `:326`，不是 Lane B 写的「281 行 stub」。Lane 引用的其余锚点抽查属实（见下）。

**代码事实抽查**（只读）：`skill_promote.py:342-349` gate32 A1（64%、合法池成员、bd1bc217、只管自动预填）存在且转述正确；`:366` 谓词 + `:376` 长度规则属实；`:1429-1433` intake 仅 `is_route_miss_span` ∩ `not _is_low_information_query`，无形状过滤；`:141-167` 分源门（gold 0.60 / miss 0.70×3pairs×2days，≥30 再校准）已存在；`replay_routing_baseline.py:52` import 谓词、`:139/:151/:233` shadow 函数存在；`span_writer.py:110` `_locked_append` 与 100µs p95 注释属实。`from_dict` 手改 JSONL（`:517-521`）、M5 `draft_sha256`（`:453-460`）、0.26 自召回注释（`:1990-1992`）、gate30 Jaccard 标定 0.88–0.99 vs ≤0.41（`:118-126`）均属实。

## 对各裁决点的意见

**裁决 1（D2 只展示层）**：成立。gate32 白纸黑字禁止 intake 杀掉回声，且 150 字上限是预填卫生不是准入卫生；Jaccard 0.8 落在 0.41–0.88 无人区，否决正确。展示层可以做，但必须前缀打标 + 默认沉底可展开，不能拿现谓词做粘性批量 dismiss。

**裁决 2（D1 shadow-only，永不硬阻断）**：方向对，三路在「不挡激活」上确实交集；Lane C 的 n=3 无区分度因此不能 FAIL，这个推理站得住。未采纳「等 cmspark 精度基线 / span_count≥10」可接受，前提是徽章保持描述性、不固化阈值。路线把 replay 发散谓词当生产验灯、又把 `core_steps` 已有能力当新交付，必须改挂载点后再开工。

**裁决 3（D3 只读统计列）**：成立。`source ∈ {gold, miss_recurrence}` 早已分闸，细分桶是伪科学；`threshold_suggestion`（`discovery.py:524-541`）已拒绝自动改阈值。只加 per-source 计数，等 ≥30 再议，与代码纪律一致。

**裁决 4（D4 否决）**：成立。威胁模型空、手改 JSONL 是支持用法、与 prune/TTL 冲突，三条都在代码里；离线 sealer 解热路径不解「无人受益」。写决策记录并附录 sealer 即可，不立项。
