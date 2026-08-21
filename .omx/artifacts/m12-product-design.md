# M12 产品设计：对话中语义洞察 → 技能发现（v3，终稿）

> 状态：gate15/15b/15c 三轮双路评审通过。v1 被 claude BLOCK（两处实测证伪，
> 均已复现确认），v2 被 claude BLOCK（准入闸门假蕴含，pi 同抓）。本版吸收
> 全部裁定与发现。事实基础：m12-exploration.md；对抗设计：
> m12-design-a.md / m12-design-b.md；评审：gate15{,b,c}-{claude,pi}.md。

## 一句话

把「多次语义相似的路由 miss + agent 处理方式一致」自动汇聚成「发现（Discovery）」，
在看板和 CLI 中以证据卡片呈现，用户提升为项目/全局技能——全程本地、人审闸门
不可绕过、证据不足时诚实标注而不是编造。

## gate15 裁定修正（v1 的两处实测证伪）

1. **聚类复用前提不成立（BLOCK-1，claude 实测，orchestrator 复现确认）**：
   `_extract_query`（clustering.py:342-367）只读 `input_data`，而 route span 生产方
   （agent_runtime.py:452 / cli/main.py:755）只把 query 放进 metadata/span name。
   本仓库实测：169 spans / 75 route spans / **0 个可提取 query / 0 簇**，
   `cluster_candidates.jsonl` 从未在本项目产生过。修复（`_extract_query` 加
   metadata 回退，声明兼容策略）进入 **M0**。
2. **claude-code 捕获通道运行零产出（BLOCK-2，claude 实测，orchestrator
   复现确认）**：hook 代码已装但本 dogfood 仓库 `.vibe/tool_sequences.jsonl`
   不存在——模板 `>/dev/null 2>&1 || true` 静默吞掉所有失败。M1 出口标准
   必须含「dogfood 真实产出 + 捕获活性信号」。
3. **gold 门表述修正**：纯 miss 簇不是「成不了候选」，而是落入 unstable 桶、
   进不了**人审可见、可提升**的 stable 候选（skill_promote.py:334-348）。
4. **join 键裁决（pi vs claude 分歧，实测采 claude）**：agent 路径的 route span
   携带真实平台 session UUID，claude-code 路径 join 成立；CLI 路径
   （main.py:745 每次 mint 新 UUID）不参与 join。M1 仍需把 session_id 前向
   传入 route hook 模板（当前未传），或回退「时间窗 join + 歧义拒挂」。

## 目标数据流（修订版）

```
M0 前置修复（新设里程碑）
  _extract_query metadata 回退 + 真实 span smoke：对本项目 spans.jsonl
  跑 scan，簇数 > 0 且含 miss 簇（出口标准）。
  miss 分类规则（显式声明）：miss = has_match=False；mode="not_intercepted"
  的 span（拦截器主动放弃、无 has_match 键，实测占 19/75，多为「继续」类
  延续指令）显式排除——注意这使真实 miss 池缩小到个位数，M0 smoke 用
  宽松阈值跑通提取链，准入门用标定阈值；若真实数据不足以成簇，
  回退为「采集至 N 条真实 miss 再做 smoke」或合成注入作为次级证据。

对话中（零打扰静默观测）
  route miss ──► route span（metadata 已有 has_match/skill_id/confidence，
                 has_match 明确排除 fallback_llm —— miss 判定直接用 spans，
                 不需 join MissCounter）
  agent 工具调用 ──► tool_sequences.jsonl（claude PostToolUse 已有代码，
                 M1 修复其静默死亡：失败不再吞、记录 last-capture 时间戳）
       │
  M1 装配桥 + 结局信号：session_id（经 route hook 前向修复）+ 时间窗
       join → tool_call span 写 spans.jsonl（消费者 dag_rebuilder /
       get_pattern_sequences 真实存在；aggregator 的 per-skill 视图不覆盖
       route-only trace，属已知边界不阻塞）。结局信号：重问（按 span 内
       task_id 复现判定，不用 query_hash——query 截断 200 字符会失配）≈
       弱负 / 会话完成无重问 ≈ 弱正 / 显式 accept ≈ 强正。
       cursor 争用：单读者扇出到双消费者（InstinctLearner + 桥），
       不各立 cursor（rotation 只重置主 cursor，多 cursor 语义未定义）。
       │
  M2 miss 簇准入 + 统一 Discovery CLI：embedding Union-Find（复用
       clustering.py，余弦阈值经 calibrate 脚本标定，起点 0.82 待标定）；
       准入 = distinct (task_key, 自然日) 对 ≥3 且 跨 ≥2 个不同自然日
       （合取）；miss 簇以 miss_recurrence 准入（不再要求 gold_rate）
       │
  M3 行为一致性门：工具序列 bigram-Jaccard ≥ 阈值（标定后进配置）→
       behavior_evidence: consistent / divergent / unavailable（三态；
       gate24 修订——原文两态无法诚实归入"有数据但低于阈值"的情形，
       divergent 为新增第三态；字段缺失 = 未采集，诚实降级标注）
       │
  M4 看板发现页（/api/discoveries，只读）——变更操作（promote/dismiss/
       mute）只在 CLI，看板不写（pi 裁决：保人审闸门单入口）
       │
  M5 promote --activate：写草稿 + 注册，但必须满足「草稿自生成以来被
       实质编辑过」或显式 --force（消解 v1 中 --activate 与「无人工确认
       不激活」的自相矛盾；编辑检测用内容 hash：生成时记录草稿 hash，
       注册前比对当前文件 hash，不同才放行——mtime 检查会被空白编辑
       骗过，不用）。全局提升：需 [XP] 跨项目证据 或 --force，
       显式隐私确认（默认 N），全局草稿剔除示例 query。
```

## 阈值哲学（修订）

- 准入（合取，gate15b 修订）：distinct (task_key, 自然日) 对 ≥ 3 **且**
  覆盖 ≥2 个不同自然日——两个条件缺一不可：pair 计数防同句同日刷量，
  跨日条件防「一下午迭代式改写」式同日多 key 爆发（v2 曾误称跨日
  被 pair 计数蕴含，数学上为假，gate15b 双路独立抓出）。验收手段：
  同日/跨日 synthetic injection tests 进 M2。
- task_key 统一复用 span 上已有的全文派生 task_id（与重问检测同一
  派生，避免截断 200 字符前缀碰撞）；标定语料基于管道实际看到的
  截断文本。
- has_match 缺失的 span（CLI 路径、错误路径、pre-W5.0 老 span）视为
  unknown，**不进 miss 池**（保守方向）。
- query 余弦：起点 0.82，**必须用 M11 的 calibrate 脚本纪律标定**
  （0.80 是为 gold 簇近邻标定的，miss-vs-miss 是另一个分布；
  用 30-50 组人工标注的 dogfood miss 对标定）
- 行为一致性 bigram-Jaccard ≥ 0.5（标定后固化）
- knob 归属：**不进 RoutingConfig**——observability 域，模块常量 + CLI flag，
  未来收 DiscoveryConfig（采 B §9，沿用 skill_promote.py 惯例）
- M11 交互承认：M11 收紧弃权后 miss 池变大（含金量 arguable 变高——以前
  被弱匹配吸收的查询现在如实暴露）；dismiss 率 >50% 熔断明确绑定到
  「M11 后 miss 池构成变化」的观测；scan 成本随 distinct task_key 增长，
  用 --days/--limit + EmbeddingCache 缓解
- **14 天冷却没有新增成员自动降档**（从 A 捡回：不再提示、看板可见）

## 用户旅程（v1）

1. 对话中：零打扰，静默观测。
2. 候选成熟：session 结束等自然停顿点提示一次；同一候选不重复提示；
   14 天无新增自动降档冷却。
3. 查看：`vibe skill discover`（按 evidence_score 排序）或看板只读卡片：
   模式概括 + 证据强度（query 证据 / 行为证据 / [XP] 跨项目）+
   脱敏示例 query + 一致性摘要 + 捕获年龄（活性信号）。
4. 决策（全部在 CLI，看板只读）：promote（草稿→人工编辑→--activate
   注册）/ dismiss（粘性否定列表，反馈单向收紧阈值）/ --mute（临时
   静音，区别于 dismiss）/ 忽略（TTL 过期）。
5. `vibe skill discover --history`：已闭环记录 + 发现精度指标
   promoted/(promoted+dismissed)，及「提升后技能被路由命中 ≥5 次」的
   闭环验证。

冷启动预期：单人用户下 ≥3 对 × 跨 2 日 + 余弦标定阈值的候选成熟以
「周」计；可用既有 spans.jsonl 回填种子（backfill）加速首批发现。

## 隐私边界（修订）

- 全部本地，无云端共享。
- 工具序列**只存工具名**（+ts+session）——v1 写「参数 key」是与实现
  不符的文字漂移，已删；不存任何参数值。
- query 脱敏沿用现有写入侧集中脱敏；span metadata 截断为 **200** 字符
  （v1 误写 500，已更正）；routing_pending 侧为 500。
- 全局提升：默认 N 显式确认；全局草稿不含示例 query 与项目标识。

## 规模与退化

- spans.jsonl 目前**无上限**——桥接后每工具调用一条 span，体量倍增。
  补 50MB 轮转（采 B §8；candidate 池 30 天 TTL 与 span 文件留存是两回事，
  v1 混淆已更正）。
- embedding 不可用：降级 token 级匹配 + behavior_evidence 标注，阈值上调。
- kimi/pi 是否有 PostToolUse 等价 hook 未定论（M1 spike 验证）；若无可
  用 hook：该平台 behavior_evidence=unavailable，query 侧阈值上调，
  卡片诚实标注。

## v1 范围切割

做：M0 提取修复、行为装配桥 + 结局信号、miss 簇准入、行为一致性门、
统一 Discovery CLI + 看板只读页、dismiss/mute、promote --activate
（编辑守卫）、全局隐私护栏、发现精度指标。
不做：自动生成 SKILL.md 正文、无人工确认的激活、对话中实时打断、
kimi/pi 行为采集强行适配、看板写操作、任何云端共享。

## 里程碑（修订）

- **M0 前置修复**：_extract_query metadata 回退（声明兼容策略）+
  真实 span smoke。出口：本项目 spans.jsonl 上 scan 产出含 miss 簇的
  簇数 > 0；若真实 miss 数据不足以成簇（当前池仅 ~6 条），按数据流
  节的回退链执行（采集至 N 条真实 miss / 合成注入次级证据）后重验。
- **M1 行为桥 + 结局信号**：route hook session_id 前向修复；claude-code
  捕获通道活性修复（失败不吞 + last-capture 时间戳）；kimi/pi hook
  可行性 spike（结论未定，spike 先行，不在文档预断）。出口：dogfood 中
  tool_sequences 真实产出，且 ≥20 条桥接 tool_call span 分布于 ≥3 个
  不同 session、last-capture 在 7 天内（「命中率>0」的薄门槛不足以
  支撑 M3 行为门）。
- **M2 miss 簇准入 + 统一 Discovery CLI**（M0+M1+M2 = 最小可 demo 闭环；
  含阈值标定；含同日/跨日 synthetic injection tests 作为准入门验收）。
  出口：真实数据准入的候选 ≥1 条出现在 `vibe skill discover`，
  证据卡片完整（防止「准入了但队列仍为空」的第三种静默空转）。
  **出口状态（gate17 记录）：延期**——当前真实 miss 池仅 6 distinct key
  （低信息量过滤后 4）,0 准入，闭环无法端到端演示；按设计回退链执行
  「采集至 N 条真实 miss 再验」（触发条件：miss 池 ≥30 distinct key 时
  重跑标定与出口验证）。实现与验收手段（合成注入测试、
  miss_pool_size/miss_admitted_count 操作员可见、embedding 降级显式
  标注）均已落地，延期仅是数据积累问题。
  **出口状态（2026-08-21 更新）：通过**——cmspark 真实数据（309
  distinct miss query，一个月）重验：标定区间不变（0.70 维持）,5 条
  miss_recurrence 候选准入且卡片完整，5/5 人工认可为真实工作流。
  过程中暴露并修复两个真实缺陷（unstable 行占满池容量堵死准入 →
  类分离预算；content-block 信封未拆 → `_extract_query` 扩展，均经
  gate21 双路复审）。全程记录:`.omx/artifacts/m12-m2-exit-verification.md`。
- **M3 行为一致性门**（依赖 M1）。
- **M4 看板发现页（只读）**（依赖 M2，可与 M3 并行）；ScanSummary 加
  各层 miss 份额分布（上线前后对比，供 dismiss 熔断观测）。
- **M5 promote --activate + 编辑守卫（内容 hash）+ --history 精度指标**
  （依赖 M2）。

## 风险清单（修订）

> **M2 前置注意（gate16 双路复审实测确认）**：fastembed 0.8.0 不支持
> embedding.py 的默认模型名 `paraphrase-multilingual-MiniLM-L12-v2`（缺
> `sentence-transformers/` 前缀，命名空间版受支持）→ `_compute` 恒返回
> None → 聚类 soft-merge 余弦合并**从未触发**，现有簇全是 hard task_id
> 分组。M2 的余弦标定前必须先修这一行，并加「embed() is not None」
> smoke（防再次静默归零）；降级不得只是 per-query warning，要在 scan
> 输出显式标注。一并进 M2 视野：`_extract_step_names` 只读 dict
> metadata（真实 span 是 JSON 字符串，step 标签只剩 span name）、
> min_cluster_size=3 对 6-key miss 池偏严、spans.jsonl 50MB 轮转未做
> （桥接后 span 增速倍增）、`vibe data purge` 域划分（outcomes/
> bridge-state 归 observability 域）。

1. **静默空转**（claude 指正：比误报疲劳更隐蔽的头号风险）→ M0/M1 的
   真实数据出口标准 + 捕获活性信号
2. 误报疲劳 → distinct-day 闸门 + 标定阈值 + dismiss 单向收紧 +
   只提示一次 + 14 天冷却
3. 平台覆盖不均 → 诚实降级标注
4. session join 错挂（CLI 路径）→ M1 前向修复或时间窗歧义拒挂
5. 候选池污染 → admit-only-if-better、TTL、否定列表
6. 隐私泄漏 → 双重确认 + 示例剔除 + 只存工具名
7. 遥测膨胀 → spans.jsonl 轮转 + TTL 惯例
8. 全局技能质量 → [XP] 跨项目证据要求（或 --force 显式绕过）
