先按路由协议匹配技能，再回代码核验评审包里的关键断言，避免只在摘要上裁决。路由命令还在跑。我同时核对评审包里最关键的代码断言，避免只按摘要下结论。路由落到 `mattpocock/review`（按 diff 审代码），和这次「方向裁决」对不上。我按对立评审做：先回代码核验包里的关键断言，再逐题下结论。关键路径已对上。接下来核对 promote 模板、pending 队列数据和门限会误伤的短 query。路由命中 `mattpocock/review`（按 diff 做 Standards/Spec 双轴审）。本次是方向裁决、没有固定对比点，按该技能走会空转。下面按对立评审做：包内断言已回代码核对，能推翻的会标出来。

---

## 包内断言可信度（先拆地基）

| 断言 | 判定 | 证据 |
|---|---|---|
| F1 zip 生产不可达 | 成立 | `clustering.py` 从同一 `member_keys` 投影 `task_ids`/`queries`，`gold_detection.py:75` `strict=True` 打不到 |
| F2 assert 低危 | 成立 | `skill_promote.py:798` 抓手工 fixture；`dashboard/server.py:481-482` 确有 `-O` 先例 |
| F3 description 是中性稀释 | 成立，但处方写反了 | Jaccard 把 description 放进 union；`+0.25/+0.4` 只打 name/keywords（`strategies.py:160-174`） |
| F5 无跨进程锁 | 成立 | `routing_pending.py` 只有 `threading.Lock`；`unified.py:1139` 每次新建 store 全量重写 |
| F6 queries_block 未折行 | 成立 | frontmatter 走 `_sanitize_yaml_value`；`queries_block` 原文拼接 |
| pending 7/7 垃圾、0 审 | 成立 | 现文件 7 行全 `pending` |
| 「7/7 都是 levenshtein@1.0 或 no-match」 | 字面真、因果假 | **3/7 是 `no_match`**（可以、/debug、route my query），门限碰不到 |
| 「matcher 门限 → 错路由和队列噪音一起消失」 | **不成立** | 门限后这 3 条仍走 `no_match` 入队；另 4 条也会变成 `no_match` 再入队 |
| 「boost 把 gold_rate 推向 promote 阈值」 | **机制写错** | `gold_rate` 是「该 instinct `success_count>=1` 的成员占比」，二值；boost 要求已有 `apps>=1` 且 `rate>=0.8`，**造不出第一颗 gold** |
| instincts 9 条 success 全 0 | 方向对、数字过期 | 现 `.vibe/instincts.jsonl` **16 行**（本轮路由又写入），`success_count` 仍全 0 |
| triage_recall 无余弦下限 | 成立，行号错 | 无阈值在 `triage_recall.py:70-79`；177-188 是 `_candidate_text` |
| global 路径「疑似」不在发现路径 | **已核实，不是疑似** | `skill add --global` → `~/.vibe/.vibe/skills/`；`CandidateManager` 两条都不搜；promote 文案却写 `~/.vibe/skills/` |
| auto-config 进了索引 | 成立 | `.vibe/skill-index.json` 有 `project/auto-config.yaml/auto-config` |
| 暴露面为零 | 对草稿成立 | draft 在 `.vibe/observability/skill_drafts/`，不在发现路径 |

**待验证（不臆造反证）**

- LLM indexer 是否真把 When-to-Apply 的 query 炼成强 profile（架构上合理，未读 indexer 实现）
- `/review` → `kimi-gated-fix@1.0` 是因为 skill token 里有 `review`，还是当时 candidate 集根本没加载 `mattpocock-review`（id 以 `-review` 结尾，按 `explicit_layer.py:54` 本应短路）
- `feedback-collect` 是否在 dogfood 机上被 launchd/cron 周期跑（代码存在 ≠ 在转）

---

## 问题 1：Review Checklist 节是否过了「僵尸结构」反驳？

**结论：没过。砍 SKILL.md 里的 Checklist 节。人审清单只留在 promote CLI 文案（一次性、不可被索引）。**

**理由**

折中设计比「验收/反模式」领域占位节干净，填空横线也比空段落难盖章。但这没有回答僵尸机制：

1. **没有激活门闩。** 「delete before activating」是散文。激活路径是「copy + `vibe skill add`」，不检查该节是否还在。
2. **会被索引。** 节一旦留下，LLM indexer / keyword 会把「改写 name/description」「何时不该用」当成技能正文。这比现在的 provenance description 更像磁铁。
3. **项目里已有僵尸先例。** `(no core steps identified — …)` 已经是「有数据源仍退化、人也不删」的活标本。再加一节可删块，默认结局是留下。
4. **和 Tier1 文案重复。** 提案已在 Tier1 写「promote 文案补 3 行人审 checklist」。CLI 输出随命令消失，进不了 skill-index。同一清单写进 SKILL.md 是双份，僵尸面只在文件里。
5. **范畴仍然错。** oneshot-web-spec 的验收清单约束的是**交付物**（网站），不是事后从 span 归纳出的草稿。人审成本高是真的，解法是「不激活空壳」（draft 已在发现路径外），不是在空壳里再塞一节流程。

「50 倍于 instinct accept/dismiss」无计量，不采信。当前零草稿、零 promote，加结构就是投机通用性。

**置信度：高**

---

## 问题 2：levenshtein 门限能否当本轮主线？形态与误杀

**结论：问题是真的，主线资格不成立。可做，但是「末层纠偏」不是「P2 变形主线」。最小字符/token 数门限会误杀；正确形态是「通用词 + 单 token 命中」拒绝，且必须搭配 pending 侧低信息过滤（P2 原案不能整段砍）。**

**理由**

队列死因有一半不在 levenshtein：

| query | 实际层 | 门限后 |
|---|---|---|
| 可以 | `no_match` | 仍入队 |
| /debug | `no_match` | 仍入队 |
| route my query | `no_match` | 仍入队 |
| /review, 使用 review, review my code ×2 | `levenshtein@1.0` | 变成 `no_match`，**仍入队** |

`should_enqueue_from_route` 对 `no_match` 无条件入队。提案一边把门限当主线，一边砍「query 侧规则进 pending」——这两件事互相拆台。门限只改错路由标签，不治告警疲劳。

计分也不是「短字符串」问题。`LevenshteinMatcher` 对 `len<=2` 的 token 已跳过；「可以」因此已经是 0 分。`/review` 被切成 token `review`，和 skill 词表精确命中 → 1.0。这是**高频泛词单点命中**，不是编辑距离。

**误杀面（合法短 query）**

- 斜杠指令：`/review`、`/debug`、`/tdd`、`/route`（应走 EXPLICIT，不该落到末层）
- 中英短指令：`修 bug`、`写测试`、`debug this`（instincts 里已有 `debug this` 走 `ai_triage`）
- 2 字中文：现网已经 0 分，再加字符下限是空操作

最小字符（例如 <12）和最小 token 数（<2）都会误杀斜杠指令。置信度 cap（例如 levenshtein 最高 0.6）也救不了队列：`_WEAK_MATCH_LAYERS` 不看分数，只要层是 levenshtein 就入队。

**建议形态（只动 Stage 4 末层，不动 EXPLICIT/SCENARIO/KEYWORD）**

1. 泛词表（review/debug/fix/test/help/code/query/route/使用…）上，**有效命中 token < 2 则返回 0**。
2. 单个长且特异的 token（长度 ≥ 8 且不在泛词表）仍可过，保住真 typo。
3. **不要**用整句字符下限当主闸。
4. 对偶：pending 对 `no_match`/`levenshtein` 共用同一套低信息规则，否则噪音只是换 kind。
5. 回归集至少包含：`/review`、`/tdd`、`debug this`、`修 bug`、`可以`、`review my code`、一条真实拼写错误。

`/review` 没走 EXPLICIT 才是更值钱的洞：`mattpocock-review` 按 `endswith("-review")` 应当短路。先查 candidate 集，再动门限。

**置信度：高**（队列拆分、计分逻辑已读；kimi-gated-fix 的 token 构成待验证）

---

## 问题 3：feedback-collect 自动 boost — 拆还是改形？

**结论：拆。不要改成「只调 confidence、不加 success_count」。**

**理由**

`record_outcome(success=True)` 同时加 `success_count` 并用 Wilson 重算 `confidence`。当前 dogfood：16 条 instinct 全是 `success_count=0`，boost 条件是 `apps>=1 && rate>=0.8 && apps<=2`，**现在一次都打不中**。拆了对现存行的语义是空操作，不是破坏性迁移。

包里「推向 gold_rate / promote 阈值」写错了：

- `assess_gold_status` 只看 `success_count >= 1`（默认），同一 instinct 从 1 加到 2，`gold_rate` 不变。
- boost **不能**创造第一颗 success。
- 真风险在另一条线：`is_reliable` 要 `apps>=3`。两次真人成功后再 boost 一次，不经第三次确认就转可靠。

改形更差：Wilson 每次 `update()` 从计数重算。只改 `confidence`、不动计数，下一次 accept/dismiss 会覆盖；要保住就得另开字段，复杂度高于拆除。decay 侧（高频 miss → `success=False`）是有新信息的，保留。

真正在灌池子的是 `unified.py:1187-1194`：`confidence>=0.7 && len(query)>5` 就 `learn(source=auto_routing)`。levenshtein@1.0 必触发。本文件已有整段评审指令、`debug debug debug…` 这种行。boost 不是最高性价比点。

**置信度：高**

---

## 问题 4：Tier 划分是否合理？

**结论：大框架能用，主线标错、有两项估高、有两项估低。**

**估高**

- **levenshtein 当 Tier1 主线**：问题真，工具选错，且砍 P2 后治不好队列。
- **feedback-boost 进 Tier1**：机制写错，当前零触发。预防性拆除可以，但不是本轮杠杆。
- **F3 当路由修复**：把 description 改成「前两条 query 拼接」会让空壳更好匹配。现在 description 是稀释；改完变成第二块 query 磁铁。name 已经是 `queries[0][:80]`。F3 若要做，方向应是 **name 去 query 化**（`draft-{cluster_id[:8]}`），description 维持 provenance 以满足 spec 必填。

**估低**

- **`vibe skill add` 不重建语义索引**：所有新技能（含 P0）在 SEMANTIC_INDEX 隐身。Phase 6 只对 skill_id 空格化做两次 `route_single`。这是激活断点，不是 T3 附属。
- **global 双 `.vibe` 路径**：已核实。promote 文案指向 `~/.vibe/skills/`，安装写到 `~/.vibe/.vibe/skills/`，发现路径两头都不收。P0 若走 `--global` 会装完找不到。

**划分尚可**

- F5/F6：小、真、本轮该做。
- F2、triage 余弦下限：T2 合适。
- 砍 F1、完整占位节、索引层过滤、skill-craft profile：同意。
- P0 装池 + before/after：必须先有 `eval_routing.py` 基线，T3 对；但 oneshot-web-spec 是**单文件 md**，不是带 `SKILL.md` 的目录，装池要先包一层。

**置信度：高**

---

## 问题 5：包内未覆盖的盲区

至少这些，按杀伤力：

1. **门限与砍 P2 逻辑矛盾（主盲区）。** 7 条里 3 条已是 no_match；另 4 条门限后也变 no_match。日上限 3 条，不滤 `no_match` 低信息，队列照死。
2. **`auto_routing` 无确认写入 instinct。** `conf>=0.7 && len>5` 即 `learn()`。levenshtein 虚高 1.0 正好跨线。gold 池空不是因为缺 boost，是因为这些行 `success_count` 一直是 0；一旦有人 accept 一条 pending（`query_hash` 已和 instinct id 对齐，例如 `review my code` → `instinct_cf4e84c13f1d`），垃圾 pattern 会立刻变 gold 种子。
3. **`/review` 的 EXPLICIT 缺口。** 斜杠匹配看 id / `/{name}` / `-{name}`。落到 levenshtein 说明当时 candidate 集里没有 `*-review`，或发现路径没扫到。门限是在末层打补丁。
4. **pending 去重键是 `(query_hash, skill_id)`。** 同一句 `review my code` 进了两条（kimi-gated-fix 和 fuck-my-shit-mountain）。日上限按条数，一条垃圾 query 能占 2/3 日配额。
5. **name=query 才是糖衣，F3 没打到。** 改 description 会加重，不会减轻。
6. **oneshot-web-spec 形态。** `~/.cmspark-agent/skills/oneshot-web-spec.md` 是单文件；发现逻辑找的是目录/`SKILL.md`。P0 不是 copy 就能进池。
7. **preference `record_selection(..., was_helpful=True)` 对高置信路由无条件记正。** 与 boost 同类，包未提。

**置信度：高**（1/2/4/6 已读代码；3 的现场 candidate 集待验证）

---

## 修订后方向清单

相对提案方：主线从「levenshtein 低信息门限」改为「队列噪音闭环」；Checklist 节从 T2 砍掉；F3 改处方；boost 降级；索引重建和 global 路径上调。

### P0 / 本轮就做（小、真、堵住负循环入口）

1. **F6** `queries_block` 单行折叠 + 截断 200  
2. **F5** `RoutingPendingStore` 补 `cross_process_lock`  
3. **pending 低信息过滤（P2 原案的薄版，不砍）**  
   与 matcher 共用规则：泛词 / 单 token / 纯斜杠无载荷的 `no_match` 与弱匹配不入队。日配额按 `query_hash` 计，不按 `(hash, skill_id)`。  
4. **promote CLI 文案**  
   补：`vibe skills index`；3 行人审（改 name、确认单一工作流、写「何时不用」）。**不写进 SKILL.md。**  
5. **F3 改处方**  
   name → `draft-{cluster_id[:8]}`（或同等非 query 标识）；description 保持 provenance（已满足必填）。禁止把代表 query 写进 description。

### P1 / 紧接着（路由质量，剂量要小）

6. **末层泛词门限**（不是字符下限）  
   仅 Stage 4；双 token 或长特异 token 才给分。回归集见问题 2。  
7. **先核实 `/review` EXPLICIT**  
   查 dogfood 当时的 candidate 集与 `~/.grok/skills` 未入发现路径。能修发现/slash 就不要用门限硬扛斜杠指令。  
8. **`vibe skill add` 成功后重建语义索引**  
   Phase 6 从「冒烟」改成「索引 + 冒烟」；失败要红，不能只打「No direct match (this is OK)」。  
9. **拆 feedback-collect 的 boost 分支**  
   留 decay + early-stop + watermark。不改形。

### P2 / 加固

10. **F2** assert → 显式守卫 + skip（对齐 `-O` 先例）  
11. **triage_recall** 最低余弦阈值（fail-open 保持）  
12. **global 安装路径**  
    统一到发现路径里的一处（建议 `~/.vibe/skills` 或 `~/.config/skills`），改 installer、promote 文案、CandidateManager，三处一起改。  
13. **auto_routing `learn()` 加闸**  
    至少排除 `_WEAK_MATCH_LAYERS`，或要求显式 accept 才落盘。这比拆 boost 更能阻止垃圾 instinct。

### P3 / 有基线再动

14. **P0 装 oneshot-web-spec**  
    先包成目录 + `SKILL.md`，copy 到**项目** `.vibe/skills/`（不要 `--global`，路径还是坏的），`vibe skills index`，`scripts/eval_routing.py` before/after。抢流量就回滚。  
15. **auto-config.yaml 发现过滤**  
16. **核实** `~/.grok/skills`、cmspark-agent 是否要进发现路径（进则单独评估，不盲加）

### 仍砍

- F1 zip 防御  
- 领域占位节（验收/反模式）  
- SKILL.md Review Checklist 节  
- 整句字符/token 数作为 levenshtein 主闸  
- 索引层再做一层内容过滤  
- skill-craft profile 机制  
- 「只调 confidence」的 boost 改形

---

## 与提案方 Tier 的主要差异

| 点 | 提案方 | 本裁决 |
|---|---|---|
| 本轮主线 | levenshtein 低信息门限 | pending 低信息过滤 + 去重按 query；门限降为 P1 且改形态 |
| P2 原案 | 砍 | 薄版留下，否则门限只改 kind |
| Review Checklist | T2 进 SKILL.md | 砍文件节，只留 CLI |
| F3 | query 派生 description | 反着做：name 去 query，description 保持稀释 |
| feedback-boost | T1 拆除（理由：gold_rate） | 拆除同意，降到 P1；理由改为 is_reliable 阈值，且不是最高杠杆 |
| skill add 索引 | 新发现、未进主清单 | P1 |
| global 路径 | T3 先验证 | 已核实，P2 三处一起修 |
| auto_routing learn | 未覆盖 | P2，比 boost 更值得动 |
| P0 装池 | T3 | 仍 T3，并补「单文件要先包目录、不要走 --global」 |

**一句话：** 负循环还没转起来，本轮不要发明新结构，先别让垃圾 query 占满 3 条日配额，也别把空壳的 name/description 变得更好匹配。
