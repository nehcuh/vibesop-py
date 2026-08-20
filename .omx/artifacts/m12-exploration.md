# Skill-Discovery 探索结论（共同事实基础）

来源：agent-50 对 vibesop-py 仓库的只读深查（2026-08-20）。两路设计均以此为准，可复查代码但不得改文件。

## 用户需求（原始表述）

在用户对话过程中进行语义洞察：如果发现多次类似的用户问题没有匹配上相应技能，但编程 agent 的处理方式类似，可以归结为一个独立的完整工作流，就将其记录为项目技能，并在看板中标注发现，支持用户提升为全局技能。

## 现状事实（已核实，含文件：行号）

### 1. 观测与记录（三条互不相通的线）
- **RoutingPendingStore**（src/vibesop/core/instinct/routing_pending.py:180）→ `.vibe/instincts/routing_pending.jsonl`。由 `UnifiedRouter._maybe_enqueue_routing_pending`（unified.py:1315）写入。字段：query（脱敏截 500 字符）、skill_id、confidence、kind（low_confidence|no_match|user_correction）、reason_zh、status、时间戳、query_hash。弱匹配层（levenshtein/custom/fallback_llm）即使高置信也入队。**限流：每天 ≤3 条**；低信息量 query 降级；24h dismiss 抑制。
- **MissCounter**（core/skills/miss_counter.py:55）→ `.vibe/miss_counter.json`。只存加盐 hash + 次数 + 首末时间戳，**不存原文**（隐私设计，但因此无法做语义聚类）。
- **Analytics**（可选默认关）→ `.vibe/analytics.jsonl`，含 query、routing_layers、duration。
- **缺口：miss 之后 agent 实际怎么处理（工具序列、是否解决）完全没有记录。** pending 的 resolved_at 只是人审时间。

### 2. 聚类（都是 query 相似度，不是行为相似度）
- **W1 span 聚类**（core/observability/clustering.py）：hard group 按 (project_id, sha1(归一化query))，soft merge 用 query embedding 余弦 ≥0.80（Union-Find）。步骤行为只在聚类后打标（label_step_frequency，core≥70%/common≥30%）。
- **P2 miss 聚类**（core/skills/missed_query_tracker.py）：token Jaccard ≥0.6（注释自认 CJK 效果差），产出流向 SkillSuggestionCollector，**不进 ClusterCandidate 池**。
- **结构断点**：`scan_candidates`（skill_promote.py:708）要求簇 span_count≥3 且 gold_rate≥0.60——**纯 miss 簇永远成不了候选**。

### 3. 提升闭环（已实现 CLI）
- `vibe skill scan-candidates`（手动/cron，未内置触发）→ 候选池（pending ≤50、admit-only-if-better、30 天 TTL）
- `vibe skill candidates` → 人审列表（stable/unstable、gold%、core steps、[XP] 跨项目标记）
- `vibe skill promote <id> [--scope project|global]` → SKILL.md 草稿（`.vibe/observability/skill_drafts/` 或全局 `~/.vibe/...`），name 用占位符 `draft-<cluster8>` 防未审先命中路由，附来源指标、示例 query（≤5 脱敏）、core steps、人工检查清单
- **人审闸门硬保证**：草稿目录不在路由发现路径；须手动 copy + `vibe skill add` 才生效
- **全局提升不是一键**：promote --scope global 止步于草稿 + 打印手动 copy 提示

### 4. 看板
- dashboard（src/vibesop/dashboard/server.py，FastAPI，`vibe dashboard`）：health/analytics/traces/spans/orchestration-dag/reflections/conversations/sessions
- **完全没有** cluster_candidates / routing_pending / miss 簇端点或 UI（index.html grep 零命中）

### 5. 技能作用域
- builtin（core/skills/ 包内）、project（.vibe/skills/）、global（~/.vibe/skills/）、central（~/.config/skills/）、平台（~/.claude/skills/）
- `vibe skill add --scope global` → ~/.vibe/skills/<id>
- 跨项目：`vibe pool add` + `scan-candidates --cross-project` 汇入全局候选池

### 6. 遥测与 gold 信号
- span 现状：`route:<query>`（metadata 仅 query 前 200 字符 + platform/mode）、`llm:<provider>:<model>`、replay/workflow_node
- **`span_kind="tool_call"` 有消费逻辑（dashboard/aggregator/dag_rebuilder）但 src 里无任何生产方**——编程 agent 真实工具调用轨迹未采集
- `conversation_import.py` 能从导入会话提取 tool_calls（只存 key），离线、不进 spans、不进聚类
- **gold 判定**（gold_detection.py:33）：簇成员 query 在 InstinctLearner 有 success_count≥1；span_count≥5 才算 gold。**success_count 只来自显式人工信号**（vibe instinct accept/dismiss、replay 确认）——没有「agent 实际解决了」的自动结局检测

### 7. 架构问题
routing_pending 头部注释自认与 SkillSuggestionCollector 平行分工——仓库实际并存**三条**挖掘管道（routing-pending 人审队列、SkillSuggestionCollector 序列模式、W4 簇候选），数据互不互通。

## 相关背景
- M11 刚完成 keyword/TFIDF 证据化评分（extended eval 91.6%），RoutingConfig 有完整 knob 体系
- 评测资产：tests/benchmark/routing_eval{,_oneshot,_extended}.yaml；eval 依赖本机 pack（环境相关已声明）
- 隐私约束是项目既有原则（MissCounter 加盐 hash、query 脱敏截断）
