# M12 设计案 B：对话语义洞察 → 技能发现（架构与数据流优先）

设计方：B（架构与数据流）。事实基础：`.omx/artifacts/m12-exploration.md`（agent-50 深查），本文所有引用文件：行号已二次复查核实（2026-08-20）。

## 0. 核心判断（三条）

1. **最大缺口不是"没有采集管道"，而是"采集管道没接到 span 体系"。** 仓库已有完整的行为捕获原语：`core/instinct/tool_sequences.py`（hook → `vibe sequence record-tool` → `.vibe/tool_sequences.jsonl`，10MB 轮转、只存工具名）+ `claude_code.py:393/504/655` 的 PostToolUse 安装器 + `aggregator/dag_rebuilder/dashboard` 三个 `tool_call` span 消费者。缺的是中间一段"装配"：把 hook 流水折算成 `span_kind="tool_call"` 的 span。**本设计不新建采集通道，只补这座桥。**
2. **miss 语义聚类不需要新算法。** miss query 已经产生 `route:` span（`agent_runtime.py:452`、`cli/main.py:755`），`task_id = sha1(normalize(query))` 已可硬分组，`clustering.py` 的 Union-Find + 余弦 ≥0.80 直接可用。真正要新建的只有两件事：**结局信号**（替代 `gold_detection.py` 的人工 success_count）和**行为一致性门**（工具序列相似度）。
3. **三条管道不合并存储，合并"出口"。** routing_pending（人审队列）、MissCounter（隐私计数器）、missed_query_tracker（即时提示）各有不可替代的写时职责；收敛发生在候选池：`ClusterCandidateStore` 成为唯一出口，`missed_query_tracker` 降级为候选池的实时投影。

## 1. 目标数据流图（文字版）

```
[热路径: vibe route / 平台 hook(UserPromptSubmit) → agent_runtime.handle_query]
   │
   ├─ route:<query> span ───────────────────────────────→ spans.jsonl   (已有, agent_runtime.py:452)
   ├─ miss? ──→ MissCounter.record(hash)                             (已有, unified.py:1300, 不动)
   └─ miss/low-conf? ──→ RoutingPendingStore.try_enqueue             (已有, unified.py:1315, 不动)

[行为捕获: 平台 hook(PostToolUse) → vibe sequence record-tool]      (已有 claude 通道; M1 扩展 kimi/pi)
   └─ tool_sequences.jsonl {tool, ts, session}                       (已有, tool_sequences.py:67)

[装配: vibe sequence assemble (懒触发/cron/scan 前置)]              (M1 新增桥, 复用 cursor 水位)
   ├─ join: tool_sequences ⋈ spans  ON (session_id, 时间窗)
   │      └─→ tool_call spans ───────────────────────────→ spans.jsonl   (★新生产方)
   └─ 结局标注: 重问检测/会话完成/显式 accept
          └─→ outcomes.jsonl {task_id, session_id, outcome, strength}    (★新小文件)

[发现: vibe skill scan-candidates (批量, 手动/cron)]
   └─ cluster_queries(spans)              (复用, 不动算法)
        ├─ assess_gold_status             (复用: 显式人工 gold, 原阈值原语义)
        └─ assess_behavioral_outcome      (★新: outcomes.jsonl → resolved_rate)
             └─ 行为一致性门 behavior_sim  (★新: 工具序列 bigram-Jaccard 均值)
                  └─ source="miss_workflow" 候选 ──→ ClusterCandidateStore (30d TTL/50 cap 复用)

[呈现/提升]
   ├─ dashboard /api/discovery/*           (★新端点, 只读)
   ├─ vibe skill candidates                (已有表格, 加 source/resolved% 列)
   └─ vibe skill promote <id> [--activate] (--activate = ★新状态机; 未审不注入保证不变)
```

关键不变量：
- **热路径零新增 I/O**：miss 判定、pending 入队、span 写入全部保持现状；所有新逻辑都在装配与批量扫描两个离线相位。
- **未审不注入**：`promote` 仍只写草稿目录（`skill_commands.py:1695` 注释所述 W4 P0 保证），`--activate` 是显式第二步。
- **隐私基线不后退**：tool_call span 只携带工具名与序号，永不携带 `tool_input`（沿用 `record_tool_event` 的最小化原则，tool_sequences.py:4-11）。

## 2. 行为采集方案（问题 1 的回答）

### 2.1 生产方挂在哪里：装配桥，不改热路径

候选位置对比：

| 方案 | 评价 |
|---|---|
| agent_runtime 内嵌采集 | ❌ agent_runtime 只在 UserPromptSubmit 时被调用，看不到后续工具调用；跨进程 contextvars 也传不过去 |
| CLI 包装 agent 进程 | ❌ 侵入用户既有工作流，且各平台启动方式不同 |
| **平台 hook（PostToolUse）→ 既有 record-tool → 装配桥折算 span** | ✅ 唯一与现状兼容的方案：claude-code 通道已上线（`adapters/claude_code.py:393`），hook 契约"必须 exit 0、必须快"已被 `sequence_cmd.py:57` 遵守 |

具体桥接：扩展 `assemble_tool_sequences`（tool_sequences.py:113）或新增兄弟函数 `bridge_tool_spans()`：

1. 按 cursor 水位读 `tool_sequences.jsonl` 新条目（水位机制已有，`_read_cursor`）。
2. 读 `spans.jsonl` 尾部（`SpanWriter.query_recent`，复用），建立 `session_id → [route spans]` 索引。
3. **Join 规则**：工具事件的 `session` 匹配 route span 的 `session_id`，且事件 `ts ∈ [route.started_at, route.started_at + N 分钟]`（N 为 knob，默认 60）。匹配失败的事件不折算（宁缺毋滥，错挂比漏挂危害大）。
4. 折算为 `tool_call` span 写入 spans.jsonl：`trace_id`/`parent_span_id` 取自 route span，`task_id` 继承（聚类硬键自动对齐）。
5. 触发时机：与现有 `assemble_tool_sequences` 相同（`vibe sequence assemble` + `vibe route` 懒触发），不写守护进程。

性能：hook 侧不变（一行 JSON append）；装配侧是批量操作，且受 cursor 水位限制只处理增量。spans.jsonl 写入走 `SpanWriter` 既有 fcntl 锁。

### 2.2 平台差异

- **claude-code**：通道已存在，零新增。
- **kimi-cli**：`adapters/kimi_cli.py:76/178` 有 `[[hooks]]` TOML 注入机制，但是否有 PostToolUse 等价事件需按 Kimi hooks 文档核实（当前只注入了 UserPromptSubmit 路由 hook）。若有：同一 `record-tool` CLI 契约；若无：该平台无行为数据，退化为纯 query 聚类（功能可用，行为门跳过）。
- **pi**：TypeScript extension 机制（`pi_coding_agent.py:445 install_hooks`），extension 内调 `vibe sequence record-tool`。
- 统一抽象：采集契约就是 stdin JSON `{tool_name, session_id}`（已是 `record_tool_event` 的输入形状），平台 shim 只负责事件→契约的翻译。**schema 不因平台分叉**；span `metadata.platform` 记录来源供分析。

### 2.3 tool_call span schema 草案

完全复用 `models.py:27` 的 `Span` dataclass，不新增字段，只约定取值：

```
name:        "tool:<ToolName>"            # 与 _extract_step_names (skill_promote.py:599) 的 name 源对齐
span_kind:   "tool_call"
trace_id:    <所属 route span 的 trace_id>
parent_span_id: <route span id>
task_id:     <继承 route span>             # 聚类硬键
session_id:  <hook payload 的 session_id>
project_id:  <继承>
status:      "ok"                          # PostToolUse 即已完成；无失败通道时不臆造
started_at/ended_at: ended_at = hook ts; started_at = ended_at - (与上一事件的间隔, 下界 0)
input_data:  None                          # 永不携带 tool_input（隐私红线）
output_data: None
metadata:    {"platform": "claude-code|kimi-cli|pi", "seq": <会话内序号>, "source": "hook-bridge"}
schema_version: CURRENT_SPAN_SCHEMA_VERSION (1)
```

`label_step_frequency`（skill_promote.py:617）从 `span["name"]` 提取步名，因此 `tool:Edit` 这类命名直接喂给 core/common/optional 打标，草稿 SKILL.md 的 core steps 自动获得真实工具序列。

## 3. 结局信号（问题 2 的回答）

| 信号源 | 可靠性 | 成本 | 判定 |
|---|---|---|---|
| 显式 accept（`vibe instinct accept` / pending accept） | 高 | 已有 | **strong positive**，等同现有 gold |
| **重问检测**：同 query_hash 在 24h 窗内再次出现于 MissCounter/pending（用户没得到答案才会重问） | 中高（负向） | 低（两个已有存储各读一次） | **strong negative** → outcome=unresolved |
| **会话完成+无重问**：session 有 ≥3 步工具调用且 24h 内无同 hash 重问 | 中（"用户没抱怨"≠"解决了"） | 低 | **weak positive** → outcome=resolved_weak |
| 后续 turn 情感/语义分析 | 中 | 高（LLM 调用+隐私） | ❌ 本期不做 |
| 会话正常退出（SessionEnd hook） | 低（用户随时关窗） | 低 | 不单独使用，仅作会话边界辅助 |

**选择**：三级结局模型 `outcome ∈ {resolved_strong, resolved_weak, unresolved, unknown}`，写入 `.vibe/observability/outcomes.jsonl`（追加式、按 task_id+session_id 去重的最新值生效，文件级 knob 控制保留条数，默认 5000）。

**gate 语义**：miss 簇的 `resolved_rate = (resolved_strong + resolved_weak) / (非 unknown 成员数)`。`resolved_weak` 在 UI 和草稿中显式标注"弱结局信号"，人审时可见——自动信号只负责"把候选送上桌面"，不代替人审。unknown 成员不进分母（避免冷启动期数据稀疏把 resolved_rate 压成 0）。

实现位置：新模块 `core/observability/outcome_detection.py`，函数签名对齐 `gold_detection.assess_gold_status`（in-place enrich `list[Cluster]`），由 `scan_candidates` 在第 3 步后调用。

## 4. 聚类与行为相似度（问题 3 的回答）

### 4.1 语义聚类：复用，不新建

`cluster_queries`（clustering.py:175）对 miss 场景直接成立：miss query 有 `route:` span → 有 task_id → 参与硬分组+软合并。MissCounter（无原文）和 missed_query_tracker（token Jaccard，自认 CJK 差）都不进发现主链，见 §6。

### 4.2 行为相似度：bigram-Jaccard 混合分

"处理方式类似"= 工具序列相似。对每个 session 的 tool_call span 序列 `T = [t1..tn]`：

```
behavior_sim(A, B) = 0.5 · Jaccard(bigrams(A), bigrams(B))     # 局部顺序
                   + 0.5 · Jaccard(set(A), set(B))             # 步骤集合覆盖
```

- **为什么 bigram-Jaccard 而非编辑距离**：编辑距离 O(n·m) 且对并行/交错调用（子 agent 并发工具调用真实存在）过度敏感；bigram 保留局部顺序信息（`Read→Edit` ≠ `Edit→Read`）又对插入噪声鲁棒，计算是集合操作。
- **为什么混合集合 Jaccard**：纯 bigram 对短序列（3-4 步，恰是本特性下限）方差大；集合项保底"用了同一组工具"。
- **簇级一致性**：`consistency(C) = mean_{pairs} behavior_sim`，要求 ≥ `behavior_sim_threshold`（默认 0.5）。
- **阈值标定思路**（沿用 `scripts/calibrate_index_threshold.py` 的 M11 惯例）：(a) 从既有 dogfood 会话抽人工标注的"同流程/不同流程"对 30-50 组；(b) 扫描阈值 0.3→0.8，取 purity（簇内人工判同率）argmax 且合并率不塌缩的点；(c) 无标注数据前用默认值 0.5 并在 ScanSummary 中输出分布分位数供首轮标定。
- **注意**：行为门是**聚类后**的第二道闸（与 `label_step_frequency` 同一相位），不改 Union-Find 的合并判据——避免单链接链式污染。

无行为数据的簇（kimi/pi 无 hook 时）：行为门跳过，仅靠 query 聚类 + resolved_rate，候选标 `behavior_evidence: "unavailable"`，人审时降权显示。

## 5. promote --activate 状态机与冲突回滚（问题 5 的另一半）

现状：`CandidateStatus = Literal["pending","promoted","dismissed"]`（skill_promote.py:73），promote 止步于草稿+手动 copy 提示（skill_commands.py:1710）。

扩展状态机：

```
pending ──promote──▶ promoted(草稿已写) ──activate──▶ activated
   │                     │                              │
   └──dismiss──▶ dismissed (sticky, 终态)   deactivate──┘ (回到 promoted)
```

- `vibe skill promote <id> --activate`：草稿物化（现有 `materialize_candidate`）→ **冲突检查**（目标 `skills/<skill_id>/` 已存在且内容 hash 与草稿不同 → 拒绝，提示 `--force` 或改名）→ copy 到 `.vibe/skills/`（project）或 `~/.vibe/skills/`（global）→ 内部走 `vibe skill add` 的注册路径 → 状态翻 `activated`。
- **回滚**：`vibe skill deactivate <id>` —— 仅当目标目录内容与草稿 hash 一致（用户未手改）才删除目录并翻回 `promoted`；用户改过的技能不删，只解除注册并告警。这就是"hash 守卫回滚"。
- **全局命名冲突**：promote 派生的 skill_id 已含 cluster hash 后缀（`custom/<slug>-<cluster8>`，skill_commands.py:1693），天然低碰撞；冲突检查兜底。不引入 `vibe-auto-` 前缀——保持命名可读，冲突交给检查。
- **兼容性**：新增 `activated` 状态值。旧二进制读含 `activated` 行的文件时按 `_parse_lines` 的"坏行跳过"策略处理——会丢该行但不崩；文档注明（schema_version 不动，因为 Span 无关；候选池行无版本字段，接受此降级）。

## 6. 三条管道收敛（问题 4 的回答）

分工终态：

| 管道 | 终态职责 | 改动 |
|---|---|---|
| MissCounter | 隐私计数器（miss 频率的 hash 证据） | **不动** |
| RoutingPendingStore | 人审队列（低置信/纠错，每天 ≤3 条） | **不动**；accept 时额外写 `outcomes.jsonl` strong positive（一行改动，在 accept 调用方） |
| missed_query_tracker | live 路径的**即时提示**保留（`cli/main.py:913` 的用户可见提示不动）；analytics Jaccard 聚类路径**废弃**，改为读 `ClusterCandidateStore` 的投影 | 中等：删 `clusters_from_analytics`，`suggest_for_live_query` 的阈值判断改查候选池 |
| ClusterCandidateStore | **唯一发现出口** | 加 `source` 字段（`"gold_span"` / `"miss_workflow"`）+ `resolved_rate`/`behavior_consistency` 字段 |

`scan_candidates` 准入改造（skill_promote.py:776 的分类段）：

```
if cluster 有人工 gold 信号:   走现有 gold_rate 门（source="gold_span"，行为完全不变）
elif cluster 成员是 miss 路由:  走新门 span_count≥3 AND resolved_rate≥0.6 AND behavior 门（source="miss_workflow"）
```

这样既修掉了探索发现的结构断点（"纯 miss 簇永远成不了候选"），又不稀释现有 gold 候选的语义。

**迁移路径**：
1. M1 落地桥与结局信号后，新数据自然流入；旧 spans.jsonl 无 tool_call span，旧 miss 簇走 `behavior_evidence: unavailable` 降级路径，无需回填迁移。
2. `clusters_from_analytics` 标 deprecated，一个版本后删除；`SkillSuggestionCollector.add_missed_query` 的调用方（cli/main.py:280）改为读候选池，collector 本身保留给 sequence-pattern 建议（它本来就只消费工具序列模式，docs/decisions/_review-sprint1-evolution-pi.md:96 明确过两者不该混）。

## 7. Dashboard 端点契约（问题 5 的前半）

全部只读，复用 `server.py:46` 的 `_read_jsonl` 环形缓冲模式（不引重依赖——server.py 头部注释明确此约束）：

| 端点 | 数据源 | 参数 | 说明 |
|---|---|---|---|
| `GET /api/discovery/candidates` | `.vibe/observability/cluster_candidates.jsonl`（+ 全局 `~/.vibe/...` 合并） | `status`, `source`, `include_unstable`, `limit`(默认50) | 列表。文件本身 ≤50 pending + 终态行，天然有界；limit 防御终态行累积 |
| `GET /api/discovery/candidates/{cluster_id}` | 同上 + spans.jsonl | — | 详情：queries、core_steps、resolved_rate、behavior_consistency、project_distribution |
| `GET /api/discovery/misses` | `miss_counter.json` + `routing_pending.jsonl` stats() | — | miss 概览：top hash 计数（无原文）、pending 队列统计 |
| `GET /api/discovery/sessions/{session_id}` | spans.jsonl 过滤 session_id | — | 行为轨迹：该会话 tool_call span 序列，供人审"处理方式" |

性能：候选池文件有界（MAX_PENDING=50 + TTL），miss_counter 是单 JSON，均 O（小）；`sessions/{id}` 走 `query_recent(limit=500)` 尾部窗口过滤，与现有 `/api/spans` 同成本。变更类操作（promote/dismiss/activate）**不进 dashboard**，保持 CLI 唯一入口，人审闸门的语义不被 UI 绕过。index.html 加一个 "Discovery" tab（探索确认当前 grep 零命中，是纯增量）。

## 8. 降级与规模控制（问题 6）

**规模控制**：
- `tool_sequences.jsonl`：已有 10MB 单轮转上限（tool_sequences.py:49），不动。
- `spans.jsonl`：当前无界。**复用同一轮转模式**：新增 `observability.spans_max_bytes`（默认 50MB），超限 rename 为 `spans.0.jsonl`，`query_recent` 读两个文件（装配桥与 scan 同步适配）。这是机制而非 knob-heavy 方案——与 tool_sequences 完全同构。
- 候选池：30 天 TTL + MAX_PENDING=50 + admit-only-if-better 驱逐，全部已有，直接覆盖新 source 的候选。
- `outcomes.jsonl`：条数 cap（默认 5000，超出按 oldest-first 裁剪）。
- 聚类 O(n²)：`scan-candidates --limit/--days` 已有（skill_commands.py:1274）；文档建议 cron 用 `--days 30`。

**embedding 不可用**（无 fastembed / `python -O` 环境）：
- `EmbeddingCache.embed` 返回 None（embedding.py:128-137 已处理）→ 软合并跳过 → 只剩 `(project_id, task_id)` 硬分组 = 相同归一化 query 才成簇。功能降级为"高频重复 miss 发现"，不崩。
- **行为门不依赖 embedding**（工具名集合运算），在降级模式下反而成为主力过滤器——这是本设计的刻意安排。
- resolved_rate 检测零依赖。

**候选池污染防护**（在既有三层之上叠加）：
1. 新 source 候选同样受 MAX_PENDING 驱逐（gold_rate 槽位用 resolved_rate × behavior_consistency 的乘积代替，保持单调语义）。
2. `is_low_information_query` 前置拦截已有（routing_pending.py:96），miss 簇的 query 成员全部过了这道闸才进过 pending/analytics——天然过滤垃圾。
3. unresolved 占多数的簇（resolved_rate < 0.3）归入既有 unstable 桶，不进人审列表。
4. 一键熔断：`vibe data purge --tool-sequences` 已有；新增 `--discovery` 清 outcomes + 候选池。

## 9. 机制 vs 配置 knob 汇总

沿用 `skill_promote.py` 惯例：**模块常量 + docstring 写明选取理由 + CLI flag 覆盖**（该文件未走 RoutingConfig，因其属 observability 域；若未来要入 config，放新 `DiscoveryConfig` 段而非塞进 RoutingConfig）。

| 项 | 类型 | 默认 | 标定思路 |
|---|---|---|---|
| join 时间窗 | knob | 60 min | 对照会话实际时长分布 p90 |
| min_tool_steps | 机制复用 | 3 | 复用 `tool_sequences.MIN_STEPS` |
| unresolved 重问窗 | knob | 24h | 对齐 pending 的 dismiss 抑制窗（24h），同量级 |
| resolved_rate 阈值 | knob | 0.60 | 对齐 `DEFAULT_MIN_GOLD_RATE=0.60` 的既有人审语义 |
| behavior_sim 阈值 | knob | 0.5 | §4.2 人工标注对标，M11 calibrate 脚本模式 |
| 行为门权重 0.5/0.5 | knob | — | 标定时随阈值一起扫 |
| spans_max_bytes | knob | 50MB | 按 query_recent(500) 能覆盖 30 天估算 |
| outcomes cap | knob | 5000 | 内存/读延迟实测 |
| 未审不注入、tool_input 红线、exit-0 hook 契约 | **机制** | — | 不可配置 |

## 10. 里程碑拆分

- **M1｜行为桥**（核心增量）：`bridge_tool_spans` + outcome 检测（重问/弱结局）+ spans 轮转 + kimi/pi shim 可行性验证。验收：一次真实 miss 会话后 spans.jsonl 出现正确挂载的 tool_call span；`vibe data purge` 可清。
- **M2｜发现准入**：`assess_behavioral_outcome` + `scan_candidates` source 分支 + 候选池字段扩展 + CLI candidates 新列。验收：纯 miss 簇能产生 pending 候选（此前结构上不可能）。
- **M3｜行为一致性门**：behavior_sim + 标定脚本 + `behavior_evidence` 降级标注。验收：标定报告，阈值有依据。
- **M4｜管道收敛**：missed_query_tracker 投影化、pending accept 写 outcome、弃用 Jaccard 路径。可与 M3 并行。
- **M5｜看板**：4 个端点 + Discovery tab。可与 M3/M4 并行（契约先行）。
- **M6｜提升闭环**：`--activate` 状态机 + hash 守卫回滚 + deactivate。依赖 M2 的字段。

M1-M2 是"能跑通的最小发现闭环"（端到端 demoable），M3 决定候选质量，M4-M6 是工程化收尾。建议按此序串行 M1→M2→M3，M4/M5/M6 视人力并行。

## 11. 风险清单

| # | 风险 | 等级 | 缓解 |
|---|---|---|---|
| R1 | **kimi/pi 无 PostToolUse 等价事件** → 行为数据只覆盖 claude-code，特性在主力平台瘸腿 | **高** | M1 第一步做可行性验证（kimi hooks 文档核对 + pi extension spike）；不行则该两平台走 `behavior_evidence: unavailable` 降级，结论透明化 |
| R2 | session join 错挂（hook session_id 与 route span session_id 不一致——CLI 路径每次 mint 新 UUID，agent_runtime 用平台 session） | 高 | join 要求 session_id 相等 + 时间窗双重条件，宁缺毋滥；M1 用真实日志回归验证 join 命中率，命中率 <50% 则回头修 session 传递 |
| R3 | 弱结局假阳（用户放弃 ≠ 解决）→ 污染 resolved_rate | 中 | weak 信号全程标注；resolved_rate 门 0.60 + 行为门 + 人审三道防线；unstable 桶兜底 |
| R4 | spans.jsonl 轮转引入消费者回归（aggregator/dag_rebuilder/recall 只读单文件） | 中 | 轮转与 `query_recent` 改造同 PR 落地，三个消费者逐一回归；先双读再轮转 |
| R5 | 新 `activated` 状态 + `source` 字段的旧二进制兼容 | 低 | `_parse_lines` 坏行跳过策略已有，文档注明降级行为 |
| R6 | 候选池被 miss_workflow 源挤占（每天 miss 远多于 gold） | 中 | admit-only-if-better 驱逐对新源生效；source 分布纳入 ScanSummary 输出供观测 |
| R7 | 隐私面扩大（工具名+会话关联） | 低 | 工具名最小化已有先例；purge 路径齐全；跨项目候选沿用 W5.2 既有警告机制 |
