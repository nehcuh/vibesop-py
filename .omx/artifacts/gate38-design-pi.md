Usage: vibe route [OPTIONS] [query]
Try 'vibe route --help' for help.
╭─ Error ──────────────────────────────────────────────────────────────────────╮
│ Got unexpected extra argument(s) (列含 CLI、hit outcome 不含                 │
│ CLI\双总体矛盾，docstring 披露是否足够？还有更优解吗？    c. `optimize       │
│ --apply` 起死回生（A 案）而非删除（B 案）：哪个对？ 4.                       │
│ **证据核查**：设计稿中的 文件:行号 引用抽查至少 10                           │
│ 处，确认真实存在且含义相符（尤其 evaluator.py:64-66                          │
│ 零样本分支、feedback_loop.py:66/196-204/208/246、optimize_cmd.py:106/140-157 │
│ 死代码断言、tool_call_bridge.py:414-539、agent_runtime.py:620-626/667-700、c │
│ li/main.py:899-936/1700-1721、eval_routing.py:174 恒 return 0、ci.yml:110    │
│ continue-on-error 先例、release.yml:15-21 workflow_call）。 5.               │
│ **完整性**：设计有没有漏掉的消费者/调用点（全仓 grep                         │
│ `.grade`、`analyze_all`、`quality_score`                                     │
│ 兜底）？测试计划能否抓住声称的行为？假 L2 修复的顺序依赖（先拆 auto          │
│ 再改数值）在单提交原子落地的裁定下是否还有残余风险？  ##                     │
│ 输出格式（严格遵守）  ``` ## Verdict PASS / PASS_WITH_NITS / BLOCK  ##       │
│ Findings - [BLOCK|MAJOR|NIT] 描述（附 文件:行号） ```                        │
│ 只读核查（grep/read），不要修改任何文件，不要客套。 # gate38                 │
│ 综合裁决稿：技能评价体系第二刀  > 日期：2026-08-23 ·                         │
│ 流程：三路独立对抗（Lane A 设计 / Lane B 怀疑 / Lane C 用户视角）→ 本稿裁决  │
│ → 三路评审（claude+pi+grok） > 前置：gate37 已交付（L1 lint + L2-lite 健康列 │
│ + L4 流程修复，80a3398）；本稿三项均为 gate34/gate37 明文 deferred           │
│ 项，非换皮。  ## 0. 裁决总览  | 项 | 裁决 | 关键分歧与裁定 | |---|---|---| | │
│ L2a top_skills | **做**（additive span metadata） | C                        │
│ 主张砍（无消费方）；A/B 主张做。裁定做——理由见 §1.0 不可逆性论证 | | L2a hit │
│ outcome | **做**（仅非 CLI hit，`side:\hit\`） | B 揭示 CLI                  │
│ 总体矛盾；裁定：镜像 miss 侧排除 CLI，口径披露写进 docstring，不与 fire      │
│ 列拼比率 | | 假 L2 处置 | **做**，按 A 方案 + B 顺序纪律 | 详见              │
│ §2；`optimize --apply` 起死回生（A 案）而非删除（B 案），理由见 §2.4 | |     │
│ report-only CI | **做**，含 requires_packs schema | C                        │
│ 主张主集先行；裁定：同一 gate 内分两个实施步，主集 job 先落地验证再动        │
│ extended | | Lane C 新提议 ×2 | **不纳入 gate38**，记档 gate39 候选 | 见 §5  │
│ |  ## 0.1 换皮回归自查  - 对照 gate34 不做清单（gate34-synthesis.md）：无    │
│ intake 过滤、无阈值工程、无硬阻断、无 hash chain。 - 对照 gate37 §4：L2a     │
│ 是裁决 2 显式留 gate38 的项；report-only CI 是裁决 4 deferred                │
│ 项且**非**硬阻断换皮（`continue-on-error` + exit 恒 0 + skipped 透明）；假   │
│ L2 处置是修订 C                                                              │
│ 点名待议项，且本稿**删除**自动处置而非新增评价维度——无比率、无新分数、无上卡 │
│ ，与\永久不做自动降级\同向。 - 零触碰清单：三套 trigger 匹配语义、双         │
│ embedding 分离、`_is_agent_prompt_shape`、gate30                             │
│ upsert、`_is_miss`/`_classify` 函数体。hit 分类器是新函数，miss              │
│ 侧既有测试零改动即冻结证明。  ---  ## 1. L2a 仪表化  ### 1.0 top_skills      │
│ 的裁决理由（C 主张砍，裁定做）  C 的\无消费方\是事实（L2b 前置 verdict≥30    │
│ 且单技能月 fire≥30，cmspark 现 verdict=0）。但存在不对称：**hit outcome 可从 │
│ spans 历史回填（派生数据），top_skills                                       │
│ 不可回填（写时数据）**——现在不记，未来 L2b 启动时永远缺这段历史。成本侧 B    │
│ 已逐点核查：生产点只是 dict 加 key（候选列表 `result.alternatives`           │
│ 本来就算出，eval_routing.py:80 在用）；序列化微秒级，远离 16384 截断与 100µs │
│ p95 门；全部 8 个 metadata                                                   │
│ 消费点（gold_detection.py:151-163、tool_call_bridge.py:368-394、skill_health │
│ .py:68-78、replay_routing_baseline.py:68-124、clustering.py:454-457、aggrega │
│ tor.py:146、dashboard server.py:137+ 等）均为容忍式解析，additive            │
│ 安全。纪律约束：任何读者在 L2b 前置满足前**不得**用 top_skills               │
│ 派生比率/处置，写进模块 docstring。  ### 1.1 top_skills 实施（A 案原样）     │
│ Schema：metadata 新增 `\top_skills\: list[str]`，≤3，primary 在前 + 至多 2   │
│ 个 alternatives；无候选时**整键省略**（沿用 `layer` 缺省即 unknown           │
│ 惯例，agent_runtime.py:693-696）。  - Hook 侧：`agent_runtime.py:668`        │
│ 后插入，数据源用 :620-626 已建好的 `result.alternatives`（list[dict]，键     │
│ `skill_id`）。 - CLI 侧：`cli/main.py:906` 后插入；alternatives              │
│ 是对象列表，用 `getattr(a, \skill_id\, \\)` + isinstance(str) 过滤，沿用     │
│ :932-936 的 MagicMock 守卫惯例。 - 不改 span_writer 序列化/脱敏路径。  ###   │
│ 1.2 hit outcome 实施（A 案 + B 降级）  - 新谓词                              │
│ `_is_hit`（tool_call_bridge.py `_is_miss` 后，约 :493）：`not rs.is_cli ∧    │
│ rs.has_match is True ∧ rs.mode not in                                        │
│ (\not_intercepted\,\slash_command\)`。CLI 排除与 miss 侧同原理（one-shot     │
│ session 只会衰变成 24h 空洞弱阳性，:470-487）。docstring 按 gate17           │
│ 惯例交叉引用 `_is_miss`。 - 新分类器 `_classify_hit`（`_classify` 后，约     │
│ :540）：同 task_id 后续 route span →                                         │
│ `(\weak_negative\,\hit_reask_same_task_id\)`；同 session 后续不同 task span  │
│ → `(\weak_positive\,\hit_session_moved_on\)`；年龄 > SESSION_COMPLETE_HOURS  │
│ → `(\weak_positive\,\hit_session_expired\)`；否则 None。**不接               │
│ accepted_queries**（explicit accept 是 miss 专属语义）。reason 一律 `hit_`   │
│ 前缀，与 miss 词表不相交。 - 新函数                                          │
│ `_derive_hit_outcomes`（`_derive_outcomes` 后）：镜像 :414-467——同一         │
│ outcomes 文件、同一 span_id 去重、plain append、不加新锁（sole-reader        │
│ 前提不变）。行 schema 加 `\side\:\hit\`；miss 行不回写，reader 以 side       │
│ 缺省=miss 处理。 - 接线：`_run` :221 后一行；`BridgeStats` 加                │
│ `hit_outcomes_recorded: int = 0`。 - **B 的降级要求（采纳）**：模块          │
│ docstring（:32-47，现声明 miss-only，不改会说谎）补 hit 段落 + 两条披露：(a) │
│ hit outcome 仅覆盖 hook 路径，与 gate37 fire 列（含                          │
│ CLI）总体不相交，**禁止**拼\fire→成功率\比率；(b) hit 弱阳性比 miss          │
│ 更虚（不再回来 ≠ 满意，也可能是放弃），不得当 ground truth。 -               │
│ **存量回灌披露**：首次运行会把全部历史 hit 一次性派生进                      │
│ route_outcomes.jsonl（write-once + span_id 去重保证幂等），CHANGELOG 点名。  │
│ - bridge 读 SPANS_FILENAME 硬编码不镜像 dev/prod                             │
│ 是**既有缺口**（:97,:195），本 gate 不改，记档。  ### 1.3 L2a 测试           │
│ tests/core/observability/test_tool_call_bridge.py（:497 有 miss e2e          │
│ 先例）：hit+同 task 重问→恰好一行 weak_negative/side==\hit\；session moved   │
│ on→weak_positive；新鲜 hit→无行且二次幂等；**must-NOT**：CLI hit 永不产      │
│ outcome；has_match True/False/None 三态互不串池；**`_is_miss`/`_classify`    │
│ 既有测试零改动（冻结证明）**；坏行/坏 metadata 跳过不抛。top_skills：Hook 侧 │
│ tests/agent/、CLI 侧 tests/cli/，断言 ≤3、primary                            │
│ 在前、无候选键不存在、MagicMock 不泄脏字段、旧 span（无键）reader 计数不变。 │
│ ---  ## 2. 假 L2 处置  三路一致：做。B 补充的关键事实（全部已核）：5         │
│ 调用点中 optimize_cmd 两处实为死代码；main.py:1707 每 20 次路由在热路径自动  │
│ deprecate/archive；render.py:66 渲染函数副作用写生命周期；generate_report 使 │
│ `stale --json` 静默处置（同命令非 --json 路径却是                            │
│ False）；`_apply_boost`（feedback_loop.py:196-204）还会把 deprecated 的 A    │
│ 档**自动翻回 active**；零样本谎言链 evaluator.py:64-66→grade D→90 天 archive │
│ 规则（:155）可命中\被 record_usage 记过但零反馈\的技能——现行行为，非理论。   │
│ ### 2.1 evaluator 零样本不再撒谎  - `total_routes == 0` → `quality_score`    │
│ 返回 `0.0`，`grade` 返回 `\?\`（新词表成员=无数据）。 - 下游兼容性（A        │
│ 逐点核查 + B 独立复核）：feedback_loop 四条规则全部精确匹配                  │
│ `\F\/\D\/(\C\,\D\,\F\)`，\?\ 全不命中 → 零数据技能不再产生任何               │
│ suggestion、不可能被 auto archive；optimization_service 有 total_routes>=3   │
│ 闸（:184）天然免疫；展示面 8                                                 │
│ 处（_quality.py:93-107、_listing.py:96-106、_health.py:146-203、slash_comman │
│ ds.py:373-384、_config.py:234、status_cmd.py:67,168 等）全部 dict.get 带     │
│ default，\?\ 落 dim/— 分支。 - **B                                           │
│ 的顺序纪律（采纳为测试要求而非提交顺序，因单提交内原子完成）**：必须有联合   │
│ must-NOT 测试证明\零样本 + last_used 90 天前 +                               │
│ auto_deprecate=True\也不产生任何动作——即拆 auto                              │
│ 与改数值任一单飞都不造成批量雪崩。 - 测试 pin                                │
│ 修正：tests/core/test_evaluation.py:40-50 两条零样本断言改                   │
│ 0.0+\?\（这是行为修复，pin 假行为的测试属被修对象）；must-NOT：零样本 grade  │
│ 不得为 D 或 F（防双向撒谎）。 - `feedback_loop.py:1-7` 模块 docstring        │
│ \F-grade → auto-deprecate\ 改写为新 opt-in 语义。  ### 2.2 auto 行为逐点处置 │
│ 1. `feedback_loop.py:66` 签名默认 `True→False`（锚点，不单独构成修复）。 2.  │
│ `feedback_loop.py:208` generate_report → 显式 False（`stale --json`          │
│ 不再静默处置）。 3. `feedback_loop.py:246` end_of_session_check → 显式       │
│ False。 4. `cli/main.py:1707` → 显式                                         │
│ False（热路径只剩计数+tip，用户可见面零变化）。 5. `render.py:66` → 显式     │
│ False（同文件 :248 已是此写法，消除同文件双口径）。 6. `optimize_cmd.py:106` │
│ → 显式 False。 7. `_apply_boost` 自动恢复：auto_deprecate=False              │
│ 时**双向**不写生命周期（deprecated→active 恢复同属暗道，B 发现并采纳）。 8.  │
│ `skill_commands.py:355-373` `stale --auto`：不动，成为唯一受 sanction        │
│ 自动入口；help 文案补\默认只读，--auto 是唯一自动处置入口\。 9. 存量已       │
│ deprecate 技能：不回滚不复活，记档（gate37 §4 边界双向适用）。  ### 2.3      │
│ optimize_cmd 死代码  - `optimize_cmd.py:106` 构造                            │
│ bug：`FeedbackLoop(evaluator)` 把 evaluator 塞进 project_root 位置参数 →     │
│ TypeError 被 :135-136 吞掉 → quality actions 恒空。修复为正确构造。 -        │
│ `:140-157` `--apply`：`loop.apply_auto_actions()` 方法不存在（AttributeError │
│ 被吞）。改为 `analyze_all(auto_deprecate=True)` 并收集                       │
│ action∈{deprecate,archive} 的 skill_id 喂给既有                              │
│ `_log_optimization`（:153）。  ### 2.4 --apply 起死回生 vs 删除（A/B         │
│ 分歧裁决）  B 主张删（三年没人发现死了=无需求）；A 主张修（--apply 是显式    │
│ flag，等价 gate37 允许的 --yes 上限形态）。**裁定修**，理由：(a)             │
│ \死而无人知\证明的是质量动作流不可见，而本 gate 修好构造 bug 后 quality      │
│ actions 首次变得可见，需求判断应在可见之后做；(b) --apply 印在 help          │
│ 里的承诺本来就是 apply，删除是另一种用户可见契约破坏；(c) 显式 flag          │
│ 门控不违反任何边界。**CHANGELOG                                              │
│ 必须点名此行为变化**（从静默无操作变为显式确认下真实生效）。  ### 2.5        │
│ 不做（记档）  -                                                              │
│ optimization_service._apply_quality_boost（matcher_pipeline.py:133           │
│ 接入生产路由）：**不动**。total_routes≥3 闸 + 数的是显式反馈记录 →           │
│ 真信号非假 L2。若未来要拔，另行立项。 -                                      │
│ 薄样本（1≤total_routes<3）仍产字母档：不动（改动会改变 stale --auto          │
│ 既有命中率）；仓内 ≥3                                                        │
│ 闸多数票（optimization_service/_listing/_health）记档，留后续裁决。 -        │
│ 反馈存储三分裂：不修（gate37 修订 H 已裁决留档）。 - 热路径每 20 次路由全量  │
│ analyze_all 的性能：修复前后开销相同，不在本范围，记档。  ### 2.6 假 L2 测试 │
│ - test_evaluation.py：改 pin + grade 词表含 \?\ + 零样本不得为 D/F。 -       │
│ tests/core/skills/test_feedback_loop.py（MagicMock evaluator 先例            │
│ :43-57）：analyze_all 默认/set_lifecycle                                     │
│ assert_not_called；generate_report/end_of_session_check 同；**联合           │
│ must-NOT**：零样本+last_used 90 天+auto_deprecate=True 无任何动作；显式 True │
│ 仍生效（stale --auto 路径）；_apply_boost 在 False 下不恢复。 -              │
│ CLI：render._render_stale_suggestions 与 main._check_stale_skills_post_route │
│ 各加 assert_not_called；optimize --apply 正例（真实 deprecate +              │
│ log）与无候选反例。  ---  ## 3. report-only CI  B 核实：ci.yml 六            │
│ job，eval_routing 不在其中；`continue-on-error: true` 有 test-windows        │
│ 先例（:110）；release.yml:15-21 以 workflow_call 复用 ci.yml，report-only    │
│ 性质须由 job 自身保证；eval_routing.py 恒 `return 0`（:174）天然             │
│ report-only；\修标注\实为 yaml 无 per-entry schema（依赖只写在头部注释       │
│ :23-32）。C 核实：主集 34 条全 registry 内 id，裸环境可跑。  ### 3.1         │
│ 实施步一：主集 job 先行（C 的最小版）  ci.yml 追加 `routing-eval`            │
│ job：ubuntu-latest + `continue-on-error: true` + uv sync --extra dev；跑主集 │
│ `--json --json-out`；top-1/recall@3 写                                       │
│ $GITHUB_STEP_SUMMARY；upload-artifact。**先本地裸环境（orbstack              │
│ 容器）跑主集拿基线存档**（B 要求），再提交 job。  ### 3.2                    │
│ 实施步二：requires_packs schema + extended  - routing_eval_extended.yaml 4   │
│ 个条目（:100-102 omx/git-master、:118-120 与 :190-192                        │
│ superpowers/using-git-worktrees、:302-304                                    │
│ superpowers/requesting-code-review）加 `requires_packs:                      │
│ [omx]`/`[superpowers]`；头部注释 :23-32 重写为字段说明（字段成唯一事实源）。 │
│ - eval_routing.py：router 构建后（:66 后）算可解析技能 id 集（builtin 侧     │
│ core/registry.yaml；external 侧                                              │
│ ExternalSkillLoader.discover_all()，external_loader.py:124）；**presence     │
│ 检查自身出错→当作存在**（保守方向，宁多报误报不藏回归，与 gold_detection     │
│ \unknown 永不当 miss\ 同向）；带标注且全部 expect id 不可解析 →              │
│ `skipped_env`：不计分母、不进 errors，metrics 加 `skipped_env:               │
│ int`，per_query 记 `ok1: null, skipped_env: true`。 - 新增                   │
│ `--strict`（误路由 exit 1）留口不接线：默认不开、CI 不用。硬阻断是 gate37 §4 │
│ 永久否决项。 - job 加跑 extended 第二份 JSON 进 artifact；retention yaml     │
│ 不评分（extended 头部 :49-50 声明）。  ### 3.3 CI 测试与风控                 │
│ tests/unit/test_eval_routing.py（build_eval_from_logs                        │
│ 脚本测试同层惯例）：skipped_env                                              │
│ 不计分母；**must-NOT**：不带标注的误路由仍计入 errors；presence              │
│ 检查抛异常按存在处理；退出码恒 0 / --strict exit 1；yaml                     │
│ 标注合法性（namespace ∈ registry，防手滑）。 风控：不发 badge 不在 README    │
│ 晒数字（防 report-only 数字被当质量门）；CI 时长以首跑实测为准（benchmark    │
│ job 先例证明量级可承受）；release ci-gate 在 continue-on-error 下 caller 见  │
│ success。  ---  ## 4. 文档同步清单  - CHANGELOG [Unreleased]：gate38         │
│ 条目，点名三个行为变化——route_outcomes.jsonl 出现 side:\hit\                 │
│ 行且首跑回灌历史、零样本 grade 变 \?\、`optimize --apply`                    │
│ 从静默无操作变真实生效。 - tool_call_bridge 模块 docstring（hit 段落 +       │
│ 双口径披露 + 弱信号声明）；feedback_loop/evaluator docstring。 -             │
│ docs/user/CLI_REFERENCE.md：stale --auto 唯一自动入口表述、report            │
│ 零样本显示。 - docs/dev/eval-set-append-workflow.md：requires_packs          │
│ 字段说明。 - check_docs + check_doc_versions 双过。  ## 5. 记档（gate39      │
│ 候选，本 gate 不做）  1. **dashboard /api/skills/health 端点**（Lane C       │
│ 提议）：dashboard /api/health 读 analytics.jsonl（opt-in 默认关），gate37    │
│ 健康列数据接进 dashboard tab，约半天。用户可感知收益最高的小切口。 2.        │
│ **verdict backfill**（Lane C 提议）：对 cmspark 5 个历史 promoted 簇补跑     │
│ shadow verifier 回填 promote_verdicts.jsonl（标 backfill                     │
│ 来源）。注意：会改变 \verdict≥30\ 触发器的语义（回填 vs                      │
│ 有机），立项时需先裁决触发器口径。 3. bridge SPANS_FILENAME 不镜像 dev/prod  │
│ 的既有缺口。 4. 薄样本字母档与仓内 ≥3 闸多数票的对齐裁决。 5. 热路径         │
│ analyze_all 全量扫描性能。  ## 6. 实施纪律  - 单 gate 多分                   │
│ commit；复审期间不动被审文件；修订收敛与正文回写同一动作。 - 新碰文件 ruff   │
│ check + format 双净；存量 lint 不顺手修；测试禁内建 hash()。 - 全量 pytest   │
│ 基线 6172 passed/14 skipped；orbstack e2e 基线 smoke 68/68 + routing 7/7。 - │
│ 双路复审（claude+pi）0 BLOCK 后 push。)                                      │
╰──────────────────────────────────────────────────────────────────────────────╯
# Gate38 设计稿三路评审（pi 复审）

## Verdict
PASS_WITH_NITS

三路裁定经受住攻击：top_skills 不可逆论证成立、hit outcome 非 CLI + 披露是唯一可行解、`--apply` 起死回生与 gate37 自身对 optimize_cmd.py:106 的处置框架一致。证据核查 16/16 处引用属实（个别行号漂移 ≤10 行，不构成误导）。不变量零触碰确认。**但发现 2 个 MAJOR 必须在实施前收敛**：① 全仓存在 gate38 未覆盖、未披露、未裁决的第 6 条自动生命周期写入路径（loader.py:160-165，discovery 热路径静默 archive）；② §2.2.8 与 §2.4 自相矛盾（"唯一受 sanction 自动入口" vs 起死回生的 `--apply`）。

## Findings

- **[MAJOR] loader.py:160-165 静默 auto-archive 未纳入假 L2 处置范围，且无披露无裁决**：`SkillLoader.discover_all()`（candidate_manager.py:129 路由热路径调用）对 `lifecycle==DEPRECATED` 且 last_used ≥90 天的技能直接 `set_lifecycle(ARCHIVED)`——一条不依赖任何 flag、无确认的自动生命周期写入。gate38 的"默认只读""自动处置收敛为显式入口""双向不写生命周期"叙事对它全部不成立。§2.2 仅 9 项，§2.5"不做"清单也不含它。尤其 §2.2 item 9"存量已 deprecate 不回滚"只说了一半：这批存量技能仍会在下次 discovery 被静默 archive。按 gate37 §4"任何自动降级/删除路径（永久边界；上限=--yes 确认）"字面，此路径本身即越界，而 gate38 的章程（假 L2 处置）正是处置它的位置。修订稿必须：显式裁决（保留则 CHANGELOG 披露 + 确认它只在"显式 deprecate 之后 90 天"触发；或对齐 --yes 边界），不得只字不提。

- **[MAJOR] §2.2 item 8 与 §2.4 直接矛盾**：item 8 裁定 stale --auto"成为唯一受 sanction 自动入口"并强制 help 文案写"--auto 是唯一自动处置入口"；§2.4 却起死回生 `optimize --apply`（`analyze_all(auto_deprecate=True)`，真实 deprecate/archive）。实施后该 help 文案是假话，用户面对两个并列的显式自动处置入口。二选一：①（推荐）改 item 8 措辞为"默认路径全部只读；显式自动入口为 stale --auto 与 optimize --apply 两处"，help 同步；② 保留"唯一"则将 --apply 降为 dry-run/report-only。当前文本会引导实施者写错文案。

- **[NIT] top_skills 在 miss span 上会写入空 primary**：§1.1 只规定"无候选时整键省略"，未规定 miss（`skill_id=""`）且有 alternatives 时的行为——按字面会写 `top_skills=["", alt1, alt2]`，读者会把空串当候选。应规定空 primary 从列表中剔除（仅 alternatives）或整键省略。另 primary 与既有 `metadata["skill_id"]` 重复，若目的是"完整排序快照"应在 docstring 说明，否则可省。

- **[NIT] 双总体披露应双挂点 + 覆盖 miss 侧**：tool_call_bridge docstring 披露"hit outcome 仅 hook 路径"正确，但 fire 列（`vibe skill list`，gate37 修订 B 补丁：CLI 命中计入）才是拼比率的诱惑面——披露应同时写进 L2-lite 列文案。且 miss outcome 同样是 hook-only（`:470-487` 同因排除 CLI），"双总体"实为 fire 含 CLI vs 两侧 outcome 均不含 CLI，docstring 应把 miss 侧一并点明，否则未来读者会以为只有 hit 侧有口径差。

- **[NIT] status_cmd.py:72 "?" 桶不可见**：`grade_counts[e.grade]` 会创建 `"?"` 键，但 `_grade_bar`（:38-43）只迭代 A-F，分母含 "?"、柱条不含——分布图百分比和不等于 100%。显示面 dict.get 兜底判断成立，但设计未指定 "?" 桶的展示（建议 A-F 之外加 `?` 列或标注"无数据不参与分布"）。

- **[NIT] `--apply` 修复后 boost 复活不入日志**：`_apply_boost` 在 auto_deprecate=True 时会把 deprecated 的 A 档翻回 active（feedback_loop.py:200-201），§2.3 的修复只收集 action∈{deprecate,archive} 喂 `_log_optimization`（:153）——复活动作被执行但不落优化日志，`optimize --apply` 的历史记录不完整。

- **[NIT] render.py:66 并非"活"调用点**：`render_fallback_panel` 全仓无调用者（仅 `__all__` 导出，src/ 与 scripts/ 均无可达路径），5 处"活调用点"实为 3 活（main.py:1707、feedback_loop.py:208/246）+ 1 潜伏（render.py:66）+ 1 死（optimize_cmd.py:106 构造 bug）。改 False 仍正确（防御 + 消除同文件 :248 双口径），但 gate37 修订 C 补丁的"活"字面失真，修订稿应如实标注，避免未来误判该路径有实际流量。

**评审要点逐项结论**：

1. **换皮检查**：通过。三项均为 gate37 明文 deferred（裁决 2、修订 C、裁决 4 留 gate38）；无 intake 过滤/阈值工程/hash chain 复活；CI 保持 continue-on-error + exit 0 + skipped 透明，非硬阻断换皮；假 L2 处置删除自动处置而非新增评价维度。唯一接近边界的项是 `--apply`（见 MAJOR ②），但其为显式 flag，未超 gate37 §4 "--yes 上限"。
2. **不变量**：零触碰成立。`_is_agent_prompt_shape`（skill_promote.py:366）冻结、`_is_miss`/`_classify` 函数体不动（新增 `_is_hit`/`_classify_hit` 独立函数 + reason 词表 `hit_` 前缀不相交）、双 embedding 与三套 trigger 匹配语义全程未涉、gate30 upsert 未涉、hit outcome 沿用 sole-reader 不加锁与 span_id 去重（与 gate16b N3 前提一致）、top_skills 为 dict 加键微秒级远离 16384（span_writer.py:39）与 100µs p95 门（test_span_emit_overhead.py:10）。
3. **裁决攻击**：
   - a. **top_skills 保留成立**。不可逆论证属实：spans 仅存 primary `skill_id`，alternatives 无法由回放复现（查询被截断 200 字符 + 索引漂移），是真正的写时数据；而 route_outcomes 本就由 spans 全量扫描派生（:414-467），hit 侧可回填。最小化纪律不构成违反：gate37 裁决 2 已预批准该项、additive 且廉价、项目已有 write-only 数据先例（route_outcomes.jsonl 至今零读者）。纪律约束写进 docstring 足够。
   - b. **披露为当前可行解**。含 CLI 进 hit outcome 已被 miss 侧同因否决（one-shot session → 24h 空洞弱阳性，:470-487）；从 fire 列剔除 CLI 则推翻 gate37 修订 B 补丁既定口径。docstring 披露是唯一不动先行裁决的选项，加 NIT ② 的双挂点即充分。
   - c. **A 案（修）正确**。死因是构造 bug 而非需求裁决，gate37 修订 C 本就把它列入待修调用点；"无需求"推断建立在对事故性死代码的误读上。B 案最强论点（入口增殖）由 MAJOR ② 吸收——修与删之外的正确动作是承认两个显式入口并存并改措辞。
4. **证据核查**：16/16 处文件:行号引用真实且含义相符（evaluator.py:64-66 零样本 0.5 兜底、feedback_loop.py:66/155/196-204/208/246、optimize_cmd.py:105-106 构造 bug + :148-149 `apply_auto_actions` 不存在、tool_call_bridge.py:414-467/470-487/495-540/97,195、agent_runtime.py:620-626/668-670、main.py:904/914/935-936/1707、eval_routing.py:66/174、ci.yml:110、release.yml:15-21、extended :100-102/:118-120/:190-192/:302-304/:49-50、external_loader.py:124、skill_promote.py:366、test_evaluation.py:40-50、test_feedback_loop.py:43-57、test_tool_call_bridge.py:497、matcher_pipeline.py:133、optimization_service.py:184、span_writer.py:39）。全部 8 个 metadata 消费点容忍式解析确认。细微漂移：agent_runtime 层省略惯例实际代码在 :699-700（:693-696 是注释）、main.py:906 vs :904、_config.py:234 vs :246。
5. **完整性**：全仓 grep `.grade`/`quality_score`/`analyze_all` 后，消费者集合与"8 处"清单一致，全部对 "?" 容忍（badges.py:220 的 `in ("A","B")` 对 "?" 同样安全）。**唯一遗漏是 loader.py:160-165（MAJOR ①）**——它不消费 evaluator 词表所以被 `?` 修复自然放过，但它是独立于 feedback_loop 的自动生命周期写入。测试计划能抓住声称的行为（零样本+90 天+True 无动作的联合 must-NOT 可证，因为 "?" 不命中 feedback_loop.py:155 的 `("C","D","F")`；stale --json 静默处置路径的 assert_not_called 可证）；顺序依赖无残余风险——单提交原子落地 + 联合 must-NOT 双保险，且分析表明拆 auto 与改数值任一单飞都各自安全（auto-only：全调用点显式 False，无雪崩；evaluator-only："?" 不命中任何规则）。
