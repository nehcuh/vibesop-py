# Skill 商店重构与智能建议反馈环 — 设计文档

> **日期**: 2026-07-18
> **状态**: ✅ 已实现（P0–P4 全部落地，逐阶段 Pi 复审 + Docker e2e，commit ae08592→322ea1a）
> **版本**: 8.2.0
> **作者**: Kimi（分析）+ Pi（评审）+ 用户（决策）

---

## 📋 背景与问题

### 用户提案（2026-07-18）

1. **Skill 商店重构**：废弃基于 GitHub Issues 的轻量市场，改为「用户需要时去 GitHub 搜索对应分类的 skill trend，询问安装，按需配置全局或项目级」
2. **未命中追踪**：后台记录重复的无匹配查询，定期询问是否去 GitHub 搜索该类技能
3. **任务蒸馏**：对重复任务定期梳理，询问是否总结对话/流程为独立技能（instinct learning 延伸）
4. **Langfuse**：是否需要集成以跟踪 agent 内部调用和对话历史

### 诊断出的真实问题（代码实测）

| 问题 | 证据 |
|---|---|
| 市场零触达：crawler 硬编码搜 `topic:vibesop-skill`，全 GitHub **0 个仓库**（公共生态 `topic:agent-skills` 有 10,426 个） | `src/vibesop/market/crawler.py:56`；gh api 实测 2026-07-18 |
| Issues 通道双实现冗余且零使用：`publisher.py`（label `skill-publish`）+ `community_cmd.py`（label `skill-share`），两个 label open issues 均为 0 | `publisher.py:18`、`community_cmd.py:50` |
| 单路由路径（`vibe route` 主流路径）**不写 analytics**：`_record_execution` 全 src 仅 `orchestrator.py:315` 一个调用点，且其签名耦合 `OrchestrationResult`（`result.mode.value`/`execution_plan.steps`），`RoutingResult` 无法直接复用 | `unified.py:810-849` |
| analytics 默认关闭（F-06 opt-in 先例）→ 补了写点也无数据，鸡生蛋死锁 | `unified.py:819-823` |
| `record_sequence` 零调用方；`SkillSuggestionCollector` 唯一入口 `add_from_pattern` 只消费工具调用序列 | `suggestion_collector.py:141` |
| 工具调用序列数据在宿主 agent（Claude Code/Kimi/Pi）侧，不在 vibe 进程内 | vibe 生命周期：query → skill_id → 退出 |
| trust store 残留：legacy 无哈希条目仍放行（`trust.py:54`）、新条目可无哈希写入（`trust.py:66-73`） | `core/skills/trust.py` |
| 现有「商店」实为三套重叠：market（crawler+publisher）+ community + featured_registry | `market_cmd.py`、`community_cmd.py`、`featured_registry.py` |

### 生态实测（2026-07-18，gh api）

- `filename:SKILL.md`：256,160 个文件；anthropics/skills 162k stars（17 个官方技能，活跃）
- 可用 topic：`agent-skills` 10,426 仓库、`claude-skills` 5,541、`claude-skill` 3,712、`claude-code-skills` 1,209、`skill-md` 907
- GitHub Code Search API 限额仅 10 req/min 且必须认证，结果不携带 stars —— **不走 code search 路径**；repository search（30 req/min、原生按 stars 排序）是正解
- awesome-list 生态：addyosmani/agent-skills 79k、ComposioHQ/awesome-claude-skills 68k 等 —— 免 API、已策展

---

## 🎯 目标与非目标

### 目标

1. 商店能搜到东西：从自指 topic 切换到公共生态，支持分类 trend（stars 排序）
2. 安装能选作用域：`--scope global|project`，项目级同样过完整安全链
3. 未命中数据闭环：单路由路径有遥测写点 + 常开 hash 计数器，不依赖 analytics opt-in
4. 建议统一出口：`SkillSuggestionCollector` 作为唯一收件箱，非阻塞、有频率预算、可 dismissal
5. 蒸馏最小闭环：编排 plan 序列 + hooks 工具序列 → record_sequence → LLM 蒸馏 → 用户审定

### 非目标（Won't）

- ❌ Langfuse 进核心（留 panel 层，见 §7）
- ❌ 常驻后台守护进程（无载体；用 CLI 同步交互点 + loop tick）
- ❌ GitHub Code Search API 依赖（10 req/min 不可接受）
- ❌ 签名机制（社区生态无身份体系，featured_registry 策展+hash pin 是轻量等效）
- ❌ 对话原文采集与蒸馏（最大隐私面；做 query/序列级即可覆盖 80% 价值）
- ❌ 阻塞式弹窗（`vibe route` 的调用方常是另一个 AI agent，AGENTS.md 路由协议）

---

## 🏗️ 总体架构：技能发现反馈环

```
                 ┌────────────────────────────────────────────┐
                 │            SkillSuggestionCollector         │
                 │   （唯一建议收件箱：pending/created/dismissed）│
                 └───────▲───────────────────────▲────────────┘
                         │ add_missed_query      │ add_from_pattern（既有）
        ┌────────────────┴──────┐      ┌─────────┴──────────┐
        │ 未命中聚类（P2）        │      │ 序列检测（P3）        │
        │ no_match.jsonl +      │      │ 编排 plan 序列        │
        │ miss_counter（hash）   │      │ + hooks 工具序列      │
        └────────────────┬──────┘      └─────────┬──────────┘
                         │ 提示「要去搜吗？」        │ 提示「要蒸馏吗？」
                         ▼                       ▼
                 vibe market search         LLM 蒸馏 SKILL.md
                 （公共生态 topic+stars）      （全文审定 + 审计）
                         │                       │
                         └──────► 安装（--scope）◄─┘
                                    │
                          F-02 pack-lock + F-03 构建门
                          + pre-audit + 信任三级
                                    │
                          命中率回升（效果度量）
```

原则：先搜现成、再提议自造（装比造便宜）；同一时刻最多一个建议。

---

## 📦 P0 — 商店改造（3 人天）

> 裁决：不推倒重写（344 行 experimental 代码改造即可），废弃 Issues 双实现。

### 4.1 搜索目标切换

- `crawler.py` 的 topic 从 `vibesop-skill` 改为集合：`agent-skills`、`claude-skills`、`claude-skill`、`claude-code-skills`、`skill-md`，按 stars 降序（即用户说的「skill trend」）
- `vibe market search <query>` 保持；新增 `vibe market trending <category>`（分类 = topic/关键词映射）
- 查询结果按聚类缓存（TTL 建议 24h），避免烧 30 req/min 限额；引导用户配置 GitHub token（未认证 10 req/min）

### 4.2 awesome-list 免 API 通道

- 从 raw.githubusercontent 拉取 1-2 个万星 curated list（addyosmani/agent-skills 等），markdown 解析为目录条目
- 与 GitHub 搜索结果合并去重（按 repo canonical URL），策展条目优先展示
- Pi 的「LLM 初筛代替策展」降级为可选增强（后续迭代）

### 4.3 信任三级（MUST）

| 级别 | 来源 | 展示与行为 |
|---|---|---|
| 官方 | `TRUSTED_PACKS`（硬编码） | 现状不变 |
| 策展 | featured_registry / awesome-list | 排序第一信号（防 stars 刷量），标注「已策展」 |
| 未知 | 开放搜索结果 | 显著标注「未经验证的互联网来源」；安装前展示 SKILL.md 全文 + audit 结果 + repo 元数据（年龄/最近提交/stars），显式确认 |

- **前置修复（security blocker）**：`trust.py` —— 新条目强制内容哈希（无哈希写入改硬错误）；legacy 无哈希条目一次性迁移（对已安装包计算哈希回填）后删除无哈希 fallback（`trust.py:54,66-73`）
- 记录安装来源 URL，供撤销审计

### 4.4 `--scope global|project`

- `PackInstaller.install_pack(..., scope="global"|"project")`
- project：clone 到 `.vibe/skills/<pack>`，**走同一条 pre-audit + pack-lock + F-03 构建门**，跳过平台 symlink 与全局索引重建
- loader 已统一扫描项目级目录（`loader.py:88-93`、`parser.py:273-280` 按路径推断 source），无需改动发现层
- UX 默认建议：「搜来的装全局，自己长出来的留项目级」

### 4.5 废弃清单

- `src/vibesop/market/publisher.py`（Issues 注册表）
- `src/vibesop/cli/commands/community_cmd.py`（skill-share）
- `market_cmd.py` 中 publisher 分支 + 3 个对应测试文件
- 注意扫文档引用（`vibe skills share/discover` 有文档提及）

### 4.6 验收标准（DoD）

- `vibe market search "code review"` 返回 ≥5 个真实公共生态结果（非 0）
- `vibe market install <repo> --scope project` 后 `.vibe/skills/<pack>` 就位且路由可命中
- trust.py 无哈希路径全部关闭，测试覆盖
- ruff/basedpyright/bandit/全量测试绿

---

## 🧱 P1 — 数据地基（1 人天）

> 想法 2/3 共用。采纳 Pi 评审：写点不能复用 `_record_execution`（签名耦合 `OrchestrationResult`），需独立路径。

### 5.1 单路由遥测写点

- 新增 `_record_single_route_execution(query, result: RoutingResult)`：
  直接构造 `ExecutionRecord(mode="single", primary_skill=..., plan_steps=[], ...)` 调 `AnalyticsStore.record()`，不经过 `_record_execution`（避免类型适配）
- 调用点：`UnifiedRouter._single_skill_route` 返回前（含 no-match/fallback 分支——未命中恰恰是主要采集对象）
- 服从 `analytics.enabled` opt-in（F-06 不变）

### 5.2 hash-only 常开计数器（破 opt-in 死锁）

- 新增 `.vibe/miss_counter.jsonl`：**盐化哈希(query) + 计数 + 首末次时间戳**，不存原文 → 无需 opt-in（不可逆转，非个人数据）
- 仅在 no-match/fallback 分支写入；写入前仍过 `redact_sensitive` 再哈希（防哈希被字典攻击反推含密钥的 query）
- 当某哈希计数 ≥3 且文本采集已 opt-in 时，可关联展示代表 query；否则提示语只说「你有 N 次未命中查询」

### 5.3 数据契约

```json
// .vibe/miss_counter.jsonl（常开，无原文）
{"h": "sha256(salt+redacted_query)[:16]", "n": 3, "first": "...", "last": "..."}

// .vibe/analytics.jsonl（opt-in，既有 ExecutionRecord，新增 mode="single" 记录）
{"query": "redacted text", "mode": "single", "primary_skill": null, ...}
```

### 5.4 验收标准

- 单路由命中与未命中均在 analytics（opt-in 时）落 `mode="single"` 记录
- 未命中时 miss_counter 无条件 +1（无原文）
- 新数据类纳入 `vibe data purge`（`data_cmd.py` 分类清除框架）

---

## 🔍 P2 — 未命中闭环（1.5 人天）

### 6.1 聚类

- 输入：analytics.jsonl 中 `primary_skill=null` 的 opt-in 记录 + miss_counter 计数
- 英文：复用 `matching/tokenizers.tokenize` + Jaccard 相似度；CJK：走 embedding 分支（`learner.py:358-394` 已有可选 sentence-transformers 路径，opt-in）
- 输出：聚类（代表 query、次数、时间范围），阈值：同类 ≥3 次未命中

### 6.2 collector 新入口

```python
# SkillSuggestionCollector 扩展（唯一建议收件箱地位不变）
def add_missed_query(
    self, cluster: MissedQueryCluster, *,
    suggested_command: str,  # e.g. 'vibe market search "code review"'
) -> Suggestion  # type="market-search"，复用 pending/created/dismissed 状态机
```

- 阈值语义与序列 pattern 不同（次数+时间窗），独立配置
- `vibe skills suggestions` 天然成为统一查看入口

### 6.3 提示形态（UX 铁律见 §8）

1. no-match 面板追加一行机器可读建议：`Search GitHub: vibe market search "<推断分类>"`（零交互、agent 可消费）
2. TTY + 人类在场 + 频率预算允许时：一行 teaser「这类查询已出现 N 次，要去 GitHub 搜吗？」→ questionary 确认 → 直接调搜索
3. 绝不在任务中途打断；绝不在非 TTY/agent 调用路径输出交互

### 6.4 验收标准

- 同一聚类 3 次未命中后，`vibe skills suggestions` 出现 `market-search` 建议
- dismissal 后同聚类**永久**不再提示（除非 `vibe skills suggestions` 中手动恢复——「不再提示」对用户的含义就是永久，VS Code "Don't Show Again" 同构）；全局开关可关闭全部建议

---

## 🧪 P3/P4 — 任务蒸馏（1.5 + 1.5 人天）

> Pi 挑战「数据回流是架构级难题」成立，但答案在生态内：三条数据源路径按成本排序。

### 7.1 数据源（P3）

| 路径 | 成本 | 粒度 | 阶段 |
|---|---|---|---|
| ① 编排 plan 序列 | 进程内现成（`ExecutionPlan.steps` 的 skill_id 序列） | 技能级 | **P3 先做** |
| ② hooks 扩展采集 | vibesop 已有 HookInstaller/post-tool-use 体系，扩展为回写 `.vibe/sequences.jsonl` | 工具级 | P3 并行（被忽略的第三条路，无需宿主回调协议） |
| ③ 宿主 transcript 解析 | 每种 agent 格式适配（`~/.claude/projects/*.jsonl` 等） | 工具级+对话 | 后期；panel 侧更合适 |

- 接线：编排完成处与 hook 采集处调 `record_sequence(steps, success, context)`（形参已就位，零调用方）
- 隐式正反馈降权：只计 application 不计 success（防 Wilson 置信度污染，`learner.py:43-45` 的 `is_reliable` 门槛保持纯净）

### 7.2 蒸馏生成（P4）

- 触发：`SequencePattern` 达标（≥5 次、成功率≥0.8、≥3 步，`learner.py:113-115`）或 instinct `is_reliable` → collector `add_from_pattern`（既有通路）
- 生成：LLM provider（`llm/factory.create_provider`，`pack_installer.py:752-755` 已有先例）把序列 + 代表 query 总结为 SKILL.md，复用 `instinct evolve` 模板（`instinct_cmd.py:325-408`）；用户须知情内容将出网到 provider
- **审定 UX（MUST）**：全文渲染（Rich Panel，`skill_craft.py:113` 先例）→ 选择器「保存 / 编辑后保存 / 丢弃」（`main.py:928-951` 既有模式）→ 产物过 `SkillSecurityAuditor`（自生成内容可能固化机密）→ 默认写 `.vibe/skills/custom/`（项目级）
- 产物头部注明来源：「从 N 次会话蒸馏于 日期」
- 同一 pattern 去重，不问第二次；不自动发布到任何市场

### 7.3 验收标准

- 编排执行 ≥5 次同类序列后产生 suggestion
- 接受建议 → 生成的 SKILL.md 经审定后落 `.vibe/skills/custom/`，路由可命中
- 产物通过 auditor 扫描；`vibe data purge` 可清除相关数据

---

## 🔭 Langfuse 决议：不进核心

- 想法 2/3 所需数据（query、命中位、序列）本地 JSONL 全覆盖；Langfuse 装在 vibe 也采不到宿主 agent 侧数据
- 引入重依赖 + 网络上报违背 F-06/F-07 本地优先、redact-first 先例
- 重型追踪（span 树、token 归因、多 agent 编排调试）归 panel 仓库（已有 OTLP bridge + sqlite trace sink）
- 唯一承诺：核心日志保持 panel 可消费的结构化格式；未来若 panel 需要更强检索，由 panel 侧集成

---

## 🔒 安全与隐私需求清单

| 功能 | MUST | SHOULD | WON'T |
|---|---|---|---|
| 搜索安装 | 全量走 pre-audit→F-03→F-02 链；信任三级展示；未知来源全文+确认；修 trust.py 无哈希残留 | 策展结果置顶；低信号 repo 额外确认；记录来源 URL | 签名；免确认自动安装 |
| 未命中追踪 | hash 计数器不存原文；文本走 F-06 opt-in + F-07 redact；纳入 data purge；聚类全本地 | 最小化存储（计数+时间戳）；条数/保留期上限 | 未命中 query 上报远端 |
| 任务蒸馏 | 写入前全文审定；产物过 auditor；LLM 蒸馏须用户知情出网 | 默认项目级；来源标注 | 自动发布到市场 |

---

## 🧭 UX 铁律

1. **永不阻塞 agent 调用方**：所有交互式询问 TTY-gate；非 TTY/agent 路径零阻塞，输出含机器可读建议
2. **统一建议预算**：2/3 共用 collector 收件箱 + 频率三重上限（同聚类 ≥3 次才提示；距上次提示 ≥7 天；全局冷却 ≥1 天）；per-聚类 dismissal 持久化；全局开关第一天就位（VS Code `showRecommendationsOnlyOnDemand` 的教训）
3. **在相关行为当下触发**，不做日历驱动推送（IDE 推荐系统史 = 通知疲劳史）
4. **先搜现成、再提议自造**：同一时刻最多一个建议

---

## 📅 分阶段路线（约 8-9 人天）

| 阶段 | 内容 | 工时 | 依赖 |
|---|---|---|---|
| **P0** | 商店改造：换 topic + awesome-list 通道 + 废弃 Issues + `--scope project` + trust.py 修复 + 信任三级 | 3d | 无（独立价值，漏斗顶部） |
| **P1** | 数据地基：单路由写点 + miss_counter + data purge 接入 | 1d | 无 |
| **P2** | 未命中闭环：聚类 + collector 新入口 + teaser 提示 | 1.5d | P1（P0 的搜索入口更佳） |
| **P3** | 蒸馏数据源：编排 plan 序列接线 + hooks 工具序列采集 | 1.5d | P1 |
| **P4** | LLM 蒸馏：生成 + 审定 UX + 审计 | 1.5d | P3 |

每阶段独立可交付、独立验收（DoD 见各节）；质量门：ruff / basedpyright(0 err) / bandit / 全量测试 + 覆盖率 ≥73。

---

## ⚠️ 风险与开放问题

| 风险/开放问题 | 级别 | 说明 |
|---|---|---|
| 外部 SKILL.md 与 spec-v3 frontmatter 差异清单 | 中 | 安装适配层需逐字段 diff（`docs/skill-format-spec-v3.md` vs anthropics 格式），P0 期间实测 |
| GitHub 搜索信噪比 | 中 | 放宽 topic 后结果质量未实测；策展置顶是第一道防线 |
| `vibe route` 调用方中 agent 与人的占比 | 低 | 影响交互式功能默认开关方向；目前按「agent 优先」设计 |
| PyPI 下载量未知 | 低 | 「零触达」基于 GitHub 侧 0 topic/0 issue 推断；若下载量大则需求侧判断需修正 |
| 劣质自动技能污染路由 | 中 | 蒸馏产物强制人工审定 + 审计 + 项目级隔离（ADR-001「无限累积」警告） |
| 隐式反馈污染置信度 | 低 | 已限定隐式信号只计 application 不计 success |

---

## 附录：评审记录

- **四视角 fanout**（2026-07-18，Kimi explore agents）：产品 UX / 架构实现 / 安全隐私 / 红队替代方案
- **Pi 对抗评审**（2026-07-18，pi 0.80.7）：5 条盲区挑战（① OrchestrationResult 签名耦合 ② NO_MATCH 数据真空 ③ collector 入口不兼容 ④ 数据回流架构难题 ⑤ opt-in 死锁）+ 优先级重排（商店 P0）+ hash-only 计数器方案；经代码复核，①③⑤ 并入设计，④ 以 hooks 第三路径回应
- **分歧裁决**：Pi 提议「砍 crawler 只做 git URL 安装」未采纳（用户要的是搜索发现体验，URL 安装已存在，两者互补）；「LLM 初筛代替策展」降为可选增强
