Usage: vibe route [OPTIONS] {query}
Try 'vibe route --help' for help.
╭─ Error ──────────────────────────────────────────────────────────────────────╮
│ Got unexpected extra argument(s) (without behavior data\), citing the        │
│ structural fact that `scan_candidates` requires gold_rate≥0.60 so pure-miss  │
│ clusters can never become candidates, and that claude-code PostToolUse       │
│ capture already exists (adapters/claude_code.py:655 →                        │
│ .vibe/tool_sequences.jsonl). Verify both claims against the code. Is the     │
│ ruling sound? Did the synthesis lose anything valuable from A or B? 2.       │
│ **Feasibility of the data flow**: the M1 assembly bridge (join tool events   │
│ to route spans by session_id + time window, emit tool_call spans), outcome   │
│ signals (re-ask = strong negative etc.), the behavior-consistency gate       │
│ (tool-sequence bigram-Jaccard). Check against actual span/store code — is    │
│ the join feasible? Are the claimed consumers                                 │
│ (dashboard/aggregator/dag_rebuilder) real? 3. **Threshold philosophy**: ≥3   │
│ misses across ≥2 natural days, embedding cosine ≥0.82, bigram-Jaccard ≥0.5.  │
│ Are these defensible starting points? Any interaction with M11's             │
│ evidence-based scoring (e.g. fallback_llm queries now more common after      │
│ M11's stricter abstention — does that flood the miss pool)? 4. **Privacy**:  │
│ is the privacy design consistent with the repo's existing conventions? Any   │
│ leak path missed? 5. **Scope**: is the v1 cut right? What's the most likely  │
│ way this milestone set fails or balloons? 6. **Missing pieces**: anything    │
│ the design needs but doesn't mention (e.g. evaluation method — how do we     │
│ measure the discovery quality?; migration/compat; cost of embedding at scan  │
│ time)?  ## Verdict format  End with exactly one of: `VERDICT: PASS`,         │
│ `VERDICT: PASS_WITH_NITS` (list nits), `VERDICT: BLOCK` (list blocking       │
│ issues with reasoning). # M12 产品设计：对话中语义洞察 → 技能发现（v1）  >   │
│ 状态：待 gate15 双路评审。由两路独立对抗设计（m12-design-a.md 用户价值视角 / │
│ > m12-design-b.md 架构数据流视角）合成，关键事实基础见 m12-exploration.md。  │
│ ## 一句话  把「多次语义相似的路由 miss + agent                               │
│ 处理方式一致」自动汇聚成「发现（Discovery）」， 在看板和 CLI                 │
│ 中以证据卡片呈现，用户一键提升为项目/全局技能——全程本地、人审闸门            │
│ 不可绕过、证据不足时诚实标注而不是编造。  ## 设计裁决（两路分歧的裁定）  1.  │
│ **行为采集是核心，不是可选项**（采 B 驳 A）：用户需求原文要求「处理方式类似  │
│ →    归结为完整工作流」。没有行为数据，「处理方式类似」无从判定，且现有      │
│ `scan_candidates` 的 gold 门（span_count≥3 且 gold_rate≥0.60，gold           │
│ 只来自人工    accept）让纯 miss 簇**结构上永远成不了候选**。A 的「v1         │
│ 不采行为、靠更严阈值补偿」    会交付一个名不副实的特性。且 B                 │
│ 的关键事实已核实：claude-code 的 PostToolUse                                 │
│ 工具序列捕获**已上线**（`adapters/claude_code.py:655` →                      │
│ `.vibe/tool_sequences.jsonl`），缺的不是采集而是「装配进 span/聚类」的桥。   │
│ 2. **产品体验采                                                              │
│ A**：信任优先（误报是复利伤害、漏报自修复）、对话中零打扰、自然              │
│ 停顿点一次性提示、看板证据卡片、dismiss 粘性否定列表且反馈单向收紧。 3.      │
│ **行为证据不可用时诚实降级**（两路共识）：kimi/pi 平台可能无 PostToolUse     │
│ 等价    hook——降级为仅 query 证据 +                                          │
│ 更严阈值，卡片明确标注「处理方式：未采集」，    绝不用 query                 │
│ 相似度冒充行为证据（A 的诚实原则）。 4.                                      │
│ **三管道：采集层分工保留，呈现层强制合一**（A 裁决，B 的 M4 兼容）：         │
│ routing_pending / MissCounter / SkillSuggestionCollector                     │
│ 降为信号源；用户只面对    一个 Discovery 队列。  ## 目标数据流  ```          │
│ 对话中（零打扰静默观测）   route miss ──►                                    │
│ routing_pending（已有，原文+层+置信度）   agent 工具调用 ──►                 │
│ tool_sequences.jsonl（已有，claude PostToolUse）        │   M1               │
│ 装配桥（新增）：按 (session_id + 时间窗) 把工具事件 join 到 route span，     │
│ 折算 tool_call span 写入 spans.jsonl（消费者 dashboard/aggregator 已存在）； │
│ 同时产出结局信号：重问≈强负 / 会话完成无重问≈弱正 / 显式 accept≈强正         │
│ │   M2 离线 scan-candidates：miss query embedding Union-Find 聚类（复用      │
│ clustering.py，余弦 ≥0.82）→ miss 簇以 miss_recurrence 准入候选池            │
│ （修复 gold 门结构断点：纯 miss 簇不再需要 gold_rate）        │   M3         │
│ 行为一致性门：簇内工具序列 bigram-Jaccard 一致性 ≥ 阈值 →        候选标记    │
│ behavior_evidence: consistent / unavailable（降级）        │   M4 呈现：vibe │
│ skill discover（CLI）+ 看板「发现」页签（/api/discoveries）        │   M5    │
│ 提升：vibe skill promote <id> --activate --scope project|global        =     │
│ 写草稿 + 自动 skill add 注册；全局提升需显式隐私确认（默认 N，               │
│ 全局草稿剔除示例 query）；人审闸门不变，未审不注入 ```  ##                   │
│ 准入阈值（信任优先，宁缺毋滥）  - ≥3 次 miss，且跨 ≥2                        │
│ 个自然日（反一次性需求的核心闸门） - embedding 余弦 ≥0.82（废弃自认 CJK      │
│ 失效的 Jaccard 0.6） - 行为一致性（有行为数据时）：工具序列 bigram-Jaccard ≥ │
│ 0.5（标定后写入   RoutingConfig 惯例的配置 knob，附标定依据） -              │
│ 阈值全部进配置；dismiss 反馈单向收紧（只上调不下调）；dismiss 率持续 >50%    │
│ 上调出厂默认值  ## 用户旅程（v1）  1. 对话中：零打扰，静默观测。 2.          │
│ 候选成熟：session 结束等自然停顿点提示一次（「发现 1 个重复出现的未覆盖      │
│ 模式，查看：vibe skill discover」），同一候选不重复提示。 3. 查看：CLI       │
│ 或看板卡片 = 模式概括 + 证据强度（★/○：query 证据 / 行为证据 /    跨项目）+  │
│ 脱敏示例 query + 一致性摘要。 4. 决策：promote（写草稿→人工编辑→激活）/      │
│ dismiss（粘性，进否定列表，    同类不再浮出）/ 忽略（TTL 自然过期）。 5.     │
│ 全局提升：显式确认隐私边界（默认 N；全局草稿不含示例 query、不含             │
│ 项目标识），跨项目簇已有 [XP] 标记沿用。  ## 隐私边界  -                     │
│ 全部本地；无任何云端共享。 - query 沿用现有脱敏 + 截断 500 字符；示例 query  │
│ 仅项目级草稿保留。 - 工具序列只存工具名与参数 key（沿用 conversation_import  │
│ 的隐私惯例），   不存参数值。  ## v1 范围切割  做：行为装配桥 +              │
│ 结局信号、miss 簇准入、行为一致性门、统一 Discovery                          │
│ 队列（CLI+看板）、dismiss 否定列表、promote --activate、全局隐私护栏。       │
│ 不做：自动生成 SKILL.md 正文内容（草稿仍人工补全）、无人工确认的技能激活、   │
│ 对话中实时打断、kimi/pi 行为采集的强行适配（降级并标注）、跨用户/云端共享。  │
│ ## 里程碑  - **M1 行为桥 + 结局信号**（含 kimi/pi hook 可行性                │
│ spike；不可行则该平台   behavior_evidence=unavailable） - **M2 miss 簇准入 + │
│ 统一 Discovery CLI**（M1+M2 = 可 demo 的最小闭环） - **M3                    │
│ 行为一致性门**（依赖 M1） - **M4 看板发现页**（依赖 M2，可与 M3 并行） -     │
│ **M5 promote --activate 状态机**（依赖 M2，可与 M3/M4 并行）  ## 风险清单    │
│ 1. 误报疲劳（A 头号风险）→ 跨日闸门 + 0.82 阈值 + dismiss 单向收紧 +         │
│ 只提示一次 2. 平台覆盖不均：行为数据初期可能只有 claude-code → 诚实降级标注  │
│ 3. session join 错挂（CLI 每次 mint 新 UUID）→ M1 spike 先行验证 4.          │
│ 候选池污染 → admit-only-if-better、TTL、否定列表沿用现有机制 5. 隐私泄漏 →   │
│ 全局提升双重确认 + 示例 query 剔除 + 脱敏沿用 6. 遥测膨胀 → 复用现有 30 天   │
│ TTL / purge 惯例)                                                            │
╰──────────────────────────────────────────────────────────────────────────────╯
All key claims verified against source. Here is my review.

---

# Gate 15 Review — M12 产品设计（对话中语义洞察 → 技能发现）

## Verification of the two adjudication-critical facts

**Claim: `scan_candidates` gold gate makes pure-miss clusters structurally ineligible. — VERIFIED.**
`src/vibesop/core/observability/skill_promote.py:708` `scan_candidates` emits stable candidates only at `span_count ≥ min_cluster_size(3)` and `gold_rate ≥ 0.60` (line 777-782); the neutral zone falls through to nothing. `gold_detection.py:33` derives gold solely from `InstinctLearner.success_count ≥ 1`, and `record_outcome` callers are only the human paths (`instinct_cmd.py`, `unified.py` accept/dismiss, replay) — no automatic "agent solved it" signal. So a miss-only cluster can never reach gold_rate 0.60. **The ruling that "behavior data is core, not optional" is sound** — the requirement text ("处理方式类似 → 归结为完整工作流") literally requires behavior, and A's "v1 without behavior data, compensate with stricter thresholds" would deliver a feature whose central claim is unverifiable.

**Claim: claude-code PostToolUse capture is already live. — VERIFIED (with a line-ref nit).**
`claude_code.py:655` installs the P3 hook; the actual PostToolUse registration is at ~393-402 and rendering at ~504; the template `vibesop-tool-seq.sh.j2` pipes the PostToolUse JSON to `vibe sequence record-tool` → `.vibe/tool_sequences.jsonl` (`tool_sequences.py`, 10MB rotation, `{tool, ts, session}`, never `tool_input`). The exploration's "655" is the install branch, substance correct.

**Claim: `span_kind="tool_call"` has consumers but no producer. — VERIFIED, with an overclaim.**
`aggregator.py:173,215`, `dag_rebuilder.py:384,455` consume it; `grep` finds zero producers in `src/`. But note: `aggregator.py:173` counts tool_call spans only inside `skill_spans` (spans whose trace has a `task` span with `metadata.skill_id`). Bridged tool spans hung under a `route:` span (metadata = query/platform/mode, no skill_id) will **not** appear in per-skill metrics — only `get_pattern_sequences` (trace-agnostic, line 201) and `dag_rebuilder` will pick them up. "Consumers 已存在" is true for the discovery use case, overstated for the aggregator.

## 1. Adjudication: direction correct, one premise over-optimistic

The synthesis's core move — "capture exists, the gap is only the assembly bridge" — is right in direction but the bridge's primary join key is **currently non-functional**, not merely "risk-prone":

- `cli/main.py:745` mints a fresh UUID per `vibe route` invocation; `agent_runtime.py:430-438` mints one when `session_id is None`.
- The route hook template `vibesop-route.sh.j2` does **not** forward `session_id` — `handle_query_for_hook` is invoked with only the query.
- Tool events carry Claude Code's own `session_id` (`record_tool_event` reads `payload["session_id"]`).

So route-span `session_id` (fresh UUID) **never equals** tool-event `session_id` (Claude Code session). A join `ON (session_id, 时间窗)` yields ~0% hit rate as specified. The fix is small (the `UserPromptSubmit` payload does carry `session_id` — the mirror hook already reads it, `conversation_cmd.py:331`) but it is a **hot-path route-hook template change**, not a verification exercise. Risk #3 in the synthesis frames this as "M1 spike 先行验证" — the spike would immediately discover the premise is false; M1 must instead be scoped to *include* the route-hook forwarding change (or an explicit fallback: time-window-only join with ambiguity rejection, or join via the conversation mirror when enabled).

**What the synthesis lost from A:** the `--history`/"已闭环" observability (the one moment the system proves itself useful — A §2 stage 4), the evidence_score ordering, the 14-day cooldown downgrade, and `--mute` (distinct from dismiss). The dismiss→threshold-tightening feedback and 只提示一次 were kept.

**What it lost from B:** the unbounded-`spans.jsonl` problem (B §8: 50MB rotation) and the outcomes cap. The synthesis's risk #6 ("遥测膨胀 → 复用现有 30 天 TTL / purge 惯例") conflates the *candidate-pool* 30-day TTL with *span-file* retention — spans.jsonl today is **unbounded**, and the bridge multiplies span volume by one span per tool call. B's rotation plan was dropped and is needed.

## 2. Data flow feasibility

- **Join**: NOT feasible as specified (see above) — this is the #1 design defect.
- **Miss source ambiguity**: the synthesis's diagram feeds M2 from `routing_pending` (rate-limited ≤3/day, dedup on query_hash, pending-status only) but clustering.py clusters **spans**, and `route:` spans carry **no matched/missed flag** (metadata = query/platform/mode only) — so neither source is a clean fit. routing_pending works for the ≥3/2-day gate (the cap even acts as an anti-flood) but undercounts evidence strength (10 similar misses/day → 3 rows); spans.jsonl is unbounded but needs a way to mark miss-ness (hot-path `matched` metadata flag, or a local MissCounter hash join — salt is at `.vibe/miss_salt`, so recomputation is feasible). The design must pin this down.
- **Consumers**: real (dag_rebuilder, `get_pattern_sequences`); aggregator per-skill view won't include them (see verification above).
- **Outcome signals**: re-ask ≈ strong-negative is weak in practice — exact query_hash re-ask (pending: `generate_id(lower().strip())`; miss_counter: `" ".join(split()).lower()`) will miss most re-asks, since users rephrase. Keep it as a weak signal, don't lean on it.

## 3. Threshold philosophy

- **≥3 misses**: aligns with `min_cluster_size=3`, `MissCounter.DEFAULT_MIN_COUNT=3`, `missed_query_tracker.DEFAULT_MIN_COUNT=3`. Defensible.
- **≥2 natural days**: good anti-one-shot gate; date bucketing feasible from span/pending timestamps.
- **Cosine ≥0.82**: clustering default is 0.80 (`_DEFAULT_THRESHOLD=0.80`); 0.82 is tighter but **neither A nor B cites calibration evidence** — it's "0.80+0.02" by fiat. M11's `scripts/calibrate_index_threshold.py` precedent should apply here too, not just to behavior_sim.
- **Bigram-Jaccard ≥0.5**: consistent with the M11 bigram calibration convention (`.omx/artifacts/bigram-threshold-calibration.md`); design correctly defers to calibration.
- **M11 interaction (the flood question) — real and unaddressed in the synthesis.** `_WEAK_MATCH_LAYERS = {levenshtein, custom, fallback_llm}` (routing_pending.py:506); FALLBACK_LLM is a terminal no-match → it lands in `MissCounter` (unlimited, no rate limit) and routing_pending. M11's stricter abstention (keyword anchor gates, 0.35 abstain floor, `keyword_anchor_cap` below min_confidence — all in config/manager.py) demonstrably pushes more queries to FALLBACK_LLM. The discovery pool will therefore see more, not fewer, misses post-M11. This is *useful* signal but the design gives no baseline-volume estimate and no miss-rate-by-layer monitor (B's R6 covers candidate-pool contention only). Recommend: layer-share breakdown in ScanSummary before and after launch; treat FALLBACK_LLM-heavy clusters with extra suspicion (agent handled via generic LLM, not a consistent workflow).

## 4. Privacy

Consistent with repo conventions — verified: `redact_sensitive` + 500-char truncation, MissCounter salted hash (miss_counter.py header), tool keys-only (`conversation_import.py:16`), tool-seq hook "NEVER tool_input", purge paths. The global-promotion guard (default N, global drafts strip example queries) is **stronger** than today's promote and well-placed. Two nits:
- Route-span metadata truncates query to **200** chars, not 500 — the design's "沿用 500 截断" is slightly off; harmless but should match reality.
- The tool-seq hook already stores the platform session id; the bridge's richer join (session + time) doesn't expand the capture surface, only the span side. No new leak path found beyond those the design itself documents.

## 5. Scope

The v1 cut is right and the "auto-skill-factory" guard (A §6) is the correct monster to avoid. Most likely failure modes:
1. **The join (above)** — if M1's bridge under-delivers, M3's behavior gate is moot and the feature silently degrades to query-only discovery, which the synthesis itself ruled "名不副实". This is the highest-probability balloon/fail point.
2. **Cold start** — for a solo user, ≥3 misses across ≥2 days with cosine 0.82 matures over weeks; the design doesn't set expectations or use backfill from existing route spans in spans.jsonl (B mentions old-span degradation but not backfill seeding). 
3. **Global promote quality** — a skill discovered from one project's miss pattern is project-jargon-rich; nothing requires cross-project evidence ([XP]) before global promotion. Privacy is guarded, quality isn't.

## 6. Missing pieces

- **Evaluation method (biggest gap).** No discovery-quality metrics/exit criteria beyond dismiss-rate. The repo has a strong eval precedent (`tests/benchmark/routing_eval*.yaml`, M11 extended 91.6%); the design should add: (a) synthetic injection tests (A has the 同日/跨日 pair — good, keep), (b) a labeled discovery corpus for precision/recall, (c) post-promote "did the promoted skill later route-hit ≥5 times" as the closed-loop precision metric (A only uses it for `--history`), (d) milestone exit gates.
- **Embedding cost at scan**: clustering is O(n²) pairwise cosine over distinct task_keys (clustering.py:251 comment — not bounded); misses accumulate fast; ~20ms/route embedding. B's `--days 30` / `--limit` mitigation is not in the synthesis.
- **`--activate` internal contradiction**: "promote <id> --activate = 写草稿 + 自动 skill add 注册" vs. the scope cut "不做无人工确认的技能激活" and "人审闸门不可绕过". If `--activate` registers an unedited draft, it bypasses the review gate the whole design rests on. Must require a "draft materially edited since materialization" check (or explicit `--force`) before registration. Also `draft-<cluster8>` placeholder names are designed *not* to route, so an auto-registered unedited draft is dead weight, not just a trust violation.
- **Dashboard-vs-CLI mutation conflict**: A's journey has dashboard promote/dismiss buttons; B explicitly forbids mutation endpoints in the dashboard ("保持 CLI 唯一入口"). The synthesis carries both and never rules. Decide (recommend B's CLI-only, dashboard read-only — it preserves the review gate).
- **Migration**: B's `activated` status + old-binary row-skip is sound and cheap; the synthesis dropped it — keep at least the "new status value" note.

---

## Verdict

`VERDICT: PASS_WITH_NITS`

Nits (priority order; #1-#2 are near-blocking and should be resolved before M1 work starts):

1. **Session join premise is verifiably false today.** Route spans mint fresh UUIDs (cli/main.py:745, agent_runtime.py:433) and the route hook doesn't forward `session_id` (vibesop-route.sh.j2), while tool events carry the platform session. M1 must scope the *route-hook session_id forwarding change* (small, precedent exists in mirror hook) or an explicit alternative join (time-window-only with ambiguity rejection / conversation-mirror join), not merely a "verify hit rate" spike.
2. **Pin the miss-query source.** routing_pending is rate-limited/deduped (undercounts evidence); spans.jsonl route spans carry no matched flag. State which one feeds M2 and how miss-ness is determined, or add a `matched` metadata flag.
3. **Resolve the `--activate` contradiction** — require an edited-draft check before registration so "人审闸门不可绕过" holds.
4. **Add an evaluation plan**: synthetic injection tests + labeled discovery precision/recall + post-promote route-hit closed-loop metric + milestone exit gates (repo precedent: routing_eval*.yaml).
5. **Fix the unbounded spans.jsonl under the bridge** — adopt B's 50MB rotation; risk #6's "30 天 TTL" applies to the candidate pool, not span files.
6. **M11 flood guard**: monitor miss-rate by routing layer (FALLBACK_LLM share grows under stricter abstention, feeds the unlimited MissCounter); add layer-share to ScanSummary before launch.
7. **Calibrate cosine 0.82** via the existing calibrate script (M11 convention), not fiat.
8. **Global promote quality guard** — require cross-project evidence or explicit confirmation for promoting a single-project pattern globally.
9. **Restore A's `--history`/"已闭环" observability** and rule the dashboard-mutation conflict (recommend CLI-only mutations, B).
10. Minor: route spans truncate at 200 chars not 500; re-ask detection via exact hash will miss rephrased re-asks (treat as weak signal only); embedding cost at scan needs `--days/--limit` guardrails in the synthesis.
