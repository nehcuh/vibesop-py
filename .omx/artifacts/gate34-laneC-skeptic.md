# Gate34 Lane C 对抗性质疑报告：EvoTrace 四方向（D1–D4）

**立场声明**：本通道职责是反驳。每条反对意见给出代码级证据；第 4 节（违心但公正地）给出各方向的最小成立版本。

## 0. 总判决先行

| 方向 | 裁决 | 一句话理由 |
|---|---|---|
| D1 promote verifier | **推迟**（降为 trigger lint 可立即做） | 在 n=3 的簇上算"捕获率"是伪统计；且 M5 内容哈希门已经挡住了它声称要防的事故 |
| D2 轨迹去重 | **有条件接受**（只做展示层折叠，否决 intake 过滤） | intake 过滤直接违背 gate32 已裁决的设计决定；簇级去重 S40 刚 ship |
| D3 分源阈值 | **否决**（降级为展示描述统计） | source 一共只有 2 个值且早已分闸；在 n≈20 上分桶是伪科学 |
| D4 hash chain | **否决** | 没有威胁模型；且 hand-edit JSONL 是代码里明示支持的用法，hash chain 会把合法操作变成"篡改告警" |

## 1. 逐方向反驳

### D1 Promote verifier 通道 —— 防错了层，且统计上无意义

**反驳 1：它声称解决的事故在现有架构里到不了路由。** "未审不注入"是双层保证：draft 写在 `CandidateManager` 不搜索的路径（`skill_promote.py:28-33` 模块 docstring），且 M12 M5 内容哈希编辑守卫（`skill_promote.py:453-460`）拒绝激活未被人手编辑过的草稿。"空壳技能被激活"这条事故链**已经断了**——D1 是在一扇已有两道锁的门前再加第三道锁。

**反驳 2：空壳的根因 D1 碰不到。** 渲染器 `_render_skill_md`（`skill_promote.py:1916-2182`）只产出元数据 + TODO 骨架；当簇内没有 ≥70% 频率的步骤名时，Steps 块就是一行 TODO，注释自己承认："the trace shows WHAT was asked, not HOW it was done"（`skill_promote.py:2048-2052`）。verifier 回放测的是"触发器能不能召回历史 query"，而空壳的病在"步骤内容不存在"——**verifier 对一个没有内容的技能打出 100% 捕获率，反而是假阳性通行证**：它把"触发词碰巧匹配"误报为"技能可用"。这比没有 verifier 更糟，是制度化的自欺欺人。

**反驳 3：统计无意义。** `DEFAULT_MIN_CLUSTER_SIZE = 3`（`skill_promote.py:141`）。在 3 条 query 上，捕获率的取值粒度是 {0%, 33%, 67%, 100%}。任何阈值在 n=3 下要么恒 FAIL 要么恒 PASS，区分度为零。2/3 成功的 Wilson 95% 置信区间大约是 [0.21, 0.94]——这个"指标"没有任何决策价值，只会制造看板上的红绿噪音。

**反驳 4：归因混淆。** draft 的 triggers 在 promote 后必然被人手改写（M5 强制），所以 shadow 回放 FAIL 时分不清是"渲染器骨架烂"还是"人写的 trigger 烂"。一个无法归因的 FAIL 信号，上了看板也只是礼仪性指标。

**反驳 5：历史教训反着用。** P0-lite 的 130/1620(8.0%) 劫持铁证说明的是"**自动触发**危险"。但 D1 管的 promote→activate 链路本来就是人工的；真正会从 EvoTrace 式自动化里学坏的是"verifier 过了就自动激活"这个下一步——D1 一旦建好，"都测过了为什么不能自动激活"的滑坡几乎必然出现。D1 不是护栏，是自动化的特洛伊木马。

### D2 子代理轨迹去重 —— 一半已 ship，另一半会误杀唯一的成功样本

**反驳 1：intake 过滤直接违背已裁决的设计决定。** gate32 A1 的注释白纸黑字（`skill_promote.py:342-349`）：agent prompt 回声"They are legitimate pool members for human review — **bd1bc217 was promoted from such a cluster**"。也就是说，全系统目前**唯一一个真实 promote 成功案例**恰恰来自 D2 要过滤掉的那类簇。intake 过滤会亲手掐死自己的训练信号。现有设计的选择是：保留入池给人审，只在**自动预填 triggers** 时用 `_is_agent_prompt_shape` 卫生过滤（`skill_promote.py:366-378`）——这是"过滤自动化，不过滤人审"的正确切分，D2 把它推反了。

**反驳 2：低信息垃圾已经在 intake 被滤了。** `_is_low_information_query` 作为 pre-pool filter 已在 `scan_candidates` 生效（`skill_promote.py:1429-1433`），含继续体/枚举回复两套形状规则，且每条规则都带"must-NOT-catch 反例"测试。D2 的"intake 过滤"增量只剩 agent prompt 回声一类——即反驳 1 里被明确保留的那类。

**反驳 3：簇级折叠刚 ship，阈值还没过观察期。** gate30（S40，2026-08-22 push `f76dd61`）刚上线 `MERGE_JACCARD_THRESHOLD = 0.5` 的 overlap-merge，阈值是用真实池标定的：真重复对 0.88–0.99，假重复 ≤0.41（`skill_promote.py:118-126`）。D2 的"簇内 Jaccard>0.8 折叠"落在 **0.41–0.88 这个完全没有标定证据的无人区**。在一个刚调好 0.5 的系统上再叠一个没标定的 0.8，是拿上周的教训当耳旁风。

**反驳 4：误杀长 prompt 工作流是确定性的。** `_AGENT_PROMPT_MAX_LEN = 150` 的注释写明依据（`skill_promote.py:360-363`）：真实用户指令 <100 字符，长 prompt 是 delegation payload。但这个依据只适用于"自动变成 trigger"的场景。粘一段报错日志、粘一份 spec 让 agent 执行——这些都是合法的、且往往高价值的用户工作流，按长度/形状在 intake 杀掉它们，等于让发现队列对"重度用户"失明。过滤规则的 false negative（垃圾入池）代价是**人审时多看一眼**；false positive（合法流量消失）代价是**永远学不到这个模式**。不对称性决定必须保守。

**反驳 5：问题规模被夸大。** 队列有 30 天 TTL（`_TTL_DAYS`，`skill_promote.py:100`）、分类容量帽（`MAX_PENDING=50` / `MAX_PENDING_UNSTABLE=20`）、admit-only-if-better 驱逐。垃圾的代价是评审注意力，不是正确性、不是存储、不是路由行为。为一个"注意力成本"问题改动数据准入层，收益成本比很差。

### D3 分源阈值 —— 要么已存在，要么是伪科学

**反驳 1：按 `source` 分桶只有 2 个桶，且早已分闸。** `CandidateSource = Literal["gold", "miss_recurrence"]`（`skill_promote.py:89`）。miss_recurrence 已有独立 admission gate：`MISS_RECURRENCE_MIN_PAIRS=3` / `MISS_RECURRENCE_MIN_DAYS=2` / `MISS_COSINE_THRESHOLD=0.70`，与 gold 的 `min_gold_rate=0.60` 完全分离（`skill_promote.py:141-167`），且 miss 阈值是用 48 对手工标注对校准过的（`skill_promote.py:158-165`）。**D3 按字面意思已经实现了。**

**反驳 2：如果"source"指发现队列里的细分 provenance，那是小样本分桶。** cmspark 发现队列 20+ 条，分到 5+ 个桶后每桶 n≈4，大量桶是 "gold 0%"。n=4 时 0% 与 50% 的差异在统计上不可区分（Fisher 精确检验 p 值根本下不来）。从这些桶"实测成功率→定阈值"，输出的是披着数据外衣的随机数。

**反驳 3：代码库自己已经写了正确做法。** `MISS_COSINE_THRESHOLD` 的注释规定："Re-calibrate once the real miss pool reaches **≥30 distinct keys**"（`skill_promote.py:164-165`）。系统自己定的再校准门槛是每桶 30 个样本。D3 在每桶 4 个样本时动手，违反自己代码库刚写下的纪律。

**反驳 4：保守版本也已存在。** `threshold_suggestion`（`discovery.py:524-541`）已经按 dismiss 计数、按 source 给出**人工可执行的阈值调整提示**，且明确"admission thresholds are never auto-changed"。D3 想自动化的那部分，正是现有设计明确拒绝自动化的部分。

### D4 不可变路由记录 —— 解决一个不存在的问题，还踩了合法用法

**反驳 1：威胁模型为空。** spans.jsonl 是用户本机、自己 CLI 写的 dogfood 观测文件。篡改者是谁？恶意场景不存在；意外场景（进程崩溃写坏）已由 fcntl + AtomicWriter + "坏行 skip 不崩"的读取容错覆盖。hash chain 防的是"有写权限的主动篡改者还试图掩盖篡改"——对本机文件而言这个攻击者无所不能，chain 防不住；对无攻击者场景它是纯开销。

**反驳 2：它会把明示支持的用法变成告警。** `ClusterCandidate.from_dict` 的 docstring 明确写着要防御"**hand-edited files** carrying invalid values"（`skill_promote.py:517-521`）——手改 JSONL 是这个系统**支持的工作流**。hash chain 上线后，每次用户手改都变成"完整性校验失败"。要么告警疲劳被无视（chain 形同虚设），要么逼用户不敢手改（砍掉一个实际在用的调试手段）。两头都是负资产。

**反驳 3：与生命周期操作冲突。** spans 有 age-out、prune、retention purge（留存池 2026-09-19 还要复挖再 purge）。append-only chain 和"删除旧行"天然矛盾：每次 prune 都要重算链或者引入 tombstone 语义。为了给不存在的威胁上链，要给每个生命周期操作加密码学簿记。

**反驳 4：出处可疑。** 这个念头来自 LLM Space 定位文的吸收清单 B4"不可变历史快照"（`docs/decisions/2026-07-31-positioning-vs-llm-space.md:143`）——而原文语境是"evaluation snapshot 不因 rubric 编辑而改写历史"，是**评估可复现性**问题，不是**防篡改**问题。D4 把一个评估语义的需求误读成了区块链式的完整性需求。而且同一份文档里"Absorb (UX only)"的定位说明这本就是 UX 层面的参考，不是核心架构需求。

## 2. 机会成本论证

同一周挂着这些**已承诺、有触发条件、有退出标准**的旧坑：

1. **发现精度首个真实数据点**：cmspark 5 条 stable 候选的 promote/dismiss 还等用户做。这是整条 observe→cluster→review 流水线的**第一个端到端精度测量**。在端到端精度未知的情况下，D1–D4 全是在优化一条"不知道准不准"的流水线。
2. **M3 阈值复检**：`calibrate_behavior_threshold.py` 等"候选簇 ≥2 条带工具序列 trace"的数据触发。已写好脚本、只差数据。
3. **留存池 2026-09-19 复挖**：时间触发，有死线。
4. **P0-lite 观察期 + 护栏**：8.0% 劫持铁证挂在那里，这是真实测量过的、影响 130 次路由的问题。D1–D4 里没有一个问题有这种量级的实测危害。
5. **发现队列表格 UX**（`dashboard/_discoveries.py`）：用户看不懂 pattern/source/score/behavior 列。这是**唯一被真人用户抱怨过的问题**，且是纯展示层工作，风险为零。D2 真正想解决的"队列里一半看不懂的垃圾"，正确答案多半在这里（展示层折叠/打标），而不是动 intake。

结论：D1–D4 全部工程的预算，填 1+2+3+5 绰绰有余，且每一件都有既有的触发条件背书。开四个新坑 vs 填四个旧坑，团队历史倾向（"开新坑比填旧坑勤快"）本身就是该被对冲的风险。

## 3. 裁决

- **否决 D4**：无威胁模型、与 hand-edit 合法用法冲突、与 prune 生命周期冲突、出处是对定位文的误读。无任何修正版本值得现在做。
- **否决 D3**（按当前表述）：source 维度已分闸；细分桶是 n≈4 的伪科学。降级为"展示层描述统计"，那不是阈值工程，不需要排期。
- **推迟 D1**：推迟到两个前置条件满足——(a) cmspark 首批 promote/dismiss 产出发现精度基线；(b) 参与回放的簇 span_count ≥ 10（给出最低限度的统计区分度）。在此之前只允许做 trigger lint 形式的极简版。
- **有条件接受 D2**：只做**展示层**（队列内按 fingerprint 折叠显示 + agent-prompt 形状打标 + 批量 dismiss），**否决 intake 过滤和簇内 0.8 折叠**。intake 侧维持 gate32 的既定裁决。

## 4. （违心但公正）各方向仍然成立的核心价值 + 最小修正版

**D1 仍然成立的**：promote→activate 之间确实没有任何"这个技能能不能召回它自己的源模式"的冒烟检查——dogfood 里出现过"promoted skill 对自己的 canonical query 只得 0.26 分"（`skill_promote.py:1990-1992` 注释）。
*最小修正版*：不做 shadow 回放 harness，在 `promote --activate` 时加一个 **trigger lint**（<50 行）：triggers 非空、不全是卫生过滤形状、技能对簇内 ≥1 条代表 query 的 recall 得分过阈值——单项不通过只**警告不 FAIL**，不上看板、不设捕获率指标。它查的是"激活前明显坏了"，不是"质量达标"。

**D2 仍然成立的**：发现队列的认知负荷是真的——约 64% miss 池是机器回声（`skill_promote.py:344-346`），人审 20+ 条队列时一半时间在看垃圾。
*最小修正版*：纯展示层。CLI/dashboard 队列按既有 fingerprint 分组折叠，agent-prompt 形状的行打 `shape: agent-echo` 标签并支持一键批量 dismiss。不改任何 admission 逻辑，不删任何数据。

**D3 仍然成立的**："gold 0%" 行反复出现说明全局阈值对某类来源可能系统性失灵，这个**怀疑**值得被数据回答，只是不该用"定阈值"来回答。
*最小修正版*：在发现队列 UI 加一列 per-source 的累计 success/dismiss 计数（描述统计，只读）。等任一 source 攒到 ≥30 样本（沿用代码库自己的再校准门槛），再谈阈值。

**D4 仍然成立的**：replay 的可复现性（"我回放的那次执行和记录是否一致"）在调试时有微弱价值。
*最小修正版*：什么都不建。如果哪天真需要，加一个 `vibe trace verify <trace_id>` 调试子命令，按需重算单条 trace 的摘要即可——不要 chain，不要写路径改动，不要默认校验。

---

**落盘建议**：本报告可作为对抗评审记录存 `docs/decisions/`；若团队仍要推进，建议只接受 §4 的四个最小修正版作为一份合并的轻量提案，D1 完整版与 D4 从路线图删除。
