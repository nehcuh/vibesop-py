# Gate37 Lane B 评审报告：技能评价体系（架构/正确性视角）

## 0. 核查结论摘要（与背景假设不符的三处事实）

1. **analytics.jsonl 是 opt-in，默认关闭**（unified.py:1216 `_analytics_enabled()`，F-06 隐私条款）。`count_skill_route_hits`（discovery.py:599）docstring 承认"文件不存在 → 暂无数据源"。**以 analytics 为主数据源的 L2 在默认安装下拿到空表。** 真正 always-on 的是 spans.jsonl（tracer 默认开，tracer.py:46）。
2. **route_outcomes.jsonl 只覆盖 miss，不覆盖 hit**（tool_call_bridge.py:414 `_derive_outcomes` 先过滤 `_is_miss`）。命中（fire）没有 outcome 行；且 outcome 是 write-once 弱信号，文件头声明"不得当作 ground truth"。"outcome 记录存在"对 miss 成立，对 fire→成功归因**不成立**。
3. **显式反馈路径有重复计数副作用**（cli/feedback.py:38-44：读出最后一条 analytics 记录、改 user_satisfied、再 record() 追加完整新行）。每次反馈让该 skill 在 count_skill_route_hits 里多计一次命中。

## 1. 逐层可行性

### L1 安装时 lint — 可行，零数据依赖
- 安装面：外部 skill 唯一入口 `PackInstaller.install_pack`（pack_installer.py:98），market install 同走；`_audit_skills`（:270）已是逐 SKILL.md 挂载循环；现有唯一内容门 `_is_valid_skill`（:630，description≥10 字符）。
- 可复用件：extract_frontmatter、_is_agent_prompt_shape、query_matches_triggers、gate36 lint checks（promote_verifier.py:431-449）；embedding 碰撞线用 DI seam（照 verify_draft）。
- 约束：安装链对 CRITICAL/HIGH fail-closed，L1 必须保持 advisory(WARN)；conftest stub 下 embedding 不可用，照 promote_verifier 的 unavailable 模式。

### L2 观测记分卡 — 部分可行，核心指标缺数据源
| 指标 | 数据源 | 可行性 |
|---|---|---|
| 触发率 | spans.jsonl route span（metadata.skill_id+has_match，agent_runtime.py:668-692） | ✅ always-on |
| fire→成功率 | **不存在** | ❌ |
| 劫持率 | **不存在**（候选从未持久化） | ❌ |
| 衰减度 | spans 时间戳分窗 | ✅ |
| 内容分 | L1 输出 | 依赖 L1 |
- fire→成功率可行路径：把 `_classify`（tool_call_bridge.py:495）弱信号推广到 hit——`reask_same_task_id`/`session_moved_on` 对 hit 同样成立；join 键 task_id+session_id，24h 窗；**建议新文件/新 outcome 类别，不改 _is_miss/_classify 现有语义**（miss outcome 口径被 M2 消费，改了污染既有基线）；必须继承 CLI 一次性会话排除（否则 24h 过期全变 hollow weak_positive）。
- 劫持率：route span 只写 winner；alternatives 只在内存/显式反馈记录。要算须在 span metadata 加 additive top-3 字段，或由 L3 离线产出。

### L3 消融回放 — 可行，但复用对象要选对
- 正确基座是 **scripts/eval_routing.py**（全路由器离线回放，record_telemetry=False，真 UnifiedRouter），不是 replay_routing_baseline.py（p0_shadow 与生产刻意分歧；build_hit_hijack_risks 是"假设激活 P0"反事实不是消融）。
- 铁律：消融报告不得引用 p0_shadow 数字；报告带 dataset hash + catalog hash + RULESET_VERSION 风格版本字段；embedding 模型版本必须记录（无 pin）。
- 语料复用 load_route_records，尊重 200 字符截断标记。

### L4 活体基准集 — 已存在 80%，提案有重复造轮子风险
- 现状：tests/benchmark/routing_eval.yaml + routing_eval_extended.yaml（107 条 scored）+ routing_eval_oneshot.yaml + routing_eval_retention.yaml（带 retain_until）已在 git；harness scripts/eval_routing.py（top-1/Recall@3/expect/reject 齐全）；补给管线 scripts/build_eval_from_logs.py（stratified+weak label+needs_review）。
- 缺口只有两个：(a) CI benchmark job（ci.yml:184-202）跑 pytest -m benchmark，**没有任何测试执行 eval_routing.py**；(b) gate10 记录的环境依赖缺陷——extended 集 5/8 正例要求评测环境装着 superpowers/omx pack，裸环境系统性 miss。
- 定位："把既有 harness 升格为 CI 门 + 修环境依赖 + 标签卫生"，远小于新建。

## 2. 文件级实施路线（摘要）
- L1：新增 core/skills/skill_lint.py（静态检查+可选 embedding 碰撞 DI fail-open）；挂 pack_installer._audit_skills 与 skill_installer；加 `vibe skill lint <path>`；测试无需 embedding（DI _FakeModel）。
- L2 分两步：**L2a 仪表化**（agent_runtime.py:668 附近 span metadata 加 top_skills ≤3 个 (skill_id,confidence)；tool_call_bridge 新增 hit 侧 outcome 派生、新 outcome 类别）；**L2b 记分卡**（新 skill_scorecard.py 只读 read-model，或扩展 aggregator.py；展示走 _discoveries.py 模式）。
- L3：scripts/replay_ablation.py（eval_routing 基座 + catalog 摘取 + 版本字段）。
- L4：改 ci.yml 让 eval_routing.py 进门 + 修 pack 依赖子集标注；注意真模型加载分钟级，CI 缓存策略。

## 3. 层间依赖
- L1→L2：内容分依赖 L1；lint 结果持久化（照 promote_verdicts 惯例），L2 只读。
- 词汇冲突：gate36 "hijack"=激活前 trigger 碰撞；L2 劫持率=运行期抢单——必须分开命名（建议 L2 用 preemption）。
- L3 依赖 L4 的标注纪律做裁决；L4 CI 门保护 L2 仪表化改动。

## 4. 独立优先级
**L4 第一**（80% 已存在，增量=CI 门+环境修复；是其他三层的安全网）→ **L1 第二**（零数据依赖，提升输入质量）→ **L3 第三**（eval_routing 基座现成，依赖 L4 标注）→ **L2 最后但先拆 L2a 仪表化**（完整记分卡卡在 hit outcome 与候选记录不存在；把 L2 排最前会逼出在 opt-in analytics 上凑指标的坏设计）。

## 5. 技术陷阱（12 条，主代理未提及）
1. analytics opt-in 默认关——L2 主源必须 spans.jsonl。
2. 反馈路径重复行虚增命中计数。
3. hit 侧 outcome 空白 + write-once 弱信号警告。
4. span status≠skill 成效（task span ok 只是管道没抛错，误读则成功率恒 ~100%）。
5. 运行期劫持率无数据（候选未持久化），须先加仪表字段。
6. 200 字符 query 截断标记须尊重。
7. session 语义：CLI 一次性会话不排则被 hollow positive 淹没。
8. 三套语义并存（p0_shadow/query_matches_triggers/EmbeddingMatcher），混用即结论无效。
9. skill_id 不稳定即断链（改名后 join 失效，需辅助键）。
10. embedding 模型无版本 pin，基线可比性风险。
11. conftest stub 下 embedding 恒 unavailable——一切 embedding 检查须 DI+降级测试。
12. L4 环境依赖未修复就上 CI 门会第一天就红。
