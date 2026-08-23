# gate38 综合裁决稿：技能评价体系第二刀（r3，定稿）

> 日期：2026-08-23 · 流程：三路独立对抗 → 综合 → 三路评审（均 PASS_WITH_NITS，0 BLOCK）→ 收敛 → 三路确认制复审（均 PASS_WITH_NITS，0 BLOCK）→ 本稿定稿
> 前置：gate37 已交付（80a3398）；三项均为 gate34/gate37 明文 deferred 项，非换皮。
> r2：第一轮 9 MAJOR + 19 NIT 收敛。r3：确认轮 grok 1 MAJOR + 2 NIT、pi 5 NIT、claude 2 NIT 收敛，逐条处置见 §7；正文已同步回写。

## 0. 裁决总览

| 项 | 裁决 | 关键分歧与裁定 |
|---|---|---|
| L2a top_skills | **做**（additive span metadata，仅 hit span 写键） | C 主张砍；裁定做——不可逆性论证（§1.0），grok/claude 复核成立 |
| L2a hit outcome | **做**（仅非 CLI hit，`side:"hit"` + `population:"hook"`） | B 揭示 CLI 总体矛盾；三路确认披露方案为两劣后最优 |
| 假 L2 处置 | **做**，含 loader.py 静默 archive 清除（pi 发现） | 默认路径全只读；显式自动入口**三处**（stale --auto / optimize --apply / cleanup --auto，grok r3 确认轮补齐）对称并存 |
| report-only CI | **做**，含 requires_packs schema；**不造 --strict** | 主集 job 先落地；永久 report-only 写进 job 注释 |
| Lane C 新提议 ×2 | **不纳入 gate38**，记档 gate39 候选 | 见 §5 |

## 0.1 换皮回归自查（r2 改写）

- 对照 gate34 不做清单：无 intake 过滤、无阈值工程、无硬阻断、无 hash chain。`--strict` 旗标已从范围移除（grok-NIT：离永久否决的硬阻断只差一次接线，YAGNI）。
- 对照 gate37 §4：L2a=裁决 2 明文 deferred；report-only CI=裁决 4 deferred（`continue-on-error` + exit 恒 0 + skipped 透明，非硬阻断换皮）；假 L2 处置=修订 C 点名待议项。
- 定性修正（claude-MAJOR-1）：本稿清除的是**静默/暗道**自动处置（热路径、render 副作用、--json 暗道、loader 发现路径），同时把一条三年死代码（--apply）修活为**显式 flag** 入口——这是净增一个可用的批量处置入口，与 stale --auto 对称，不违反"上限=显式确认"边界，但叙事上不得自称"只删不增"。无比率、无新分数、无上卡。
- 零触碰清单：三套 trigger 匹配语义、双 embedding 分离、`_is_agent_prompt_shape`、gate30 upsert、`_is_miss`/`_classify` 函数体。hit 分类器是新函数，miss 侧既有测试零改动即冻结证明。

---

## 1. L2a 仪表化

### 1.0 top_skills 的裁决理由

C 的"无消费方"是事实（L2b 前置 verdict≥30 且单技能月 fire≥30，cmspark 现 verdict=0）。但存在不对称：**hit outcome 可从 spans 历史回填（派生数据），top_skills 不可回填（写时数据，路由器状态随时间漂移不可回放重建——claude 复核确认）**。成本：生产点只是 dict 加 key（`result.alternatives` 本来就算出，eval_routing.py:80 在用）；序列化微秒级；全部 metadata 消费点容忍式解析（grok 复核修正引用：dashboard server.py 容忍解析在 :73-82,:128-133；aggregator.py:146 是 token_accounting 特判非通用 walk——结论不变）。纪律：L2b 前置满足前任何读者不得用 top_skills 派生比率/处置。

### 1.1 top_skills 实施（r2 收紧）

Schema：metadata 新增 `"top_skills": list[str]`，≤3，primary 在前 + 至多 2 个 alternatives。**仅当 `has_match is True` 才写键**（pi/grok-NIT 收敛：miss 时 CLI 侧 alternatives 是 fallback nearest（result_mixin.py:277-328）、hook 侧 miss 在 `if primary` 内才填 alternatives（agent_runtime.py:619），两侧 miss 语义不对齐；且空 primary 会写出 `["",alt1,alt2]` 脏数据）。hit 时 primary 恒非空。与 `metadata["skill_id"]` 的重复是有意的完整排序快照，docstring 说明。

- Hook 侧：`agent_runtime.py:668` 后插入，数据源 :620-626 的 `result.alternatives`（list[dict]）。**写键条件钉死**：用 `result.router_matched`（即 :692 写入 metadata["has_match"] 的同一表达式）——**禁止用 `result.has_match` 属性**，它在 intercepted miss 上仍为 True（:671-675），会把 r2 的"仅 hit 写键"打回脏数据（grok-NIT）。
- CLI 侧：`cli/main.py:906` 后插入；alternatives 是对象列表，`getattr(a,"skill_id","")` + isinstance(str) 过滤，沿用 :932-936 MagicMock 守卫惯例。**写键条件 = 与该写入点 metadata["has_match"]（:914，grok r3 修正行号）完全相同的表达式，数据源是路由 result 对象而非 span metadata**（:906 在 :914 之前，按"已写 metadata"判断会让 CLI hit 永不写键——pi-NIT）。
- 不改 span_writer 序列化/脱敏路径。

### 1.2 hit outcome 实施（r2 收敛）

- 新谓词 `_is_hit`（`_is_miss` 后，约 :493）：`not rs.is_cli ∧ rs.has_match is True ∧ rs.mode not in ("not_intercepted","slash_command")`。docstring 按 gate17 惯例交叉引用 `_is_miss`。
- 新分类器 `_classify_hit`（`_classify` 后，约 :540）：同 task_id 后续 route span → `("weak_negative","hit_reask_same_task_id")`；同 session 后续不同 task span → `("weak_positive","hit_session_moved_on")`；年龄 > SESSION_COMPLETE_HOURS → `("weak_positive","hit_session_expired")`；否则 None。不接 accepted_queries。reason 一律 `hit_` 前缀。
- 新函数 `_derive_hit_outcomes`（`_derive_outcomes` 后）：镜像 :414-467——同一 outcomes 文件、同一 span_id 去重、plain append、不加新锁。行 schema = miss 行 + `"side":"hit"` + **`"population":"hook"`**（grok-MAJOR-6：行级自描述总体，防止未来读者拼错口径）；miss 行不回写，reader 以 side 缺省=miss、population 缺省=hook 处理（miss 侧同为 hook-only，docstring 一并点明——pi-NIT）。
- 接线：`_run` :221 后一行；`BridgeStats` 加 `hit_outcomes_recorded: int = 0`。
- **口径披露（三路收敛，双挂点）**：(a) tool_call_bridge 模块 docstring（:32-47）补 hit 段落 + 披露"两侧 outcome 均仅 hook 路径，与 fire 列（含 CLI，gate37 修订 B）总体不相交，禁止拼 fire→成功率比率；hit 弱阳性比 miss 更虚（不再回来≠满意，也可能是放弃）";(b) 同一警示写进 fire 列头脚注/CLI_REFERENCE（claude-NIT：披露必须抵达引诱发生的界面）。
- **首跑回灌披露**：全部历史 hit 一次性派生（write-once + 去重幂等）；其中 `hit_session_expired`（24h 规则，SESSION_COMPLETE_HOURS :91）在回灌中占主导、信号最弱——grok 建议"expiry 仅对增量生效"，**裁定驳回**：需引入日期常量、与 miss 侧回灌行为失对称；以 reason 前缀可过滤 + docstring 披露代替（§7 记录）。
- **成本声明**（claude-NIT）：`_classify_hit` 与 miss 侧同渐近 O(hits×spans)，首跑一次性付满，spans.jsonl 无界增长时 bridge 单次成本按平方涨；离线路径不违 100µs 热路径门；与 spans 轮转上界的依赖记档 §5。
- bridge 读 SPANS_FILENAME 硬编码不镜像 dev/prod 是既有缺口（:97,:195），本 gate 不改，记档。

### 1.3 L2a 测试

tests/core/observability/test_tool_call_bridge.py（:496 有 miss e2e 先例）：hit+同 task 重问→恰好一行 weak_negative/`side=="hit"`/`population=="hook"`；session moved on→weak_positive；新鲜 hit→无行且二次幂等；**must-NOT**：CLI hit 永不产 outcome；has_match True/False/None 三态互不串池；**`_is_miss`/`_classify` 既有测试零改动（冻结证明）**；坏行/坏 metadata 跳过不抛。top_skills：tests/agent/ + tests/cli/——仅 hit 写键、≤3、primary 在前、miss（含 fallback alternatives）键不存在、MagicMock 不泄脏字段、旧 span（无键）reader 计数不变。

---

## 2. 假 L2 处置

### 2.0 现状（r2 更正后的伤害链，grok-MAJOR-1）

- 任务书 5 调用点实况：`cli/main.py:1707`（每 20 次路由热路径）与 `render.py:66`（no-match 渲染副作用）以默认 `auto_deprecate=True` 调 `analyze_all()`；`feedback_loop.py:208`（generate_report，经 `stale --json` skill_commands.py:378 可达，而同命令非 --json 路径 :373 是 False）；`feedback_loop.py:246`（end_of_session_check）；`optimize_cmd.py:105` 构造 bug（evaluator 塞进 project_root 位置参数→TypeError 被 :135-136 吞，quality actions 恒空）+ :148 同样构造 bug 先触发（:149 `apply_auto_actions()` 不存在的 AttributeError 不可达——claude 证据修正）。
- **伤害链更正**：生产 `evaluate_all_skills` 只纳入 routing feedback/preferences/execution feedback，不扫 usage_stats-only 技能（evaluator.py:246-254）；零样本 0.5→D 后规则顺序是 D+60d warn 先 return（feedback_loop.py:139-152），warn 即使 auto=True 也不写生命周期——**现状零样本技能的直接暴露是"D 档假成绩误导展示 + 永远停在 warn"，不是 auto archive**。但热路径/render/--json 三处静默 auto 调用仍是悬置的雷：任何项目一旦攒出真 F 档反馈，无确认批量处置立即发生；`_apply_boost`（:196-204）还会把 deprecated 的 A 档自动翻回 active。
- **pi 发现的第 6 条**：`loader.py:160-165` —— `SkillLoader.discover_all()` 对 DEPRECATED 且 last_used≥90d 的技能直接 `set_lifecycle(ARCHIVED)`，不依赖任何 flag，discovery 热路径静默写入。

### 2.1 evaluator 零样本不再撒谎（r2：原子对 + 展示面逐点）

- `total_routes == 0` → `quality_score` 返回 `0.0` **且** `grade` 返回 `"?"`（新词表成员=有对象无路由反馈）。**两返回值必须同一 commit**（grok-MAJOR-2：只改分数不短路 grade() → 0.0→F → F+30d+<3 命中 deprecate 规则 :119-125，比现状更糟）；§6 的"多分 commit"纪律对本原子对例外。
- 下游兼容（三路合并审计清单）：feedback_loop 四条规则精确匹配 F/D/(C,D,F)，"?" 全不命中；optimization_service 有 total_routes>=3 闸（:184）免疫；badges.py:203-223（`all(g in ("A","B"))`，"?" 不授徽章=与今日 D 同结果，无需改）；_config.py:246-248（== 精确匹配，仅建议不动作）；_listing.py:245（total_routes>0 门挡住零样本数值展示）。
- **展示面逐点处理（grok-MAJOR-5 + claude-NIT，原"dict.get 落 dim 兜底"核查不成立）**：
  - `_health.py:156-162`：非 A/B/C/D 一律 🗑️ → "?" 单独分支（无数据图标，不用垃圾桶）；
  - `_quality.py:102` 等分数渲染：零数据行**分数显示 "—" 而非 "0%"**（无数据≠差，分数侧同一谎言不能换通道回来）；`vibe skills quality` 排序零数据行沉底可接受（claude 确认为自觉选择）；
  - `status_cmd.py` grade 分布图（:38-43 只迭代 A-F，:70-72 分母含 "?"）："?" 不计入分布分母，单独标注"无数据 N 个"；
  - `slash_commands.py:372-384`：同 _quality 处理。
- 词表冲突披露（grok-NIT）：retention.py:72 已有 "?"=无评价对象；evaluator 新 "?"=有对象无路由反馈——两词表同符不同义，两处 docstring 互相指引分开。
- 测试 pin 修正：tests/core/test_evaluation.py:40-50 改 0.0+"?"；must-NOT：零样本 grade 不得为 D 或 F；grade 词表含 "?"。
- `feedback_loop.py:1-7` 模块 docstring 改写为新 opt-in 语义。

### 2.2 auto 行为逐点处置（r2：10 项）

1. `feedback_loop.py:66` 签名默认 `True→False`（锚点，不单独构成修复）。
2. `feedback_loop.py:208` generate_report → 显式 False（`stale --json` 不再静默处置）。
3. `feedback_loop.py:246` end_of_session_check → 显式 False。
4. `cli/main.py:1707` → 显式 False（热路径只剩计数+tip）。
5. `render.py:66` → 显式 False（同文件 :248 已是此写法）。
6. `optimize_cmd.py:106`（展示路径）→ 显式 False——**构造 bug 修复后若漏此项，无 --apply 的 `vibe optimize` 展示就会写生命周期**（grok-MAJOR-4），dry-run must-NOT 测试锁定。
7. `_apply_boost`：auto_deprecate=False 时双向不写生命周期（deprecated→active 恢复同属暗道）。
8. `skill_commands.py:352-373` `stale --auto`：不动。**措辞收口（三路 MAJOR 收敛 + grok r3 补齐）**：删除"唯一"表述——help/文档改写为"默认路径全部只读；显式自动处置入口**三处**：`stale --auto`、`optimize --apply`、`vibe skills cleanup --auto`（cleanup_cmd.py:181-194 对 archive/deprecate 直调 `_apply_*`，接线 skill_commands.py:1304，本身就是显式 flag 门控）"。
9. 存量已 deprecate 技能：不回滚不复活（gate37 §4 边界双向适用）。
10. **loader.py:149-165 静默 auto-archive 整块清除**（pi-MAJOR-1 + grok 确认轮 MAJOR，纳入本范围）：删除整个块**含 `continue`**——只删 `set_lifecycle(ARCHIVED)` 写入而留 `continue`，会得到新暗道（状态仍 DEPRECATED 却按 last_used 从发现集消失）。删除后 DEPRECATED 不论 last_used 都留在 `discover_all` 返回值；ARCHIVED 仍走 :166-167 过滤；路由不受影响（lifecycle.py:85 / candidate_manager.py:347-348 已把 DEPRECATED 当不可路由），受影响的是发现集/索引（candidate_manager.py:129、indexer.py:283,684）。**已知后果（写进 CHANGELOG，不暗示等价替代）**：显式 archive 仅剩 stale --auto 的 archive 规则（feedback_loop.py:154-155，谓词 grade∈(C,D,F) ∧ evaluation.last_used≥90d），与原 loader 谓词（lifecycle==DEPRECATED ∧ usage_stats.last_used≥90d，不论 grade、不论有无评价数据）不等价——gate38 后 DEPRECATED+"?"/usage_stats-only 技能**不存在任何到达 ARCHIVED 的路径**，将永久保持 DEPRECATED 并留在发现池（loader 只排 ARCHIVED，:166）。裁定接受此后果：隐藏-by-last_used 而无状态变化本身是另一条暗道，诚实的默认是可见。测试：断言可见性（DEPRECATED≥90d 仍在 discover_all 返回值）+ set_lifecycle assert_not_called，双锁（不能只测其一——grok）。loader 暗道无既有测试 pin（pi 核实 test_loader.py/test_lifecycle.py），删除零测试冲击。

### 2.3 optimize_cmd 死代码修复（r2）

- `:105` 构造 bug → 正确构造 `FeedbackLoop`（配合 §2.2.6 的显式 False）。
- `:140-157` --apply：`analyze_all(auto_deprecate=True)`，**按实际写入收集**（claude-NIT：analyze_all 现不返回真实写入，_apply_boost 仅在 lifecycle=="deprecated" 时写（:199-201），deprecate/archive 失败被 except 吞（:185,:193）——按 suggestion 收集是镜像撒谎）。实现：`_apply_*` 返回 bool（或 analyze_all 返回 applied ids），仅实际发生 set_lifecycle 的 skill_id 进 `_log_optimization`（:153）与 "Applied Optimizations" 列表；三类动作（deprecate/archive/boost 复活）一视同仁；must-NOT：已 active 技能的 boost suggestion 不得出现在 log。help 文案如实说明三种动作。
- 展示侧对齐（grok-NIT）：`optimize_cmd.py:109-133` 现只映射 deprecate/warn/boost、丢掉 archive——构造 bug 修好后 dry-run 预览必须看得到 --apply 会执行的 archive，展示映射补齐 archive。
- `optimize --apply` 无 --yes 二次确认（optimize_cmd.py:31-38）——与 stale --auto 同级（显式 flag 即确认），对称可辩护，CHANGELOG 并列点名。

### 2.4 --apply 修而非删的裁定（维持 §0 裁决，三路复核通过）

B 主张删（三年没人发现死了=无需求）；**裁定修**，理由：(a) "死而无人知"被构造 bug 污染，不能当需求证据（grok 同认）；质量动作流在本 gate 修好构造 bug 后首次可见，需求判断应在可见之后做；(b) 删除印在 help 里的承诺是另一种契约破坏；(c) 显式 flag 门控不越 gate37 §4 上限。约束：uniqueness 措辞收口（§2.2.8）+ 动作/日志对称（§2.3）+ dry-run must-NOT（§2.2.6）。

### 2.5 不做（记档）

- optimization_service._apply_quality_boost（matcher_pipeline.py:133 接生产路由）：不动。≥3 闸 + 显式反馈记录 → 真信号。
- 薄样本（1≤total_routes<3）仍产字母档：不动；仓内 ≥3 闸多数票记档留后续裁决。
- 反馈存储三分裂：不修（gate37 修订 H）。
- 热路径每 20 次路由全量 analyze_all 性能：修复前后开销相同，记档。
- RetentionPolicy（retention.py:64-132）无生产调用方属死代码（claude 发现）：本 gate 不清，记档。

### 2.6 假 L2 测试（r2）

- test_evaluation.py：改 pin + 词表 + 零样本不得为 D/F。
- tests/core/skills/test_feedback_loop.py：analyze_all 默认/generate_report/end_of_session_check → set_lifecycle assert_not_called；**联合 must-NOT（r2 防空测，grok-MAJOR-1）**：构造真实 `SkillEvaluation(total_routes=0, last_used=90d前)` 走 `analyze_all(auto_deprecate=True)` → 断言 grade=="?" **且 suggestions 为空（含无 warn）** 且 set_lifecycle 未调；显式 True 对真 F 档仍生效；_apply_boost 在 False 下不恢复。
- CLI：render/main 各加 assert_not_called；`vibe optimize` 无 --apply 不写生命周期（dry-run must-NOT）；--apply 正例（三类动作真实生效+全部入 log）与无候选反例。
- loader：discovery 对 DEPRECATED≥90d 不产生 set_lifecycle 调用**且该技能仍在 discover_all 返回值中**（可见性断言，双锁缺一不可）。

---

## 3. report-only CI（r2）

核实（含 grok 修正）：ci.yml 六 job，`continue-on-error: true` 先例在 test-windows（:110）；`workflow_call` 在 ci.yml:11，release.yml:17 是 uses 调用方——report-only 性质须由 job 自身保证；eval_routing.py 恒 `return 0`（:174）。裸环境基线已存档（.omx/artifacts/gate38-eval-baseline-bare.jsonl）：主集 34 条 top-1 61.8%/recall@3 70.6%；extended 107 条 top-1 94.4%，6 errors 中 4-5 为 pack 环境缺失。

### 3.1 实施步一：主集 job

ci.yml 追加 `routing-eval`：ubuntu-latest + `continue-on-error: true`；uv sync --extra dev；主集 `--json --json-out`；top-1/recall@3 写 $GITHUB_STEP_SUMMARY；upload-artifact。**job 注释写明"永久 report-only，不设观察期转硬门"**（claude-NIT：对照 test-windows :105-110 观察期注释，防被一次性清掉）。

### 3.2 实施步二：requires_packs schema + extended（r2）

- extended yaml 4 条目（:100-104、:118-121、:190-193、:302-304）加 `requires_packs`；头部注释 :23-32 重写为字段说明，并**如实披露两类残余噪音**（claude-NIT）：(a) reject-only 条目（expect:[] + reject 含 pack id）在裸环境空过、抬高通过率；(b) 头部自述 ~5 条 env-sensitive fallback 条目未带标注仍计 errors——extended 数字不是干净基线。
- eval_routing.py：router 构建后算可解析 id 集（builtin 侧 core/registry.yaml；external 侧 ExternalSkillLoader.discover_all()，external_loader.py:124）；presence 检查自身出错→当作存在（保守方向）。skip 谓词（grok-NIT 防空跳）：**expect 非空**且全部 expect id 不可解析才判 skipped_env（`all([])` 为 True 的陷阱）；skipped_env 不计分母、不进 errors；metrics 加 `skipped_env:int`；per_query 记 `ok1:null, skipped_env:true`——**聚合处 ok1 为 None 不进求和**（:91,:128 防 TypeError/除零），**errors 列表同步排除**（:106 `if not ok1:` 对 None 为真会把 skipped 行误加进 errors，需 `if not ok1 and not skipped_env:`——pi-NIT）。
- **不新增 --strict**（grok-NIT 采纳：硬阻断枪不造，出现被批准用途再加）。
- job 加跑 extended 第二份 JSON 进 artifact；retention yaml 不评分。

### 3.3 CI 测试与风控

tests/unit/test_eval_routing.py：skipped_env 不计分母；must-NOT：不带标注误路由仍计 errors；presence 检查抛异常按存在处理；退出码恒 0；expect:[] + requires_packs 不 skipped；skipped 行不进 errors 列表；全 skipped 时聚合不除零；yaml 标注合法性（namespace ∈ registry）。风控：不发 badge 不晒数字；CI 时长首跑实测；release ci-gate 在 continue-on-error 下 caller 见 success。

---

## 4. 文档同步清单（r2）

- CHANGELOG [Unreleased] gate38 条目，点名五个行为变化：route_outcomes.jsonl 出现 side:"hit" 行且首跑回灌历史（expiry 占主导信号最弱）、零样本 grade 变 "?" 且分数显示 "—"、`optimize --apply` 从静默无操作变真实生效（三类动作全入 log）、loader 不再静默 auto-archive、默认路径全部只读（显式入口三处：stale --auto / optimize --apply / cleanup --auto）。
- tool_call_bridge docstring（hit 段落+双总体披露覆盖 miss 侧+弱信号声明+成本声明）；feedback_loop/evaluator/loader docstring；retention.py 与 evaluator 的 "?" 词表互相指引。
- docs/user/CLI_REFERENCE.md：三处显式入口枚举、report 零样本显示、**fire 列"含 CLI 命中，与 outcome 口径不可拼比率"警示**。
- docs/dev/eval-set-append-workflow.md：requires_packs 字段说明。
- **GOALS.md:104 / ARCHITECTURE.md:597**：移除 FeedbackLoop 自动降级的过时宣传（grok-NIT）。
- **docs/USE_CASES.md:281,291,300 / docs/ROADMAP.md:45**：移除"全自动（90 天没用 + D/F 级 → 归档）"宣传与已勾选的 Auto-archive 条目（pi 确认轮）——注意 `USE_CASES.md:291` 若实为 `cleanup --auto` 活文档则改为如实描述该显式入口而非按死功能移除（grok r3）；另补 grok r3 抓到的邻行：**GOALS.md:55、ARCHITECTURE.md:603、ROADMAP.md:354、USE_CASES.en.md:281,291,300（英文镜像）**——gate38 后任何路径都不存在全自动归档，这些不改会继续撒谎。
- check_docs + check_doc_versions 双过。

## 5. 记档（gate39 候选，本 gate 不做）

1. dashboard /api/skills/health 端点（Lane C，用户可感知收益最高小切口）。
2. verdict backfill（Lane C；立项前先裁决触发器口径：回填 vs 有机）。
3. bridge SPANS_FILENAME 不镜像 dev/prod 的既有缺口。
4. 薄样本字母档与 ≥3 闸多数票对齐裁决。
5. 热路径 analyze_all 全量扫描性能；bridge outcome 派生 O(hits×spans) 与 spans 轮转上界依赖。
6. RetentionPolicy 死代码清理。

## 6. 实施纪律

- 单 gate 多分 commit；**例外：evaluator 的 quality_score=0.0 与 grade="?" 必须同一 commit（原子对）**。
- 复审期间不动被审文件；修订收敛与正文回写同一动作（本稿即先例）。
- 新碰文件 ruff check + format 双净；存量 lint 不顺手修；测试禁内建 hash()。
- 全量 pytest 基线 6172 passed/14 skipped；orbstack e2e 基线 smoke 68/68 + routing 7/7。
- 实施双路复审（claude+pi）0 BLOCK 后 push。

## 7. 三路评审收敛记录（r2）

| 来源 | finding | 处置 |
|---|---|---|
| pi-MAJOR-1 | loader.py:160-165 静默 auto-archive 未裁决 | 采纳→§2.2.10 清除暗道 |
| pi-MAJOR-2 / grok-MAJOR-3 / claude-MAJOR-1 | "唯一入口" vs --apply 复活矛盾 | 采纳→§2.2.8 删"唯一"，两入口枚举，§0.1 定性修正 |
| pi-NIT / grok-NIT | top_skills miss 态空 primary、两侧 miss 语义不对齐 | 采纳→§1.1 仅 has_match=True 写键 |
| pi-NIT / grok-MAJOR-6 / claude-NIT | 双总体披露不足 | 采纳→行加 population:"hook"，披露双挂点（docstring + fire 列界面），覆盖 miss 侧 |
| pi-NIT | status_cmd "?" 桶分布图不可见 | 采纳→§2.1 展示面逐点 |
| pi-NIT / claude-NIT / grok-MAJOR-3 | --apply boost 复活不入 log | 采纳→§2.3 三类动作全收集 |
| grok-MAJOR-1 | 伤害链错误、联合 must-NOT 测空 | 采纳→§2.0 更正、§2.6 改真实 SkillEvaluation 断言 |
| grok-MAJOR-2 | 0.0 与 "?" 拆分会更糟 | 采纳→§2.1 原子对 + §6 例外 |
| grok-MAJOR-4 | optimize 展示路径漏 False | 采纳→§2.2.6 + dry-run must-NOT |
| grok-MAJOR-5 / claude-NIT | "?" 展示兼容核查不成立；分数侧 0% 谎言 | 采纳→§2.1 展示面逐点 + 分数显 "—" |
| grok-NIT | --strict 是硬阻断枪 | 采纳→移除，§0.1/§3.2 |
| grok-NIT | hit_session_expired 回灌淹没 | **裁定驳回**（日期常量 + miss 侧失对称；reason 可过滤+披露代替），§1.2 披露 |
| grok-NIT | CLI hit 落盘 eligible:false | **裁定驳回**（注定空洞的 24h 弱阳性，写入即噪音；population 字段已自描述） |
| grok-NIT | skipped_env 边界（all([])、ok1 None、除零） | 采纳→§3.2 谓词与聚合细则 |
| grok-NIT | 文档清单漏 GOALS/ARCHITECTURE；"?" 词表冲突 | 采纳→§4 + §2.1 |
| claude-NIT | --apply 死因表述（:148 TypeError 先于 :149）；:105 非 :106 | 采纳→§2.0/§2.3 证据修正 |
| claude-NIT | skipped_env 残余噪音两类 | 采纳→§3.2 头部注释披露 |
| claude-NIT | routing-eval 须写明永久 report-only | 采纳→§3.1 |
| claude-NIT | 兼容审计补录（badges/retention/_config/_listing/均值） | 采纳→§2.1 清单扩充；retention 死代码记档 §5 |
| claude-NIT | hit 派生 O(N²) 成本未声明 | 采纳→§1.2 成本声明 + §5 记档 |
| grok/claude 行号修正 | workflow_call 在 ci.yml:11；dashboard 容忍解析 :73-82 等 | 采纳→§1.0/§3 文内修正 |

### 确认轮（r3）

| 来源 | finding | 处置 |
|---|---|---|
| grok-MAJOR | §2.2.10 未钉 `continue`：只删写入留 continue=新暗道 | 采纳 (a) 案→整块删除含 continue，DEPRECATED 留发现集，可见性+不写双锁测试 |
| grok-NIT | hook 侧 `result.has_match` 属性在 intercepted miss 上仍为 True | 采纳→§1.1 钉死 `result.router_matched` |
| grok-NIT | optimize 展示路径丢 archive 映射 | 采纳→§2.3 展示侧补齐 |
| pi-NIT | §4 漏 USE_CASES.md:281,291,300 / ROADMAP.md:45 全自动归档宣传 | 采纳→§4 |
| pi-NIT | "?" 档手动 deprecate 技能无 archive 路径 | 采纳→并入 §2.2.10 已知后果（与 claude-NIT 合并表述） |
| pi-NIT | CLI 插入点在 has_match 写入之前 | 采纳→§1.1 钉死 result 对象数据源 |
| pi-NIT | eval_routing.py:106 errors 列表会把 skipped 行误入 | 采纳→§3.2/§3.3 |
| pi-NIT | 行号漂移（:91/:71-74/release.yml:17） | 采纳→正文修正 |
| claude-NIT | §2.2.10 "等价替代"暗示过强 | 采纳→已知后果写明：DEPRECATED+"?" 永久留池 |
| claude-NIT | --apply 收集未钉到实际写入粒度 | 采纳→§2.3 _apply_* 返回 bool，按实际 set_lifecycle 收集 + must-NOT |
| 三路确认 | 第一轮 9 MAJOR 全部核实解决；expiry/CLI-hit 两驳回裁定被接受 | 记录 |

### r3 定稿确认（grok）

| 来源 | finding | 处置 |
|---|---|---|
| grok-NIT | 漏第三条显式入口 `vibe skills cleanup --auto`（cleanup_cmd.py:181-194，skill_commands.py:1304 接线） | 采纳→§0/§2.2.8/§4 全改"三处"；feedback_loop/skill_commands docstring 同步 |
| grok-NIT | CLI has_match 锚点实为 :914 非 :920 | 采纳→§1.1 行号修正 |
| grok-NIT | 文档邻行漏网：GOALS.md:55、ARCHITECTURE.md:603、ROADMAP.md:354、USE_CASES.en.md:281,291,300 | 采纳→§4 |
