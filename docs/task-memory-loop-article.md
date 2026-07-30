# 让 AI Agent 记住你做过什么：VibeSOP 的任务锚定记忆与技能演化闭环

> 本文基于 VibeSOP（github.com/nehcuh/vibesop-py）在 2026 年 7 月最后一周完成的 task-memory-loop v3 MVP 的真实开发历程。4 周，5 个里程碑（W0–W4），从"agent 不知道自己在做什么"到"agent 把你做过的事情沉淀成可复用的技能候选"。这是一篇关于**观察→行动闭环**的复盘。
>
> 配套阅读：[Vibe Coding 实战](./vibe-coding-article.md) 讲的是怎么和 AI 一起活下来；本文讲的是怎么让 AI 把活过的东西记下来。

---

## 零、先说人话

如果你时间有限，读完这一节就够了。

**问题**：今天的 AI 编码 agent（Claude Code、Cursor、Grok Build、Kimi、Pi、OpenCode……）有一个共同的盲点——**它们看得见自己正在做什么，但记不住你做过什么**。

**结果**：

- 你上周解决过一个棘手的"截图权限"问题，今天再遇到，agent 又从零开始瞎摸。
- 你重复执行了十次的"部署→验证→回滚"流程，从来没变成 agent 的本能。
- 每个 agent 平台各自为政：你在 Claude Code 里面积累的 SKILL.md，搬到 Kimi 里就是一份陌生文档。

**VibeSOP 的回答**：

> **Mastra 让你看清楚 agent 在做什么；VibeSOP 让 agent 记住你做过什么。**

这是个**闭环**：观察 agent 工作 → 按"任务"聚类 → 提取高频高成功率的任务模式 → 生成人审 SKILL.md 草稿 → 你点头之后才进入技能池。本文讲这个闭环是怎么被一步步逼出来的，以及我们和已有工作的根本差异。

---

## 一、场景：一个独立开发者和他的五个 AI agent

VibeSOP 服务于一个具体的 persona：**独立开发者，单机工作，但同时使用多个 AI 编码 agent**。

这听起来像个边缘场景，但其实是 2026 年中 AI 编码工具爆发的自然结果：

- **Claude Code**——主力，写代码、跑测试、改架构都靠它
- **Grok Build**——做对抗评审，抓设计漏洞
- **Kimi Code CLI**——长上下文窗口，跑大文档分析
- **Pi**（OpenCode 系）——产品视角评审，UX 反馈
- **Cursor / Aider / Cline**——按场景切换

每个 agent 都有自己的技能格式、自己的命令系统、自己的"最佳实践"。开发者面对的不是"哪一个更好"，而是**"在什么时候用哪一个，记不记得上次怎么用的"**。

VibeSOP 最早的定位——**SkillOS（技能操作系统）**——就是为这个场景而生的：一个跨平台的技能路由、编排、生命周期管理层。你表达意图，VibeSOP 帮你找到合适的技能；技能来自哪里、跑在哪个 agent 上，VibeSOP 替你桥接。

但路由只是入口。**真正的痛点在 4 周前暴露出来**：路由用得越多，越发现 agent 永远在"现在这一刻"工作，没有任何跨会话的记忆。

---

## 二、问题：观察和行动的不对称

2026 年中是一个有意思的时间点：**观察侧的工具 suddenly matured，行动侧却几乎一片空白**。

### 2.1 观察侧的成熟

- **OpenTelemetry** 把 trace/span 语义标准化了
- **Langfuse、Langchain Studio、Helicone** 把 LLM 调用可视化做到了产品级
- **Mastra Trace Intelligence**（2026-07 发布）甚至开始用 LLM 给 trace 打标签、聚类

你打开 dashboard，能看到 agent 跑了什么模型、调了哪些工具、每一步耗时多少、token 花在哪里。**观察已不是问题**。

### 2.2 行动侧的真空

但你关掉 dashboard 之后呢？**什么都不会发生**。

- 没有一个工具会告诉你："这个任务你已经成功执行过 8 次了，要不要固化成一个技能？"
- 没有一个工具会在你下次说"修 dashboard 反思 bug"的时候，提示"上次你走了 X→Y→Z 这三步，30 秒搞定，要不要照着来？"
- 没有一个工具会把你跨 Claude Code、Grok、Kimi 的执行经验**沉淀成一个统一的、平台无关的技能格式**

观察侧在记事，行动侧在失忆。这就是 VibeSOP task-memory-loop v3 要闭合的环。

### 2.3 为什么这事难

难在三个地方：

1. **"任务"是什么？** —— 你说"修 bug"，agent 看到 `trace_id=abc123`，两者怎么对应？没有 task anchor，所有观察都是孤儿数据。
2. **"成功"是什么？** —— 一个 trace `status=completed` 不代表它值得复用。可能只是 agent 把 bug 藏起来了。被动信号怎么提取真正的"金标准"？
3. **"自动写技能"的恐惧** —— 如果让 LLM 自动生成 SKILL.md 并自动注入到路由系统，**一次幻觉就毁掉整个技能池的信任**。怎么设计"人审前的隔离"？

这三个问题，每一个都已经在网络上被以不同方式回答过。但**没有一套回答把它们闭合起来**。

---

## 三、网络上类似的工作

在动手之前，我们调研了几条相关的路径。

### 3.1 Mastra Trace Intelligence（竞品，2026-07）

**他们做什么**：SaaS 产品。每条 trace 喂给 LLM，生成 4 个信号（意图、结果、成本、异常）；然后用 UMAP 降维 + HDBSCAN 聚类，把相似 trace 归堆；最后在 dashboard 上展示"这是你最常见的 5 类 agent 任务"。

**他们的局限**：

- **纯观察**——你在 dashboard 上看完之后，什么都不会自动发生
- **LLM 给 trace 打标签**——一次 LLM 幻觉就污染整条 trace 的归属
- **SaaS 形态**——独立开发者的代码、prompt、调试上下文要全部上传，隐私和成本都不可接受
- **聚类粒度靠 UMAP**——单用户低频场景下（每周几十条 trace），HDBSCAN 的密度假设根本不成立，会聚出"噪声簇"

**我们的差异**：VibeSOP 不靠 LLM 猜聚类，靠**用户路由时的 query 直接派生 task_id**（`sha1(normalize(query))[:16]`，纯 query 内容，不含 project_path、不含 session）。同一个 query 自然归到同一个 task——不需要 LLM，不需要 UMAP，密度假设也不需要。

### 3.2 AgentTrails（VLDB 2026 workshop 论文）

**他们做什么**：把 trace 组织成 provenance graph（哪些 span 依赖哪些 span），跨 trace 把"语义相似的 capsule"聚到一起，最后 join 成一张"任务家族"图。

**论文自己的承认**：用 LLM 猜依赖边**不 scale**——每条 trace 多花一次 LLM 调用，1000 条 trace 就是 1000 次 LLM，成本和延迟都崩。

**他们的价值**：joined graph 的 support count（某个子流程在多少条 trace 里出现）是判断"哪些步骤是 canonical"的强信号。

**我们的差异**：

- **不猜依赖边**——VibeSOP 用 `parent_span_id` 直接构造 DAG，零 LLM
- **砍掉 joined DAG 作为 UI 卖点**——单用户不需要 viz，看一眼就关了
- **保留 support count 的核心价值**——W4 的 `label_step_frequency`（core ≥70% / common 30–70% / optional <30%）就是这个思想的简化版：跨同一 task 的多次执行，统计每个 step 出现的频率，core 步骤就是 canonical

论文的洞察我们吸收了，论文的 LLM 路径我们绕开了。

### 3.3 Matt Pocock 的 wayfinder 技能（mattpocock/skills）

Matt Pocock 是 TypeScript 教育圈知名人物，2026 年中他发布了 `mattpocock/skills` 仓库——一个精心策划的技能集合，其中 **wayfinder** 是核心：

> "Chart the path to a goal as a decision map (tickets on the issue tracker), then work through them one by one. Forces planning before execution — counters vibe coding."

wayfinder 不是单一技能，它是一个**规划流水线**：

- `grilling`（拷问）—— 用追问暴露隐藏假设
- `domain-modeling`（领域建模）—— 固化系统边界和实体
- `to-spec` / `to-tickets`（转规格 / 转工单）—— 把规划输出成可执行工件
- `research`（研究子代理）—— 扇出搜索
- `prototype`（原型）—— 用完即扔的验证

这是一套**自上而下的规划纪律**，对抗"上来就写代码"的 vibe coding。

**他的局限**：

- **技能是预先策划的**——Matt 写的，不是你的工作流自动长出来的
- **通用规划框架**——不知道你上周刚解决过什么 bug
- **不闭环**——用了 wayfinder 不会让你的下次类似任务变快

**我们的差异**：VibeSOP 是**自下而上**的——观察你重复做了什么，把高频高成功率的模式沉淀成候选技能。wayfinder 回答"我应该怎么规划一个新任务"，VibeSOP 回答"我做过什么值得固化下来"。两者互补——事实上我们今天把 wayfinder 整批加入了 VibeSOP 的 featured_registry（7 个 mattpocock 技能，wayfinder 优先级 88 居首），让用户装上之后**可以用 wayfinder 做规划，用 VibeSOP 做记忆**。

### 3.4 Anthropic Claude Code 的 SKILL.md 格式

Anthropic 在 Claude Code 里定义了 SKILL.md 这个轻量级技能格式：一个 YAML frontmatter（name、description、trigger hints）+ Markdown 正文。这是事实标准，Cursor、OpenCode 都在跟进。

**他们的局限**：

- **每个技能都要人写**——SKILL.md 是写出来的，不是长出来的
- **绑定 Claude Code**——`~/.claude/skills/` 是 Claude 专属目录
- **没有反馈闭环**——技能写完之后，用得好不好、该不该淘汰，没有信号

**我们的差异**：VibeSOP **采用 SKILL.md 作为通用格式**，但通过多平台 adapter 分发到 `~/.claude/skills/`、`~/.kimi/skills/`、`~/.config/opencode/skills/`、`~/.config/skills/`（中心存储 + symlink）。同一个技能定义，所有 agent 都能用。更关键的是：**VibeSOP 让 SKILL.md 既能被人写，也能从历史执行模式里被长出来**。

### 3.5 已有的技能包生态：superpowers / gstack / omx

这三个是社区里最活跃的技能包：

- **superpowers**——Python 偏向，TDD / 重构 / 安全审计
- **gstack**——通用工程纪律
- **omx**——脚手架和工作流模板

它们都是**自上而下的策划产物**——作者把自己认为好的实践写成 SKILL.md。

**他们的局限**：和 wayfinder 一样，**通用最佳实践 ≠ 你的最佳实践**。一个独立开发者三周内重复解决了 5 次的"截图权限"问题，不会出现在任何通用技能包里。

**我们的差异**：VibeSOP 在 routing 层把这些外部技能包平等接入（featured_registry 里 superpowers/tdd 优先级 80，mattpocock/tdd 优先级 85，按质量和场景排序），但在记忆层**生长你自己的技能**。两条腿走路。

### 3.6 InstinctLearner（VibeSOP 自己的旧件）

VibeSOP 在 v4.2 就有了 `InstinctLearner`——记录每次路由的 outcome（success/fail），把高置信度决策沉淀为"本能"。这是个雏形的记忆系统，但**只记路由偏好，不记任务执行**。

task-memory-loop v3 的核心升级：**把 InstinctLearner 的 `record_outcome` 当作"金标准主信号"**——用户路由之后是否真的解决了问题，由 InstinctLearner 提供。task-memory-loop 在这之上加任务聚类、加 embedding 召回、加 skill promote。

---

## 四、我们的回答：4 周 MVP

设计原则 10 条（详见 `docs/decisions/2026-07-29-task-memory-product-design.md`），核心是这三条：

1. **拒绝 auto-write skill**——候选池隔离 + 必须人审（"未审不注入"）
2. **Embedding 是主路径**——BM25 在中文 query 上 0% 召回（W0 预检实测），embedding day 1 必需
3. **task_id 纯 query 派生**——`hash(normalize(query))[:16]`，不含 project_path（这一条是 v2 → v3 的关键反转，下面单说）

### 4.1 W0：Instrumentation Fix + 模型选型

发现 task_id 在两个地方是 `None`——CLI 主入口和 hook 入口。修复，加上 dev/prod 自动检测（`PYTEST_CURRENT_TEST in os.environ`，env var 容易忘设）。

跑 embedding mini-benchmark：MiniLM-L12-v2 vs bge-small-zh-v1.5 vs bge-base-en-v1.5。**MiniLM 胜出**（384 维，~120MB，separation −0.274）。

### 4.2 W1：Embedding + Cluster + 金标准检测

把 MiniLM 集成进去，加 cache（model_id 进 hash 防止模型升级后旧 cache 错乱）。cluster 算法：**同 task_id 直接 group**（硬 cluster）+ 不同 task_id 但 cosine ≥0.80 → soft cluster。

金标准规则（多信号）：

- 主信号：`InstinctLearner.record_outcome(success)`
- 辅信号：`status==completed AND has_match==true AND duration<=p50(cluster)`
- 门控：`cluster_size >= 5`，n<5 标 `candidate_success`

阈值 0.85 → 0.80 是 W0 benchmark 后的调整：0.85 时 recall 只有 49%，金标准簇碎成单点。

### 4.3 W2：Recall CLI

`vibe recall "<query>"` —— 单项目，扫当前 project 的 spans.jsonl，embedding cosine top-3，绝对阈值 ≥0.7。输出 top-3 历史 trace 摘要 + step 序列 + 来自哪个 task_id。

未达阈值默认视为无召回——**错召回比没召回更糟**，用户被骗一次就弃用。

### 4.4 W3：Replay 模式

`vibe route --replay` 命中金标准时一键回放：提示"上次处理这个 task 走了 X→Y→Z（trace_id=...），按上次方案执行？[Y/n]"。在 span 里记 provenance——回放产生的 trace 标记 `replay_of=<原 trace_id>`，方便事后评估。

### 4.5 W4：Skill Promote（本文写作时刚 ship）

**这是闭环的最后一公里**。

触发：`cluster_size >= 3 AND gold_rate >= 60%`。反条件：`gold_rate < 30%` 进 unstable 队列（"这 task 本身有问题"诊断）。

流程：

1. `vibe skill scan-candidates` —— 扫近期 spans，聚类，标签 step frequency（core/common/optional），填充候选池（TTL=30d，硬上限 50）
2. `vibe skill candidates` —— 列出待审候选（默认只显示 stable，`--include-unstable` 看全部）
3. `vibe skill promote <cluster_id>` —— 写 SKILL.md 草稿 + status=promoted
4. `vibe skill dismiss <cluster_id> --reason "..."` —— 拒绝并记录原因
5. 人审通过后，`cp -r .vibe/observability/skill_drafts/<id> .vibe/skills/ && vibe skill add .vibe/skills/<id>` —— **手动注入**

最关键的设计：**第 5 步是手动的，不是自动的**。这就是"未审不注入"的字面落地。

---

## 五、设计反转：v2 → v3 的教训

v2 设计曾把"跨项目记忆"作为核心卖点：`task_id = hash(query + project_path)`，理论上同一 query 在不同项目算出不同 task_id，跨项目 cluster 加分。

**grok + pi 双评审独立抓到这个设计的数学矛盾**：

> 一边把 `project_path` 放进 task_id hash，一边把"跨项目 cluster"作为核心卖点——这两个设计数学上互斥。同一 query 在不同项目算出不同 task_id，跨项目 cluster 永远聚不起来。

v3 修订：**MVP 退回单项目 + task_id 纯 query 派生**。跨项目作为 opt-in feature defer 到 post-MVP。

教训记录在 [`feedback-feature-mutual-exclusion-check`](../memory)：**每加一个特性，必须问"与已有特性数学上是否互斥"**。两个互斥设计塞同一方案，是设计 review 应该早抓的。

---

## 六、W4 ship 时 grok 抓到的架构 bug

W4 第一版 ship 之后，按惯例跑 grok + pi 双评审。grok 抓到一个**架构级**的问题：

> `materialize_candidate` 把 SKILL.md 草稿写到 `.vibe/skills/<id>/SKILL.md`。
> `.vibe/skills/` 这个路径在 `CandidateManager._build_search_paths` 里——
> **每次 promote 出来的草稿都会被下一次 `get_candidates()` 自动发现**。
> "未审不注入"在架构上是假的。

原来的测试为什么没抓到？因为它 patch 了 `CandidateManager` 类，断言"promote 从不构造 CandidateManager"——**vacuously true**。promote 本来就不碰 CandidateManager，断言通过的同时保证已经被打破。

修复：

1. 草稿路径改为 `.vibe/observability/skill_drafts/<id>/SKILL.md`（不在搜索路径里）
2. 测试改为构造**真实**的 `CandidateManager(project_root=tmp_path)`，promote 之后断言草稿的 `skill_id` **不在** `get_candidates()` 返回的 248 个技能里

这个 bug 是"评审闭环 ≠ 生产可用"的活案例（见 [`feedback_no_premature_production_ready`](../memory)）。代码长得像对的、测试是绿的、设计文档写得很漂亮——但架构上是假的，只有独立评审从外部看才能抓到。

---

## 七、和已有工作的根本差异

把上面散落的差异点收一收：

| 维度 | 已有工作 | VibeSOP |
|------|---------|---------|
| **观察 vs 行动** | Mastra、Langfuse 等只观察 | 观察 + 自动候选 + 人审 + 注入 |
| **任务 anchor** | Mastra 用 LLM 打标签；AgentTrails 用 provenance graph | task_id 纯 query 派生，零 LLM |
| **聚类** | UMAP + HDBSCAN（密度假设） | task_id 硬 group + embedding soft cluster (cosine ≥0.80) |
| **金标准** | LLM 判分 / 用户手标 | InstinctLearner 的 record_outcome 当主信号 |
| **技能来源** | 自上而下策划（Matt Pocock / superpowers / gstack / omx） | 自下而上从历史执行生长 + 平等接入外部策划 |
| **平台耦合** | Claude Code 绑 `~/.claude/skills/`；Cursor 绑自己的 | SKILL.md 中心存储 + 多平台 symlink adapter |
| **自动注入** | Anthropic Skills 自动加载 `.claude/skills/` | "未审不注入"：草稿路径不在 `_build_search_paths` 里 |
| **隐私** | Mastra / Helicone 是 SaaS | 单机本地，spans 落 `.vibe/observability/` |
| **数据密度假设** | Mastra 假设团队高频；AgentTrails 假设大量 trace | 单用户低频——所以 kill criteria 测效用不测频次 |

最核心的差异是**第一行**：所有已有工作要么只观察（Mastra、Langfuse），要么只执行（Claude Code skills、外部技能包），**没有人闭合 observe→cluster→review→inject 这个环**。VibeSOP 的 task-memory-loop v3 是第一次把这个环走通——而且**最后一公里强制人审**，因为我们对 LLM 自动写技能的能力保持怀疑。

---

## 八、接下来做什么

MVP ship 不等于 production ready。接下来 4–12 周的 post-MVP roadmap：

1. **跨项目 recall**（v3 砍掉的特性）：单项目验证通过后，加 allowlist + embedding-only index（不原文合并），promote 跨项目加分需人工确认
2. **launchd/cron preset**：`scan-candidates` 定时跑（比如 `0 */6 * * *`）
3. **候选池 timeline/DAG 可视化**：CLI 跑通后再考虑
4. **W12 kill criterion**：active skill 在 routing 中**实际命中** ≥3 次/月——否则归档

同时还有一批 W4 review 时 defer 的 P2：

- `vibe skill candidate <id>` 详情视图
- `vibe skill unpromote`（promote→dismiss 目前是非对称的）
- 通用 AtomicWriter 的 inode-rename race（继承自 ReflectionStore 的已知限制）
- common step 在 SKILL.md 草稿里的可见性

这些不影响 MVP 的核心价值，但决定它能不能长期跑下去。

---

## 九、一句话总结

**今天的 AI 编码 agent 看得见自己正在做什么，但记不住你做过什么。**

观察侧的工具成熟了，行动侧还是空的。Mastra 让你在 dashboard 上看清楚 agent 在干什么，AgentTrails 论文证明了 joined DAG 的价值但 LLM 猜边不 scale，Matt Pocock 的 wayfinder 给了规划纪律但是是预先策划的，Anthropic 的 SKILL.md 是事实标准但每条都要人写。

VibeSOP task-memory-loop v3 闭合了这个环：

> 观察 → 按 task 聚类 → 提取高频高成功率模式 → 生成人审 SKILL.md 草稿 → 你点头之后才进入技能池

4 周 MVP，5 个里程碑，55 个新测试，3 轮 grok + pi 对抗评审，2 次设计反转（v1→v2→v3），1 个被独立评审抓到的架构级 bug。**核心教训**：

- **复杂设计必须双评审**——自对抗容易抓表面漏结构性（见 [`feedback-dynamic-workflow-external-review-first`](../memory)）
- **评审闭环 ≠ 生产可用**——vacuous test 是已知反模式（见 [`feedback_no_premature_production_ready`](../memory)）
- **每加一个特性，必须问"与已有特性数学上是否互斥"**（见 [`feedback-feature-mutual-exclusion-check`](../memory)）

这三条比任何具体代码都重要。

---

> **状态**：task-memory-loop v3 MVP 已 ship（W0–W4 全过 review gate）。本文是这一阶段的复盘。
>
> **下一步**：W12 kill criterion 验证——active skill 在 routing 中实际命中 ≥3 次/月，否则归档。如果 12 周后这条线没过，说明"agent 记事"是个伪需求，我们会老实承认。
>
> **代码**：[github.com/nehcuh/vibesop-py](https://github.com/nehcuh/vibesop-py)
> **设计文档**：[`docs/decisions/2026-07-29-task-memory-product-design.md`](./decisions/2026-07-29-task-memory-product-design.md)
> **W4 review brief**：[`docs/decisions/w4-review-brief.md`](./decisions/w4-review-brief.md)
