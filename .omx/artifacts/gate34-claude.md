代码核查完成（约 20 处引用逐一对照原文）。以下为评审。

## Verdict
PASS_WITH_NITS

## Findings

- [MAJOR] **阶段二 verdict store 绕过 M12 M5 隐私边界，三路+裁决稿均未审**。`_render_skill_md` 对 `scope="global"` 强制不携带原始 query（skill_promote.py:1954-1959，理由是“草稿可跨机器流动”）；而 verdict 明细要求记录“未捕获 query + 各自最近邻”——`promote --scope global` 时这些是跨项目原始 query。若 verdict 落项目目录 `.vibe/observability/`，则 A 项目的 verdict 文件含 B/C 项目 query；若落全局目录，则多项目 query 汇聚单文件。且看板 payload 同读 project+global 两 scope（`_discoveries.py:60,89`），裁决 2 第 4 步把 verdicts 段加进 payload 会把 global verdict 明细直接带给看板——渲染层刻意维持的边界被新 store 侧漏。需在路线里明确：global scope 的 verdict 只存计数/哈希，或 verdict 只落发起 promote 的项目且 payload 按 scope 过滤明细。
- [MAJOR] **阶段一批量 dismiss 机制未指明，且与现存 threshold_suggestion 反馈环直接冲突**。`vibe skill discover dismiss` 写的是 DiscoverySignalStore 指纹负名单，**不翻候选行状态**（skill_commands.py:2627-2632），且每次 dismiss 计入 `_discovery_dismiss_total()` 喂 `threshold_suggestion`（skill_commands.py:2658-2665）。批量 dismiss 几十条 agent-echo 会推高 dismiss 计数、触发“上调准入阈值”建议——用机器回声污染 D3 统计列（裁决 3）要展示的同一组计数，阶段一内部自相打架。且走负名单的话候选行仍占 `MAX_PENDING=50`/`UNSTABLE=20` 容量直到 30 天 TTL（skill_promote.py:100-110），队列减负目标打折。实施前必须裁决：shape 批量否决走 pool status 翻转（`vibe skill dismiss` 机制）还是负名单+豁免计数。
- [NIT] **“为什么在这里”行的字段承诺不实**。裁决稿阶段一第 1 步称“从 ClusterCandidate 字段直译：miss 跨 N 天复现 M 次”——已核对 `ClusterCandidate` 全部字段（skill_promote.py:425-469），**没有** recurrence pairs/days 字段，只有 `source="miss_recurrence"`。要么加字段（schema 变更 + `from_dict` 容忍 + round-trip 测试），要么文案降级为“miss 复现入池”。裁决稿自己的验收标准（“与字段一致防文案说谎”）会当场抓住这条。
- [NIT] **阶段二第 5 步大部分已 ship**。`_render_skill_md` 已在 `core_steps` 非空时预填 Steps 块（skill_promote.py:2036-2039），gate31 已交付 fill-in skeleton（git log 97c8c30）。剩余增量只有“标注生成来源”和空 `core_steps` 簇（后者是数据不存在，任何预填都救不了）。Lane A/C 的“空壳模板”叙事基于旧代码状态，裁决稿照单全收，该项工作量描述失真。
- [NIT] **verifier 回放口径未定义，草稿 name/description 中性化会系统性压低分**。draft 的 name 是 `draft-<cluster_id>`（M7 F3，skill_promote.py:1970）、description 是 provenance-only 稀释剂——若 shadow 回放包含 index/embedding 侧而非仅 trigger 侧（`p0_shadow` 口径），好簇也会因 name 无 +0.4 containment bonus 而 WARN。Lane C 反驳 4 只讲了“trigger 会被手改”，没讲这个更结构性的口径问题。需明确 verdict 仅回放 trigger 侧，或在明细中声明该降级。
- [NIT] **D2 重议门槛的度量措辞错位**。裁决稿定义测 (b) “>150 字符且非 agent 形状的 miss 占比”，重议条件却写“长 query **误杀率** <1%”——(b) 是风险人口占比，不是过滤器误杀率。未来重议会拿错数。
- [NIT] 引用小勘误：Lane B 的 "indexer.py:455" 实际路径为 `src/vibesop/core/skills/indexer.py`（0.45 门注释在 462-463）；e2e "65/65" 静态未能复现（`record()` 调用点 11 处、多在循环内，运行时总数 [assumed]）。转述内容均准确，不影响结论。

**代码事实核查总评**：三路报告引用的约 20 处关键位置（gate32 注释 341-349、谓词 366/363、intake 1429-1433、分源阈值 141-167、≥30 再标定纪律 164-165、draft_sha256 守卫 453-460、hand-edit docstring 515-527、渲染器 1916+/2048-2052/1990-1992、promote 链路 skill_commands.py:1959/1967/2024、replay 脚本 ：52/:139/:151、span_writer.py:110-127、conftest.py:281、triage_recall floor 0.25、discovery.py:107/524/550、决策文档 ：143 确在“宜吸收（UX 纪律）”节下）**全部真实且转述准确**，无一虚构。

## 对各裁决点的意见

**裁决 1（D2 只展示层）**：站得住。决定性证据核实无误——gate32 注释原文确称回声为合法池成员且 bd1bc217 是唯一真实 promote 成功案例；150 上限在 intake 侧是数据丢失方向；0.8 落在 0.41–0.88 标定无人区。展示层 + 一次性测量 + 谓词冻结（保 replay 基线可比性，:52 import 属实）是正确的最小集，重议门槛设计合理（措辞见 NIT）。

**裁决 2（D1 shadow-only）**：形态正确，三路交集真实存在，n=3 区分度批评（`DEFAULT_MIN_CLUSTER_SIZE=3`，:141）与 ≥30 再议纪律均成立。但两个补丁不够：verdict store 隐私（MAJOR 1）和回放口径（NIT）都必须在 gate36 动工前补进设计，否则“描述性明细”本身会制造新的污染面。

**裁决 3（D3 只读统计列）**：站得住。分闸已存在核实属实（158-167），细分桶 n≈4 伪科学成立，代码库自带的 ≥30 纪律（:164-165）引用准确。唯一问题是被 MAJOR 2 连累——批量 dismiss 会污染这列要展示的 dismiss 计数，两者必须在阶段一一起定义口径。

**裁决 4（D4 否决）**：站得住，四条反对全部有实码支撑（hand-edit 是明示支持的用法 ：515-527、prune/留存池生命周期冲突、出处是对定位文 UX 节的误读——已核实原文语境确为“evaluation snapshot 不因 rubric 编辑改写”而非防篡改）。sealer 设计存档不立项是正确的成本姿态；若未来需要，Lane C 的 `vibe trace verify <id>` 按需重算版本比 sealer 更轻，决策记录里值得两者并列。
