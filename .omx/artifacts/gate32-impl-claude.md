# Gate 32 实施复审 — v3

## Verdict: **PASS_WITH_NITS**

(1 项残留 MAJOR + 4 项 NIT;无 BLOCK。)

**先说一个流程事实**：复审 prompt 里嵌入的 diff 是**旧版**(v2 实现)。工作树已吸收过一轮 pi impl 评审(`.omx/artifacts/gate32-impl-pi.md`)——其 MAJOR-1(hit 劫持检测 + agent 误触发计数)与 NIT-1/2/4/5/6 在磁盘上全部修复。本评审以**工作树**为准(`git diff HEAD` 对账后逐文件实读)。`gate32-impl-claude.md` 是空文件(仅 1 行)，该路评审未落地。

**验证执行** [executed]:162 项 gate 测试 + 577 项 observability 全目录测试全过；ruff 除 scripts/ 下 1 个 I001 外干净(项目 lint 命令 `ruff check src/ tests/` 不含 scripts/,不咬 CI);`_render_skill_md` 渲染 → YAML 结构逐行实读。cmspark 首跑数字(3549/650/22/29)[assumed]——外部语料，本仓库不可复现(pi NIT-4 同判)。

---

## Findings

### MAJOR-1 — pi impl MAJOR-2 未处置：0.45/margin 分布前后测量缺失
`indexer.py:467`(`_compute_profile_text` 追加 triggers)+ `indexer.py:386-388`(每次 build 全量重算 embedding)。

A2 改变**全量技能**的 0.45 门输入文本，下一次 `vibe skills index` 即生效。grok M2/M5「可以不改阈值，不能不测」、claude NIT-5「分布移动是大概率」、pi BLOCK-3 返工清单第 3 条「A1+A2 作为同一校准单元重测」——工作树代码、CHANGELOG、测试均无 before/after 分布证据；replay 脚本只测 route 级 miss/hijack,不覆盖 semantic_index 得分分布(标定集 margin 0.071 vs 0.0702 的脆性记录正对着这里)。
**修法**：全量 rebuild 一次，记录 0.45/margin 得分分布与标定集正例 margin 对照，作为 CHANGELOG 验收数字；或至少把该项显式写进「推迟项(带触发条件)」。属测量债不属代码 bug,故不 BLOCK。

### NIT-1 — shadow 归一化与生产规则口径差异未文档化(复审重点 3 直答)
`scripts/replay_routing_baseline.py:130-132` vs `triage_service.py:533-536`。生产 `has_explicit_guard_signal`:lowercase + **撇号剥离**(`'`/`’``)、**无空白折叠**、containment **无长度下限**、first-hit-wins。shadow:lowercase + 空白折叠、不剥撇号、≥6 字符下限、全记录 + collision。双向系统性偏差(撇号变体、<6 字符 trigger、多空格 query)。entries 保留 raw query 可事后重派生，B1 激活前也强制重跑带护栏 shadow,故仅文档级：建议 docstring 补一句与生产谓词的刻意分歧说明(如同 `is_route_miss_span` vs `_is_miss` 的写法)。

### NIT-2 — `queries[:5]` 先切片后过滤
`skill_promote.py:2016-2020`。前 5 条样本全被卫生过滤时直接 TODO,即使列表深处有干净样本(grok 副作用 5 的残留半边)。fail-safe 方向(人手写 trigger),可接受；改成“过滤后再取前 5”一行可解。

### NIT-3 — ruff I001(scripts/replay_routing_baseline.py:46-58)
import 块排序(`skill_promote` 导入块应并入上方块)。CI lint 范围不含 scripts/,`--fix` 一行修。

### NIT-4 — `gate32-impl-claude.md` 空产物
评审管线三路只剩两路落地，gate 记录不完整；补跑或删除占位。

---

## 四个复审重点的结论

**1. A1 卫生谓词边界** — 会误杀，但按设计接受，非缺陷：`"you are "` 前缀的合法英文指令、>150 字符长指令、`"background task "` 开头的功能查询都会被拒于预填外；后果全部是「人手写 trigger」(prefill-only),且编辑守卫兜底。测试钉死了权衡边界(`"you are"` 无尾空格放行、150 字符边界)。pi impl NIT-3 已裁决，我复核同意。

**2. A2 restamp × content_hash 论证 — 正确，且我找到了 restamp 的第二重价值**:
- 前提核实 [executed]:`_build_prompt`(indexer.py:518)以 `", ".join` **全量、无截断**地把 triggers 编入 prompt(body 才有 `[:4000]` 截断)→ 改 triggers 必变 prompt → 必失 hash → 走 fresh 路径。论证成立。
- 我额外排除了一个隐患：cache-hit 复用旧 embedding 的陷阱**不存在**——`build_index:386-388` 把 cache-hit 与 fresh 合并后统一 `_compute_embeddings`,且该函数(470-503)不跳过已有 embedding,每次 build 全量重算。pack 增量路径的暂态不一致已文档化(indexer.py:748-754,"Accepted")。
- 反例：现状无实用反例(sha256 截 16 hex 碰撞可忽略；仓库历史上不存在不含 triggers 的 prompt 版本)。唯一真实反例类是**未来 prompt 模板改动把 triggers 移出 prompt**——那一刻 restamp 从迁移价值升级为承重墙。restamp = pre-1.5.0 迁移 + 前向防御，双路径填充是正确的防御性选择。测试 `test_cache_hit_restamps_triggers_from_live_spec` 恰好钉住迁移场景。

**3. P0-shadow 与未来 P0-lite 口径** — 规则族一致(归一化 substring containment),细节五处不一致(归一化两维、长度下限、exact 独立规则 vs 生产 containment 已涵盖、first-hit-wins vs collision 记录)，见 NIT-1。结论：shadow 数据作为**「信号存在性」基线有效**，作为**「激活数据集」无效**——B1 全套护栏(IDF、否定词、仲裁)必然更严，原始计数会高估 gated would-fire。entries 记录 raw query + rule + trigger 支持重派生，且 B1 触发条件已含「激活前带护栏 shadow 周期」。CHANGELOG 措辞已按 pi 建议修正(「精度待人工裁决……原始覆盖率是上限不是正确性证据」)。

**4. 测试钉住 must-fix 情况** — 逐条核对：

| 评审 finding | 状态 | 钉住测试 |
|---|---|---|
| pi BLOCK-1 / grok M5 / claude MAJOR-2(profile 字段+通路+版本) | ✅ | `test_spec_triggers_*`、`test_triggers_round_trip`(含 legacy 缺键)、`test_fresh_path_populates_triggers`、`test_cache_hit_restamps_*`、版本 pin 到 `INDEX_VERSION` 常量 |
| pi BLOCK-2 / claude MAJOR-3(数据源=人工过目的 frontmatter) | ✅ | 结构性：编辑守卫实存(skill_commands.py:2063-2099,byte-identical 拒绝);`_spec_triggers` 只读 live spec,无第三通道 |
| pi BLOCK-3 / grok M1(query_patterns 不污染) | ✅ | `test_query_patterns_not_polluted_by_triggers`(pi impl NIT-5 修复) |
| pi MAJOR-1 / grok M4 / claude MAJOR-1(B4-lite) | ✅ | `test_agent_prompt_shapes_and_low_info_filtered` + 谓词边界测试 |
| pi MAJOR-2 / claude MAJOR-2(global 隐私) | ✅ | `test_global_scope_never_prefills_raw_queries` |
| grok M3(metadata query + 200 截断) | ✅ | `test_truncation_marked_at_cap` + records 系列(含 JSON 串/dict 双形态) |
| pi impl MAJOR-1(hit 劫持 + agent 误触发) | ✅ | `TestHitHijackRisks`(agreeing≠risk、diverging 记录、miss 不评估)+ `test_agent_shape_would_fire_counted_but_excluded` |
| claude MAJOR-4 / grok N3(B1 触发条件) | ✅ | CHANGELOG 推迟项带条件 |
| grok M2 / pi impl MAJOR-2(分布测量) | ❌ | 无实现可钉 → 本评审 MAJOR-1 |

**一句话**：A1/A2 闭环修复按三路评审约束落地干净(数据源唯一、编辑守卫完好、Jaccard 快路径有回归测试钉住、restamp 论证经反例排查成立)，A3 双侧基线(收益 + 精度)已补齐且有测试；把 0.45/margin 分布前后测量补上、顺手清 4 个 NIT,即可关 gate。
