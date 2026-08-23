# Gate37 综合设计：技能评价体系的对抗收敛与实施路线

> 输入：gate37-laneA-product.md / gate37-laneB-arch.md / gate37-laneC-skeptic.md
> 性质：主代理裁决稿。分歧点全部显式裁决。

## 0. 本轮对抗的独特价值

Lane B 核查出三个颠覆性事实，直接否决了原提案的数据假设：

1. **analytics.jsonl 默认关闭**（F-06 隐私 opt-in,unified.py:1216）——以它为主数据源的任何设计在默认安装下拿到空表；always-on 的是 spans.jsonl。
2. **route_outcomes 只覆盖 miss，不覆盖 hit**(tool_call_bridge.py:414)——"fire→成功率"目前**没有数据源**。
3. **L4 已存在 80%**:tests/benchmark/routing_eval*.yaml（含 107 条 scored)+ scripts/eval_routing.py + build_eval_from_logs.py 都在 git，只差 CI 门与标注卫生。

Lane C 的元备注成立并采纳：本提案与 gate34 D1-D4 高度同构（L1≈D1 lint、L2≈D3 统计、L3≈已 ship 的 shadow、L4 CI 硬阻断≈D4 已否决）。**流程新规：今后新提案先对照 gate34 不做清单做"换皮检查"。**

## 1. 三路结论对照与裁决

| 层 | Lane A | Lane B | Lane C | 裁决 |
|---|---|---|---|---|
| L1 lint | 第一优先 | 第二优先 | 仅 ≤3 规则警告版 | **做极简版**（三路共识区间） |
| L2 记分卡 | 瘦身版（3 事实） | L2a 仪表化先行，L2b 最后 | 推迟，只许只读列 | **拆:L2-lite 现在做，L2a gate38,L2b 推迟** |
| L3 消融 | 按需工具 | 第三优先（eval_routing 基座） | 否决（n=1、第三份回放设施） | **否决当前形态**，重启条件写明 |
| L4 基准集 | 移出产品范围 | 第一优先（升格 CI 门） | 否决 CI 硬阻断，只追加真实样本 | **不做 CI 硬阻断；只追加真实样本** |

## 2. 裁决明细

### 裁决 1:L1 极简 lint —— 做（gate37 主体）

采纳三路交集：
- **规则集 ≤3 条静态检查**（以 §6 修订 A 为准）：triggers 非空且非全卫生形状 / 正文非 gate31 TODO 空壳 / description 存在性（复用 `pack_installer._is_valid_skill` :630 的 ≥10 硬门）。when-not-to-use 与营销句式两条已删（修订 A)。
- **形态**:advisory 警告，只警告不阻断、无分数、不上看板；每条 finding 一行白话（Lane A 纪律）；挂 `pack_installer._audit_skills`(:270 现成挂载点）+ 新 `vibe skill lint <path>`。
- embedding 碰撞线本 gate 不做（conftest stub 下不可测的部分不 ship)。

### 裁决 2:L2 拆三层 —— L2-lite 现在做，L2a 进 gate38,L2b 推迟

- **L2-lite(gate37)**:`vibe skill list` 加健康摘要列（全部口径以 §6 修订 B + §6.1 修订 B 补丁/H 为准）。只展示**今天就有数据源的事实**：来源（`_get_skill_source` 三值口径，pack 折叠为 external——"promote/手工"无数据不标，标了就是说谎）、近 30 天 fire 计数（**从 spans.jsonl**——always-on,Lane B 证实；不用 analytics)、显式反馈原始计数（正/负原始数，**不算比率**——Lane A/C 一致：n<10 的"成功率"是自欺）。"从未 fire"仅作信息展示，**禁止派生任何处置动作**(Lane C：杀掉的技能不再产生数据证明杀错）。列头/文案带"n<30 不下结论"纪律标注。
- **L2a 仪表化（gate38 候选，本 gate 不做）**:span metadata 加 additive top_skills(≤3)+ hit 侧 outcome 派生（reask_same_task_id/session_moved_on 推广到 hit，新 outcome 类别，**不改 _is_miss/_classify 语义**)。理由记档：fire→成功率与劫持率目前**无数据源**，不先补数据就永远只能凑假指标；但它触生产 span/bridge 路径，需要自己的复审轮，不进 gate37。
- **L2b 完整记分卡：推迟**。前置条件（两条件同时满足，沿用代码库自带纪律）：verdict ≥30 条 且 单技能月 fire ≥30。
- **词汇裁决**：运行期抢单命名 `preemption`，与 gate36 的 hijack（激活前 trigger 碰撞）分开（Lane B)。

### 裁决 3:L3 消融 —— 否决当前形态

采纳 Lane C：消融对象 n≈1、回放设施已有两份（replay_baseline + promote_verifier)、650 miss 语料被回声掏空后有效 n≈0、离线回放原理上答不了活体因果。重启条件：**promote 技能 ≥30 且 verdict ≥30**（以 §6 修订 D 为准）；届时以 **eval_routing.py 为基座**(Lane B 纠正：不是 replay_baseline 的 p0_shadow，后者与生产刻意分歧）跑一次性摘除敏感性分析，产出一次性报告，**不建常驻 harness**。

### 裁决 4:L4 —— 不做 CI 硬阻断，只追加真实样本

- Lane C 的 D4 同构论证成立（技能池是数据，CI 为数据漂移硬阻断=合法操作变告警+告警疲劳）。**CI 硬阻断形态否决。**
- 做 Lane C 最小版：把 cmspark 真实 promote/dismiss 的 query（带真实人工裁决标签）追加进 `tests/benchmark/routing_eval*.yaml`，流程以 §6 修订 E + §6.1 修订 I 为准（导出→extended needs_review:true 且**强制 redact**→人审→--merge;dismiss 样本走 retention yaml)。
- Lane B 的两个缺口（eval_routing 不进质量门、pack 环境依赖子集）记为**待议项**，前置讨论点：report-only CI job（非阻断）是否可接受——留到 gate38 与 L2a 一起议（L2a 触路由写入路径时，回归安全网才有紧迫性）。

### 裁决 5:meta 流程

新提案立项前先对照 gate34 不做清单 + 本裁决书做"换皮回归检查"（Lane C 元备注，第二次发生，升级为流程）。

## 3. gate37 实施范围（一天级）

1. `src/vibesop/core/skills/skill_lint.py` 新模块（≤3 静态规则，以 §6 修订 A 为准；白话 finding，零阈值）；挂 pack_installer（安全审计之后独立 advisory 行）+ skill_installer `warnings[]` 输出；`vibe skill lint <path>` 子命令。
2. `vibe skill list` 健康摘要列：来源（三值口径）/30 天 fire（spans 派生，read-only，口径以 §6 修订 B 为准）/反馈原始计数（§6 修订 B+H)；n<30 纪律文案；无任何处置动作派生。
3. routing_eval 真实样本追加：流程以 §6 修订 E+I 为准（导出→extended needs_review:true 且过 redact→人审 expect→--merge;dismiss 样本走 retention yaml)。
4. 测试：lint 规则正反例（must-NOT-catch 反例惯例）、list 列 read-model 测试（合成 spans fixture)、eval yaml 追加脚本测试。全量 pytest 零回归 + e2e。

## 4. 显式不做清单（防复活）

- fire→成功率比率、劫持率/preemption 记分卡列、衰减度列（L2b 范畴，前置条件未到）
- L2a 仪表化（gate38 议）
- L3 常驻消融 harness（重启条件：promote ≥30 且 verdict ≥30)
- L4 CI 硬阻断（永久否决）；report-only CI job 留 gate38 议
- 任何自动降级/删除路径（永久边界；上限=gate35 式 --yes 确认）
- embedding 碰撞 lint 线（无 DI 可测性前不 ship)

## 5. 与旧坑的关系

本 gate 不挤占任何触发器（grok probe/M3/留存池 9-19/verdict 攒数/P0-lite 全在等数据）。L2-lite 的 fire 计数展示恰好让"verdict/数据攒得怎么样"第一次对用户可见——是数据积累的可视化，不是新坑。

---

## 6. 三路评审收敛（claude / pi / grok 均 PASS_WITH_NITS，0 BLOCK；12 个 MAJOR 去重后 8 项，全部吸收）

评审产物：gate37-claude.md / gate37-pi.md / gate37-grok.md。层裁决不变，实施口径全部钉死如下：

### 修订 A:L1 规则集收敛到 ≤3 条可测谓词（grok-MAJOR-1/2、claude-NIT、pi-NIT）
- **删掉**"有 when-not-to-use"（全仓无此 schema/正文惯例，spec/models.py:101-102 只有 trigger_when/triggers——按字面实施会对存量含 builtin 100% WARN,D4 告警疲劳复现）与"description 非纯营销句式"（被否决的"可路由性阈值"换皮；现有硬门 `_is_valid_skill` desc≥10 已够）。
- 最终规则集：① triggers 非空且非全 `_is_agent_prompt_shape` 卫生形状；② 正文非 gate31 TODO 空壳（骨架槽位残留检测）；③ description 存在性（复用 ≥10 硬门，不另造）。每条带 must-NOT-catch 反例测试（仓内惯例）。
- **挂载口径**：`_audit_skills`（pack_installer.py:270-281）是安全审计挂载点且 CRITICAL/HIGH fail-closed——lint **不得**喂进 `is_safe`/`has_high`，在安全审计之后追加**独立 advisory 行**；单技能入口走 `skill_installer.install_skill` 的 `warnings[]`(:73)。

### 修订 B:L2-lite 三列口径全部钉死（grok-MAJOR-3/4/5、claude-MAJOR-1/2、pi-MAJOR-1/2）
- **来源列**：只用现有三值 `builtin/project/external`(SkillSource，external_loader.py:22-27);"promote/手工"无数据（promote 不写 provenance 到 SkillConfig)——不标，写了就是说谎。
- **fire 计数谓词**:`span_kind=="task"` ∧ `name.startswith("route:")` ∧ `metadata.has_match is True`（口径先例 gold_detection.py:108-163);metadata 在文件中是 JSON 字符串须反序列化；**镜像 `is_dev_environment()` 的 spans.dev.jsonl/spans.jsonl 文件选择**(span_writer.py:65);**单次全表扫描**，禁 per-skill 重读、**禁持 flock**(writer 用 LOCK_EX，持锁会卡 hook 热路径，span_writer.py:47-50);file-missing→空、不 mkdir(_discoveries.py:29-33 守卫惯例）。列头标"**本项目**"（spans 按项目落盘，全局技能跨项目 fire 不可见——系统性欠报如实标注）。
- **反馈列**（⚠ 本句已被 §6.1 修订 H 取代，以 H 为准）：钉死 `ExecutionFeedbackCollector`(core/feedback.py:352）项目级 `.vibe/execution_feedback.jsonl`，复用 `get_skill_summary`(:393)，不新写解析器；空数据显示"无记录"（**禁止暗示中性**);fire 与反馈来自不相交总体（hook 路径无反馈 UI)，文案注明。反馈重复行陷阱（cli/feedback.py:38-44 追加新行虚增命中）已由"不用 analytics"规避。
- **断链披露**:skill_id 改名/重装后历史 fire 计数归零、`/`vs`-` 规范化断链（candidate_manager.py:140-141)，列文案/文档注明。

### 修订 C：点名仓内既有"假 L2"，不做清单扩充（grok-MAJOR-6)
仓内已有 `vibe skills report`(Grade/Score/Success%;`quality_score` 在 total_routes==0 仍返回 ~0.5,evaluator.py:64-66）与 `FeedbackLoop.analyze_all(auto_deprecate=True)`（自动 deprecate F 档，feedback_loop.py:66-86)——**与"永久不做自动降级"直接冲突**。本 gate:新列**不得**调用 evaluator/aggregator.success_rate;`stale --auto` 保持人审闸不接线；上述两者的处置（修 quality_score 零样本返回值、auto_deprecate 默认关）记为 gate38 待议项。

### 修订 D:L3 重启条件统一（pi-NIT、grok-NIT、claude-NIT)
promote ≥10 的放宽无论证，收回。统一为 **promote ≥30 且 verdict ≥30**（与 Lane C 原判及 L2b 前置量级一致）。

### 修订 E:L4 追加流程强制项（claude-MAJOR-3、grok-NIT、pi-NIT)
（⚠ 本段流程描述已被 §6.1 修订 I 取代——`--merge` 吃不下导出、merge 路径无 redact、"禁止手改 yaml"仅限主集；以 I 为准）真实 query 进 git yaml 是一次性泄漏面（与 F-06 同构）：追加**只走脚本**——复用 `scripts/build_eval_from_logs.py --merge`（自带 `strip_wrapper(redact_sensitive())` 纪律与 needs_review 标注），**禁止手改 yaml**；追加后 smoke-run eval_routing.py 验证可解析可跑。前置依赖写明：cmspark 已裁决标签的导出（用户侧动作）。全集勘误：34+107+11+22=174 条。

### 修订 F：数字勘误（pi-NIT、claude-NIT)
回声引用改为实测值：cmspark miss 池 525、池回声 4.8%、卡片回声 42.9%（gate35-echo-measure-cmspark.md);Lane B"extended 5/8 正例"→ 文件头自述 4/7;"skill list 健康叙事雏形"张冠李戴（那是 `_skill_overview` hub，:48-49；真正 list 只有五列）——加列目标不变，背书纠正；span 引用口径：668-692 是 task span(name=route:…)。

### 修订 G:meta 换皮检查落地（grok、claude 裁决 5 意见）
对照物路径写明：新提案立项前必读 `.omx/artifacts/gate34-synthesis.md` §不做清单 + 本稿 §4;**凡声称"已有数据源/现成件"必须附 文件:行号 核查清单**（claude 建议，Lane B 已示范）。

### 维持不变
L2a 进 gate38;L2b 前置（verdict ≥30 且单技能月 fire ≥30);L4 CI 硬阻断永久否决（report-only 留 gate38);lint 不碰 embedding 线；看板只读不动。

---

## 6.1 round2 复核收敛（claude/pi/grok 均 PASS_WITH_NITS；3 路合计 5 个 MAJOR 去重后 3 项 + 9 NIT，全部吸收）

评审产物：gate37-r2-claude.md / gate37-r2-pi.md / gate37-r2-grok.md。§2/§3/§4 正文已回写同步（grok/pi 共同 MAJOR：裁决层与实施层断裂，gate34 同型问题再现——以后修订收敛与正文回写同一动作完成）。

### 修订 H：反馈列最终口径（claude-MAJOR-1 / grok-MAJOR-1 / pi-NIT-3/5）
- 计数方法：`get_records()` 自行数 `was_helpful` True/False 原始数——`get_skill_summary`(:393-415）只返回 total+比率，照字面复用会打印比率，违反本 gate 自己的纪律。
- 存储分裂如实处理：`vibe skills feedback` 走**全局** `~/.vibe/execution_feedback.jsonl`（默认构造器，_quality.py:153)，交互式 TTY 反馈写**项目级** `.vibe/execution_feedback.jsonl`(cli/feedback.py:85-87)。本 gate 读项目级 + 文案披露"`vibe skills feedback` 的全局写入是既有断链、不计入"（不修，留档）。
- 偏置披露：`partial` 被记为 `was_helpful=False`(cli/feedback.py:33-35,58)——"负"计数混入"部分满意"，列文案注明。
- 总体关系表述更正（pi-NIT-2/claude-NIT)：反馈 ⊂ CLI 路径 fire（部分重叠），不是"不相交"。

### 修订 I:L4 追加流程最终形态（grok-MAJOR-2 / claude-MAJOR-2 / claude-NIT）
`build_eval_from_logs.py --merge` 只搬 `needs_review:false` 且 expect 非空的条目，且 merge 路径无 redact、抽取强制 `--analytics`（已否决的默认空源）。正确流程：**导出 → extended(needs_review:true，过 `redact_sensitive`)→ 人审 expect → `--merge`**;"禁止手改 yaml"仅指主集 yaml,extended 的人审编辑是流程内动作。**dismiss 样本（expect=[]）走 retention yaml**（或显式扩展 merge 条件，实施时二选一并记档）。脱敏从"继承输入"改为**落盘前强制 redact**(claude-MAJOR-2:cmspark 导出路径无人脱敏）。

### 修订 B 补丁（三路共同 NIT)
- `SkillSource` 实为**四值**（含 PACK,external_loader.py:28,:280 真实赋值）；三值来自 `candidate_manager._get_skill_source`(:309-315,pack 折叠为 external)。来源列用 `_get_skill_source` 口径，列头注明"pack 技能显示为 external"。
- fire 谓词补 is_cli 口径决定：沿用 gold_detection 谓词先例（CLI route hit 也写 has_match=True,gold_detection.py:125-129),**CLI 命中计入**并在列头注明（与"本项目"并列）——因为反馈 UI 恰好在 CLI 路径，排除 CLI 会让 fire 与反馈总体彻底脱节。
- `pack_installer._is_valid_skill` 路径限定（仓内有两个同名函数，explicit_layer.py:81 是存在性检查）。

### 修订 C 补丁（claude-NIT)
gate38 待议项附调用点清单：`auto_deprecate=True` 活调用点 5 处（cli/main.py:1707、render.py:66、optimize_cmd.py:106、feedback_loop.py:208/246)——修复不得只改签名默认值。另记档：promote 在草稿 description 内嵌 provenance 标记（skill_promote.py:2062)，来源列不标 promote 的决策仍成立（内嵌标记非结构化字段），但理由表述修正。
