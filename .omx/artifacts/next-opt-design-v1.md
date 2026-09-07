# 下一步优化设计（锁 v1）— 图书管理员先可信

> 状态：吸收三路对抗后的锁。实现以本文为准，v0 作废。
> 上游：v0 固件 + `.omx/artifacts/next-opt-review-synthesis.md`
> 日期：2026-09-07

## 0. 一句话

先停止误注入和自动专家计划；**打了标的方法卡**默认点名才打开；并行工人只走显式入口；剩下的格子用实验判决，整机流水线不做成本周期产品。

## 1. 前提（与 v0 相同，补一句锁）

P1–P6 成立性见合成。补：P3 是历史探针，CI 锁已松，D3 是补锁不是锦上添花。P4 是社区文献综合，不是自家「点名 vs 八专家」A/B。

## 2. 锁定命题（已降调）

L1. **带 `disable-model-invocation` 的卡**对非 EXPLICIT 路径默认不注入。未打标的卡本周期仍可被自动路由（缺口 W1.1）。找不到匹配是成功。
L2. 并行工人 ≠ 专家委员会。禁止角色词自动拉小队或等价 Execution Plan。
L3. 本周期 **不增长** 执行层专家编制。不声称增量只可能在设计/信息层（那是 E2 的事）。
L4. 整机「设计院→施工队」是假设。E4 没绿，禁止做成 CLI / 默认编排。
L5. 本周期：**撤回**已上线的角色词小队 auto-trigger；**冻结增量** SkillMarket / 协同过滤 / 主动推荐专家。自动 deprecate 维持 gate38（显式 flag），不标 won't-do。

## 3. W1 契约

### D1. disable-model-invocation

- 一等字段 `SkillSpec.disable_model_invocation: bool = False`；解析 `disable-model-invocation`。
- parser `build_spec` 白名单必须映射该 kebab 键，并 stamp 进 candidate dict。禁止只写 metadata 当过滤源。**禁止**为了收未知键去改 `SkillSpec.extra` 为 forbid/allow。
- **过滤缝**：不要用 `filter_routable`（它在 EXPLICIT 之前，会杀死点名）。复用 `filter_management_candidates` 模式——EXPLICIT 看见全量池；SCENARIO/INDEX/KEYWORD/AI_TRIAGE/EMBEDDING/FALLBACK 及 orchestrate/squad 步骤分配剥掉该旗。
- EXPLICIT 实际语法以 `explicit_layer.py` 为准（`/id`、`!id`、`use|run|execute|try id`）。v0 写的 `@skill_id` 和 `vibe route --slash` **不是**技能点名通道；单测覆盖「点名 + 角色词」仍走 EXPLICIT。
- **fail-closed**：非 EXPLICIT 若仍带上该 id——单技能路径 demote 且不得发 `[ACTIVE SKILL]`/`NEXT STEP`；**orchestrate/squad 路径必须剥 `plan.steps` 里的该 id，剥空则走 no-match 信封**，不得复用「mode!=orchestrate 才 demote」的旧空正文逻辑。
- **作用域**：D1 保证的是 **vibe 路由与注入层**。`vibe build` 副本必须原样透传该字段（pin 测试）。对没有该语义的平台副本树（Pi/Kimi 等）：W1 在设计里声明「透传字段 + 不从副本树删除」（避免一次做完部署面）；W1.1 审计平台原生自动调用。不得在文档里写成「全宇宙不可见」。
- 不隐式改写上游社区卡。

### D2. 拆角色编制，留下显式并行入口

**拆除（必须同时拆，只删 ROLE_KEYWORDS 不算完成）：**

1. `ROLE_KEYWORDS` 条数 ≥2 → `MULTI_AGENT_SQUAD` 快路径。
2. 短查询 `suggested_roles>=2` / `complexity in (composite, multi_agent)` → `ORCHESTRATE`。
3. `_decision_from_analysis` 的 `squad_needed` / `complexity==multi_agent` → SQUAD，以及「实现/审查」类 facet 计数导致的 composite→ORCHESTRATE。
4. LLM 分析 prompt 里「2+ DIFFERENT roles → squad_needed」的角色表，不得再按架构/实现/审查/测试计数。
5. 默认长句 → ORCHESTRATE 不得再作为「没认出角色也开会」的兜底。无并行意图的日常句 → `SINGLE`。

**保留：**

- 真有序多意图（「先调研再实现」这类顺序标记）仍可 `ORCHESTRATE`，但是 **workflow 步骤，不是专家角色绑定**。
- **显式入口清单**（hook 无 flag，必须写进用例）：
  - CLI：`vibe orchestrate --strategy parallel` / `--pattern parallel` / `--agents` 仍到达并行编排；squad CLI 确认闸保留。
  - Hook / 自然语言：仅当同时出现 (a) 并行/独立上下文/多窗口工人 等词，(b) ≥2 个已命名工作项。小词典 **禁止** 含实现/审查/测试/架构。
- 回归金标随契约改。验收必须打 `IntentInterceptor.should_intercept(...).mode` **且** `handle_query_for_hook` 文本，不能只打 `AgentRuntimeResult.mode`（squad 会被改写成 orchestrate）。
- 「实现+审查」类 query：不得 SQUAD，**也不得**因此注入 Execution Plan。
- 文档：USE_CASES 中英、`docs/architecture/routing-system.md`、ARCHITECTURE、ROADMAP v7 auto-trigger 条目、CHANGELOG 记行为变更。

### D3. 负例闸（两层，字段名跟代码走）

**YAML 层**（`router.route`，不经 interceptor）：

- 同一 `routing_eval.yaml`，`category: must_not_inject`，裸 `expect: []`，禁止带 `reject`。
- 最低集可增不可减：写公众号总结；写一篇微信文章；翻译这段英文；今天天气怎么样；帮我出一道考试题，不要实现；乱码条保留。
- 该 category 的 ok1：**primary 为空且 layer 不是 fallback_llm**。
- `--update-baseline --force` **拒绝**吸收该类 true→false。CI 必须 `--hermetic --check`。该类条目 **不得** 进入 baseline known-fail；ok1 必须全真。
- 从已有 `scripts/ai_triage_probes.yaml` 抽翻译/总结/闲聊进 hermetic，不要另起更弱故事。YAML 只声称 hermetic 层不误命中。

**Runtime 层**（`handle_query_for_hook` → `to_hook_response`）：

- 探针原句必须包含方法论里的伤害句「写公众号总结」。
- 不得出现：`Execution plan injected`、`[VibeSOP Execution Plan]`、`[ACTIVE SKILL]`。
- `plan.steps` 不得含非空、非 `fallback-llm` 的 `skill_id`。
- 无 LLM 的 hermetic 未必长出四角色：用 mock `IntentAnalysis` 钉「日常长句被标成 squad/orchestrate」。
- 断言字段：`systemMessage` / `hookSpecificOutput.additionalContext` / `plan`。不存在的键 `skill_content` 不得当闸。

### D4. 不碰

- 不实现整机 CLI。
- 不批量改社区技能正文。
- 不把 LLM 评审做成常驻默认注入。
- 不删 `vibe instinct auto-promote`。但契约写明：它已经能经 `apply_instinct_boost` 改 primary（加分不是注入）。本周期不把它接到正文注入，也不宣传「与路由分已划清」。

### D5. 生成规则文案（原 Q5，升格必做）

- 改适配器**模板源**（`adapters/_generation.py`、`grok_build.py`、kimi/pi/claude 模板），再 `vibe build` 刷新生成物。
- 口径：路由仍建议跑（图书管理员查目录）；**no-match 是正常输出**；禁止「find the best skill / 必须匹配」。
- 命中时 `[ACTIVE SKILL] MUST follow` 可保留（只在真命中）。
- no-match 现有 `Proceeding in normal mode` 可作基准。
- 验收 grep（负向+正向）：生成树（含 `AGENTS.md`、`.grok/rules/routing.md` 及 kimi/pi/claude 对应生成物）不得再出现「find the best skill」作为强制匹配口径；必须出现「no-match 是正常输出」或等价英文（`Proceeding in normal mode` / `no-match is a successful outcome`）。

## 4. W2 实验轨（不阻塞 W1）

同 v0：E1 弱模型路由质量；E2 信息型技能 A/B；E3 三臂 dump vs route；E4 整机（硬依赖 R8 盲评）。不把未做实验写成产品功能。

## 5. 文档轨（W1 合并时）

- ROADMAP：撤回 squad auto-trigger 完成叙事；SkillMarket 未完成子项冻结增量；处理 `ROADMAP.md` 里 SkillMarket「50+ packs」类未来指标（不再当本周期目标）。
- GOALS.md：本周期冻结协同过滤/市场扩张，留痕。不默默改口。
- CHANGELOG：D2 行为变更（v7 已发布特性）。
- architecture 决策树不再把 ≥2 ROLE_KEYWORDS 当正典。
- 方法论正文不改，除非与 D1–D5 冲突（当前无）。

## 6. 验收

- 夹具技能 `disable-model-invocation: true`：非 EXPLICIT 永不 primary；EXPLICIT 可以；点名+角色词仍 EXPLICIT。
- 「实现+审查」：interceptor 非 SQUAD，hook 无 Execution Plan。
- 「写公众号总结」：hook 无 Execution Plan / ACTIVE SKILL，plan.steps 无真实 skill_id。
- must_not_inject YAML 全绿且不得经 fallback 过关。
- 生成规则 grep：不得再出现「find the best skill」作为强制匹配口径。
- `vibe skills info` 显示该字段（C 路 NIT，升为 W1 小项，避免「技能神秘消失」）。

## 7. W1.1 欠条（不进 W1 最小集，必须留痕）

- 点名了但不存在的技能 → 干净 no-match，而不是 fallback-llm 编造（原 Q4）。
- 平台原生技能面（Claude/Pi/Kimi 副本树自动调用）审计。
- OpenCode 插件自猜 `skills/<id>/SKILL.md` 路径是否尊重 disable 字段。
- 泛化 unknown-key 保留（W1 只映射这一个 kebab 键）。

## 8. 非目标

同 v0，外加：W1 不解决平台原生技能面绕过（声明作用域 + 透传字段即可）。
