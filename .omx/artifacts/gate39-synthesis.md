# gate39 综合裁决稿：让 gate38 的数据开口说话（r2，三路评审收敛后）

> 日期：2026-08-23 · 流程：三路独立对抗 → 综合 → claude+pi+grok 三路评审（均 PASS_WITH_NITS，0 BLOCK；9 MAJOR + 15 NIT 收敛）→ 本稿 r2
> r2 修订与正文回写同一动作完成，逐条处置见 §6。
> 前置：gate38 已交付（368ee89）。本稿范围由对抗裁决产出，与 gate38 §5 记档清单有实质偏离（backfill 砍、dashboard 推迟、新增 outcomes 出口）——偏离理由逐条在 §0.1。

## 0. 裁决总览

| 候选 | 裁决 | 理由（对抗收敛） |
|---|---|---|
| **`vibe skill outcomes` 只读出口**（Lane C 新提案） | **进，主项** | gate38 hit outcome 数据首日已攒 2437 行（cmspark 实测）但全仓零消费方；与 gate37 同构——**已有数据第一次可见**，不是 L2b 效用结论（grok-MAJOR 叙事降格）。用户可感知收益：高 |
| bridge dev/prod 文件名镜像 | **进，搭车，单独 commit** | A/B 双进：唯一正在产生错误数据的正确性 bug（写侧显式 storage_path 绕过 dev 检测，:273）；C 的"用户零感知"成立但不妨碍修测试卫生债 |
| RetentionPolicy 死代码删除 | **进，搭车** | 三路同进：说谎的死代码（retention.py:113 广告 auto-archive 与 gate38 后世界矛盾）+ "?" 词表冲突的一半 + apply_auto_actions 无人把守的自动处置暗道 |
| verdict backfill | **砍** | B/C 双否：(a) 答错问题——verdict 测 trigger 召回（promote_verifier.py:11-12），不是用后价值；(b) 时空错位（今天的 trigger/catalog × 历史 query）+ 幸存者偏差，回填行是 RULESET_VERSION 下的静默第二总体；(c) 0→5 条刷不动 ≥30；双前置的硬瓶颈实测是有机 verdict=0（pi 更正：cmspark 12 个技能全期 fire≥30，fire 那条腿头部可达——原稿瓶颈归因不实，砍除结论由 (a)(b) 独立成立）。B 的"报告式降级"（写 .omx/artifacts 不落 store）也不做——C 论证它对售后问题零贡献 |
| dashboard /api/skills/health | **推迟** | B：无需求证据（dashboard 主 tab 默认空——analytics opt-in）；披露文案搬运是真实的双口径漂移面。重议触发条件（grok-NIT 更正：原绑 L2b 前置是张冠李戴，本项是 L2-lite 只读面不依赖 verdict）：出现真实 dashboard 使用需求、且愿意把脚注披露原文打进 payload。若未来做：必须 import skill_health 禁重写谓词 + 披露原文进 payload |
| 薄样本（1≤total_routes<3）字母档 | **推迟** | A 发现硬冲突：feedback_loop.py:143-148 F-deprecate 规则要求 grade=="F" ∧ total_routes<3 ∧ days_since≥30——薄样本是该规则唯一燃料，改 "?" 即规则死亡。这是对处置规则语义的裁决，需配数据独立对抗轮。B 的反方证据（retention.py:87 uses<3 语义）随本 gate 删文件而失效 |
| 热路径 analyze_all / bridge 性能 | **砍** | 无测量不立项；bridge 在 assembly 离线阶段；记档更正（C）：spans.jsonl **无轮转机制、无界增长**（span_writer.py 只有 16384 payload 截断）——这是容量治理议题，且 bridge 单 run 成本随文件线性涨（dedup 后只有新 hit 进分类器，"平方涨"言重了，首跑回灌才是一次性平方） |

## 0.1 换皮回归自查

- outcomes 出口 vs gate34/37：非新分数、非比率、非处置派生——与 gate37"L2-lite 让数据攒得怎么样第一次可见"完全同构，是 gate38 已产数据的可视化，零写路径改动。
- backfill 砍除与 gate38 §5.2 的关系：§5.2 记档要求"立项前先裁决触发器口径"——本稿完成该裁决（不计入，且整项砍除），符合记档意图。
- 零触碰清单不变：三套 trigger 语义、双 embedding、`_is_agent_prompt_shape`、gate30 upsert、`_is_miss`/`_classify` 函数体。

---

## 1. 主项：`vibe skill outcomes` 只读出口

### 1.1 数据事实（Lane C 实测，cmspark 2026-08-23）

- `route_outcomes.jsonl` 3068 行：hit 侧 2437（`hit_session_expired` 1268 / `hit_reask_same_task_id` 1167 / `hit_session_moved_on` 2），miss 侧 631。
- outcome 行**不带 skill_id**；join 键 = outcome.span_id → spans.jsonl 的 span `id`，span metadata 取 `skill_id`。实测：span_id 命中 2437/2437，但其中 **37 行（1.5%）源 span 的 `metadata.skill_id` 为空串**（has_match=true 的旧脏 hit，双评审独立实测）——可归因 2400/2437，空 id 行跳过不计。读侧与 fire 列同谓词：非空 str 才入桶（skill_health.py:77-78 同款）。
- expired 占 hit outcome 52%（gate38 §1.2 披露的"回灌占主导、信号最弱"实证）——**三种 reason 必须分列**，否则弱阳性淹没弱阴性。
- 命名：`vibe skills health` 已被 pack 完整性检查占用；`vibe skill outcomes` 无冲突。

### 1.2 设计

- **新模块 `src/vibesop/core/skills/skill_outcomes.py`**（与 skill_health.py 同层同风格）：
  - 单次扫描 outcomes 文件 + 单次扫描 spans 文件建 span_id→skill_id 映射（两个文件各一遍）。**span metadata 是 JSON 字符串**，join 侧必须复用/镜像 `_route_hit_skill_id`（skill_health.py:68-78）的 str→json.loads 容错与非空 str 谓词——照字面 `span["metadata"]["skill_id"]` 会全量漏 join，空串 skill_id 会出空白 Skill 行；
  - 读侧纪律原样继承 skill_health.py:12-22：不持 flock、坏行跳过、file-missing→空不 mkdir；**spans 镜像 `spans_file_for` dev/prod 选择，outcomes 恒读 `route_outcomes.jsonl`**（写侧无 dev 变体——dev 下组合为 spans.dev.jsonl × route_outcomes.jsonl，已知不对称记档 §4.7，先例：execution_feedback.jsonl 同款）；
  - 只处理 `side=="hit"` 行；`population` 缺省按 hook 处理；
  - 产出：per-skill `{skill_id: {reask, moved_on, expired, last_at}}` 原始计数 + **顶层 `unjoined: int`**（claude-MAJOR：join 落空必须有可见性，防未来 spans 轮转后表静默缩水）。**unjoined 口径钉死（pi 确认轮）：unjoined = span 缺失 ∪ skill_id 空/缺，且对账式 Σper-skill 三列 + unjoined = hit 行总数**——防实现期把 unjoined 收窄成仅 span 缺失而让 37 行再次静默消失；
  - **`last_at` 钉死取 outcome 行的 `span_ts`**（grok/claude-MAJOR：回灌行 recorded_at 全是回灌当天，用之则 Last 列恒同一天=撒谎；span_ts 缺失则该行不更新 Last）；
  - **排序钉死 `skill_id` 字典序**（grok-MAJOR：按 reask/total 降序就是弱负排行榜；字典序测试可复现）；
  - **无比率、无百分比、无 grade、无处置派生**。
- **CLI**：`vibe skill outcomes`（独立子命令，挂 skill 单数组；命名无冲突——`vibe skills health` 是 pack 完整性检查）。表格列：Skill / Reask / Moved-on / Expired / Last + unjoined 末行。`--json` 提供，schema raw counts only。脚注沿用 skill_commands.py:205-220 体系 + gate38 弱信号披露，r2 修订后全文：
  - 「**同源 spans，但路径（本表仅 hook vs fire 列含 CLI）与时间窗（本表全量 vs fire 列 30d）皆不同，禁止拼比率**」（claude-MAJOR + pi 确认轮更正：『子集』亦不严格——时间窗错位使 reask 全量可超 30d fire）
  - 「三种 outcome 分列：reask=同任务重问（弱负；**证据含任意路径后续路由**），moved_on=会话推进（弱正），expired=24h 无证据到期（最弱；cmspark 实测回灌占主导 1268/2437）」
  - 「**三列均为下界计数**（task_id 由 query 全文派生，改述即换 id）；**原始计数跨技能不可比**（fire 基数不同）」
  - 「原始计数，n<30 不下结论；不再回来 ≠ 满意，也可能是放弃」
  - 「空 skill_id 的脏 hit 行跳过（cmspark 实测 37/2437）；unjoined 计数见末行」
- **gate38 披露双挂点补票**（pi-MAJOR）：`vibe skill list` 的 fire 列脚注（skill_commands.py:209-214）随主项同一 commit 加一行「与 outcomes 口径不同（含 CLI、30d 窗），禁止拼比率」——gate38 §1.2 裁定的双挂点只落了一半。
- **测试**（tests/core/skills/test_skill_outcomes.py + CLI 侧）：
  - 合成 spans + outcomes fixture → 计数与手算一致；三 reason 分列；排序=字典序；
  - **混合 fixture**：部分 outcome 的 span 不存在 + 部分 span 的 skill_id 为空串 → unjoined 计数可见且准确、表中无空 id 行（双锁：只测『跳过』不够，要测『落空可察觉』）；
  - miss 行（无 side 键）不进任何技能计数；recorded_at 与 span_ts 不同的行 → Last 取 span_ts；
  - **must-NOT**：输出任何位置（含 --json）无比率/百分比/grade 键；
  - file-missing 双文件各自 → 空表不抛；坏行/坏 metadata JSON 跳过；dev 模式读 spans.dev.jsonl × 恒 route_outcomes.jsonl（pin 一次）。

### 1.3 明确不做

- 不给 hit outcome 行加 skill_id 键（动写路径，违背纯只读定位；join 一次顺序扫描的成本 skill_health 已在付）。
- 不做 dashboard 接线（§0 推迟）。
- 不做时间窗过滤参数（30d 窗口留给有需求时；首版全量计数 + last_at 已够）。
- **不把三列加进 `vibe skill list`**（grok-NIT：与 Fire 30d 并排即视觉拼比率，脚注拦不住）。CLI 形态锁死独立子命令，理由（pi-NIT 固化）：list 表已 8 列 3 脚注且行集不同域（安装技能 vs 有 outcome 技能），独立命令降低并置诱惑面。
- §0『第一个回答出口』叙事降格（grok-MAJOR）：与 gate37 同构的是『已有数据第一次可见』，**不是** L2b 效用结论——文档与 CHANGELOG 按此措辞。

## 2. 搭车项 A：bridge dev/prod 文件名镜像

- `tool_call_bridge.py:130` `SPANS_FILENAME = "spans.jsonl"` → 解析函数 `_spans_filename()`（`"spans.dev.jsonl" if is_dev_environment() else "spans.jsonl"`，与 span_writer.py:65 / skill_health.py:41-47 同谓词）；使用点 :229（读）与 :273（写，显式 storage_path 绕过 SpanWriter :64-69 自检——双错）一处调用。
- 只镜像文件名选择，**不镜像** skill_health 的 exists-gate（bridge 写侧需要路径即使在文件缺失时）。
- **fixture churn 预警（Lane A）**：pytest 下 `is_dev_environment()` 为真（span_writer.py:55 自述 auto-detect pytest），改后 test_tool_call_bridge.py 现存 fixture 文件名全部失配——fixture 统一改经 `_spans_filename()` 或写 dev 文件 + 一条 dev/prod 选择正例 pin。
- 不搭车扩到 dashboard/server.py 的五处同型硬编码（:137,:195,:296,:330,:344）——独立技术债，记档 gate40。
- 行为变化仅限 dev 环境；prod 路径逐字节不变。

## 3. 搭车项 B：RetentionPolicy 死代码删除

- **整文件删除** `src/vibesop/core/skills/retention.py`（`RetentionPolicy` :51-190 + `DeprecatedRetentionSuggestion` :26-48 一并）+ `tests/core/skills/test_retention.py`。
- 代码引用三处（已核实）：`core/routing/candidate_manager.py:265` 注释、`feedback_loop.py:122` docstring、`evaluator.py:86` 的 "?" 词表互指（gate38 双向指引，删一侧收另一侧）。
- **文档引用四处（三路收敛，点名进删除 commit，不靠 grep 兜底）**：GOALS.md:48 与 :105、docs/architecture/skill-runtime-interface.md:265/:266（weekly 触发建议）与 :341（类→文件映射表行）。
- 兜底 grep 模式收窄（grok-MAJOR：原模式误伤活符号）：`RetentionPolicy|DeprecatedRetentionSuggestion|vibesop.core.skills.retention`——不得碰 `RetentionSuggestion`（feedback_loop 活符号）、`retention_actions`、`span_retention_days`、skill_promote 的 retention-pool。
- `apply_auto_actions`（retention.py:152-179）暗道随文件消失——删除即排雷。
- CHANGELOG 点名（破坏性变更：公开符号消失）。

## 4. 记档（gate40 候选）

1. dashboard server.py 五处 spans.jsonl 硬编码（:137,:195,:296,:330,:344）。
2. 薄样本字母档独立对抗轮（含 F 规则唯一燃料冲突的处置语义裁决）。
3. spans 无轮转、无界增长的容量治理（更正 gate38 §5 的"平方涨"表述）。
4. evaluate_skill 三读 records（evaluator.py:172/:204/:205）+ optimization_service 每 match 调用的性能（gate38 §2.5 边界内，需测量先行）。
5. verdict backfill 的永久否决理由（本稿 §0）——未来任何人重提需先反驳：答错问题/时空错位第二总体/有机 verdict 才是硬瓶颈。
6. hit 写侧空 skill_id 活洞（实测 37/2437：has_match=true 但 metadata.skill_id==""，agent_runtime.py:668 写 `result.skill_id or ""`）——本 gate 读侧跳过即可，写侧守卫另立项。
7. outcomes 文件无 dev 变体的已知不对称（execution_feedback.jsonl 同款先例）——防未来误当 bug 修。

## 5. 实施纪律

- 单 gate 分 commit：主项 / bridge 镜像 / 死代码删除各自独立。
- 新碰文件 ruff check + format 双净；存量 lint 不顺手修；测试禁内建 hash()。
- 全量 pytest 基线 6218 passed/14 skipped（RetentionPolicy 删除后相应减少）；orbstack e2e 基线 smoke 68/68 + routing 7/7。
- 文档同步：CLI_REFERENCE（outcomes 命令 + 脚注体系）、CHANGELOG（含 RetentionPolicy 破坏性变更点名；叙事按『数据第一次可见』非『效用结论』）、§3 点名的四处 RetentionPolicy 文档引用、check_docs 双 checker。
- 三路评审（设计稿级 claude+pi+grok）→ 实施 → 双路复审（claude+pi）→ push。

## 6. 三路评审收敛记录（r2）

| 来源 | finding | 处置 |
|---|---|---|
| claude-MAJOR | 『总体不相交』事实错误（子集关系，可证伪） | 采纳→§1.2 脚注改写 |
| claude-MAJOR | join 落空无可见性（轮转后静默缩水） | 采纳→顶层 unjoined 计数 + 混合 fixture 双锁测试 |
| claude-MAJOR / grok-NIT / pi-NIT | RetentionPolicy 文档引用未枚举 | 采纳→§3 点名四处 |
| grok-MAJOR / pi-MAJOR | 空 skill_id 脏 hit 37/2437 未裁决 | 采纳→读侧同 fire 谓词跳过 + 披露 + §1.1 数字更正 2400/2437 + 写侧洞记档 §4.6 |
| grok-MAJOR / claude-NIT | last_outcome_at 未钉 span_ts | 采纳→§1.2 钉死 span_ts |
| grok-MAJOR | 排序未钉=弱负排行榜；叙事过强 | 采纳→字典序钉死 + §1.3 叙事降格 |
| pi-MAJOR | fire 列脚注双挂点只落一半 | 采纳→§1.2 随主项同 commit 补 |
| claude-NIT | metadata 是 JSON 字符串，照字面取全漏 | 采纳→复用 `_route_hit_skill_id` 谓词 |
| claude-NIT / pi-NIT | outcomes 无 dev 变体不对称未记 | 采纳→§1.2 显式组合 + §4.7 记档 |
| claude-NIT / pi-NIT×2 | reask 下界/含 CLI 证据/跨技能不可比 | 采纳→§1.2 脚注三句 |
| pi-NIT | backfill 瓶颈归因不实 | 采纳→§0 更正，结论不变 |
| pi-NIT / grok-NIT | CLI 形态无理由 | 采纳→§1.3 锁死独立子命令 |
| grok-NIT | dashboard 重议条件张冠李戴 | 采纳→§0 改写 |
| grok-MAJOR | 兜底 grep 模式误伤活符号 | 采纳→§3 收窄 |
| grok-NIT | F 规则完整引用 :143-147；路径写全 | 采纳→文内修正 |
| claude-NIT | cmspark 实测数字留验收快照 | 采纳→验收环节执行 |

### r2 确认轮（pi）

| 来源 | finding | 处置 |
|---|---|---|
| pi-MAJOR | §0 叙事未实际降格（§1.3 点名了 §0 但 §0 原样存活） | 采纳→§0 裁决行改写 |
| pi-NIT | 『子集关系』不严格（时间窗错位） | 采纳→脚注改『路径+时间窗皆不同』 |
| pi-NIT | unjoined 口径未钉死 | 采纳→§1.2 对账式定义 |

### r2 确认轮（claude + grok，与 pi 修订交叉核对）

| 来源 | finding | 处置 |
|---|---|---|
| grok-NIT / claude-NIT | 删『子集关系』括号断言，脚注只写事实差异 | 已被 pi 修订满足（现文=『路径+时间窗皆不同』），记录 |
| claude-NIT | unjoined 边界（空串行计入否） | 已被 pi 修订满足（∪ 定义+对账式），记录 |
| claude-NIT | §4.3 漏现存 prune 释放阀 | 采纳→§4.3 补 |
| grok-NIT / claude-NIT | F 规则完整引用 :143-148 含 days_since；fire 脚注块 :209-214 | 采纳→文内修正 |
