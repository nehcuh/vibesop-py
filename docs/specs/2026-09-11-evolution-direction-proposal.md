# 提案：VibeSOP 演进方向 — 把「可信」从声称变成可测量

> 响应任务书：`docs/specs/2026-09-11-evolution-direction-prompt.md`
> 日期：2026-09-11 · 基线 commit：`60fd0487` · 状态：**设计提案，未实现，未跑任何实验**
> 证据等级：【实测】= 本次真实读取/执行得到；【文档】= 有记录但本次未复跑；【假设】= 待实验判决

## 0. 一句话

把 gate45 已证明的确定性纪律（hermetic 中和、内容指纹、退出码语义、吸收守卫）推广到四个未观测区——语义层方差、禁令执行、历史收敛、no-match 双向误差——全部 report-only、零门禁化；先用方向 E 把一切产物落进版本控制。

## 1. 事实基础（我实际读了什么）

| 文件 | 确认的事实 | 证据等级 |
|---|---|---|
| `docs/ROADMAP.md` | 「图书管理员先可信」；W1（D1–D5）已随 8.3.0 交付、8.3.1 修复轮进行中；W2 = E1–E4；禁止清单（整机 CLI / LLM 评审当放行闸 / 墙钟叙事）；头部 8.2.0 滞后于正文 | 实测（通读 1–45、85–129） |
| `pyproject.toml` | `version = "8.3.0"` | 实测 |
| `.omx/artifacts/next-opt-design-v1.md` | L1–L5、D1–D5 全文；D4 = 不把 LLM 评审做成常驻默认注入；D3 负例闸最低集 | 实测（通读） |
| `docs/dev/routing-benchmark.md` | hermetic 六步；吸收守卫拒绝 `ok1: true→false`；退出码 0/1/3；2026-08-28 确定性证明；§deliberately NOT gated 承认语义层（embedding / semantic_index 回退 / AI triage）与 SCENARIO/INDEX 在 CI 不可见 | 实测（通读）；证明未复跑→文档 |
| `src/vibesop/core/routing/benchmark.py` | `HERMETIC_POSTURE`（:50）、`compute_fingerprint`（:97）存在 | 实测（函数清单；未逐行） |
| `src/vibesop/core/observability/behavior_consistency.py` | 0.5 待验证起点；三态语义；单工具 trace 静默排除（gate24 pi#5 accepted）；隐私只读 name | 实测（通读） |
| `.omx/artifacts/m3-behavior-calibration.md` | 2026-08-21：同簇正例对 = 0、跨簇负例对 = 1，exit 2 fail-closed | 实测（通读）；span 计数未复跑→文档 |
| `docs/specs/2026-09-09-verification-contract.md` | 模型评审与机器验收分别记录；不以自述代证据；类型检查不 exit-3 兜底 | 实测（通读） |
| `CLAUDE.md` / `AGENTS.md` | uv-only、验证命令、多平台部署面 | 实测 |
| `.vibe/optimization-plan{,-p1,-p2,-auto-opt}.md` | 四份同日（2026-07-20）；p2 含 P2-A1..A4（补测试）与 P2-B1（_shared 拆分） | 实测（ls+mtime+抽查；未逐字） |
| `.omx/artifacts/gate*` | 390 个文件（tracked 313）；抽查 gate1-review-claude.md（`[P1]` 编号列表 + 门禁结论行）、gate10-claude.md（MAJOR/MINOR/NIT 计 2）——标签异构 | 实测（抽查 2 份） |
| `docs/specs/2026-09-11-optimization-convergence-requirements.md` | R1–R7 全文；建议序 R4→R3→R1→R2→R7→R5→R6 | 实测（通读） |
| `.omx/artifacts/optimization-convergence-r3/r4-prereg.md` | 判据写死、状态「尚未执行」 | 实测（通读） |
| `scripts/measure_null_report_rate.py`、`scripts/check_behavior_calibration_readiness.py` | 骨架就位，`TODO(r3-wire)` / `TODO(r4-wire)` 未接线 | 实测（grep） |
| 版本控制状态 | `.git/info/exclude` 含 `.omx/`；`.gitignore:143` 含 `.claude/`；HEAD 跟踪 `.omx/` 恰 356 个 | 实测（`git ls-tree -r HEAD --name-only .omx/ \| wc -l`） |

## 2. 现状判断

**已经解决好的**
- 确定性路由门禁的完整 D 类纪律（六步中和、内容指纹、0/1/3、吸收守卫）+ 逐字节复现证明【文档】。
- 负例闸 `must_not_inject`（hermetic YAML + runtime 两层）。
- 验证契约纪律：不以自述代证据；模型评审与机器验收分记；类型检查不 exit-3 兜底。
- 研究结论已结构化为 R1–R7；R3/R4 已预注册、骨架就位（待接线）。

**已承认但未度量的盲区**
- 语义层 CI 不可见（routing-benchmark.md:49–56 自己写明）。
- 0.5 阈值从未被真实数据检验（正例对 = 0）。
- 「禁止 LLM 评审当放行闸」是文档不是机制。
- 「找不到匹配是成功」无任何数字在测。
- gate1..45+ 与四份优化计划的收敛性从未被统计。

**已发生但被忽略的静默损失**
- `.omx/` 新写入被本地 exclude 静默忽略；356 个历史文件靠强制入库幸存；本轮 R3/R4 prereg 也是 `git add -f` 抢救进暂存区的。

## 3. 候选方向

### 方向 A：语义层可靠性画像（观测，不是门禁）

**要解决的问题**：`docs/dev/routing-benchmark.md:49–56` 承认 embedding、semantic_index 回退、AI triage 与 SCENARIO/INDEX 层在 CI 完全不可见；确定性最强的部分被覆盖得最好，非确定性最强的部分零观测。

**提案**：在 `scripts/eval_routing.py` 增 `--profile-semantic` 姿态：保留 hermetic 六步中的第 1/2/6 步中和（cwd→tmp、HOME→tmp、pin 候选宇宙），放开第 3/4 步（不 null `load_sentence_transformer`、`enable_embedding/enable_ai_triage=True`），SCENARIO 维持 pin 空。同一 commit、同一 fixture 重复 N 次，每次记录每题 top-1 primary 与命中 layer。**控制组**：null-embedding 跑同样 N 次，必须 100% 稳定，否则测到的是 harness 噪声而非语义层方差。

**指标定义（可计算）**：每题 top-1 稳定度 = 众数 primary 出现次数 / N（∈(0,1]）；layer 稳定度同式；按题集分层报告均值与直方图。产物：`docs/benchmark/semantic_profile/<fingerprint短码>.json`（含 N、env pin 清单、torch/HF 版本、线程设置）+ 人读 md 摘要。复用既有 4 个题集（`tests/benchmark/routing_eval*.yaml`），不新建数据集。

**N 与机器差异隔离**：N=10（分辨率 0.1；成本 = 10×题量次路由）。机器差异按 hermetic 既有先例隔离（HOME/cwd/pin），另固定 `HF_HOME` 指向本地缓存并置单线程（`OMP_NUM_THREADS=1` + `torch.set_num_threads(1)`）——单线程 CPU 推理的运行间确定性是【假设】，由控制组判决。

**凭什么不是门禁**：退出码恒 0，任何阈值化都会把随机层做成 flaky gate；ROADMAP:35 禁 LLM 评审当放行闸；report-only 先例见 routing-benchmark.md:4–7（Routing Eval report-only 永久不做门禁）。

**成功判据 / 证伪**：成功 = 控制组稳定度恰为 1.0（harness 自检过）且语义层产出首个数字化画像。证伪：(a) 控制组不稳定 → harness 在测噪声，先修 harness 再谈数据；(b) 语义层稳定度 ≈ 1.0 → 盲区实际很小，A 降级为低频抽检，不投入更多。

**成本与依赖**：eval_routing.py 一个姿态分支 + 聚合报告；无模型成本外的依赖；前置 = 方向 E（产物须落跟踪路径）。

**与 E1–E4**：E1 的前置。E1 判「弱模型命中/拒判」前需先知道现栈语义层自身方差，否则弱模型差异与方差混叠。与 E2/E3/E4 无关。

### 方向 B：把「禁止 LLM 评审当放行闸」从声明变成机制

**要解决的问题**：禁令在 `docs/ROADMAP.md:35`，是文档不是机制；无任何东西在检测「某条代码路径把 LLM 输出当成门禁判据」。R5（requirements:233–263）落的是运行时验证记录字段（proposer/verifier 同源 → unsupported），覆盖产品面，不覆盖 CI/流程面。

**提案（两层，B1 先行）**：
- **B1 声明式闸注册表**：仓库内新增注册表（yaml），为 CI 每个 required job 声明 `decision_source: deterministic | human`；新增脚本交叉核对 `.github/workflows/ci.yml` 的 job 清单与注册表：缺登记者红灯；声明含模型输出者为 required 即红灯。
- **B2 静态禁入**：对注册表枚举的闸脚本集做 import 扫描：`decision_source: deterministic` 的脚本禁止顶层 import `anthropic`/`openai`。粗粒度可绕过，但把「无意引入」变成红灯。

**边界**：不扩大产品面（产品代码零改动）；不做常驻默认注入（next-opt-design D4）。**诚实极限**：检测不了「人把模型结论粘进 PR 批注」，残余面靠人纪律——机制缩小表面，不归零。

**成功判据 / 证伪**：成功 = 注册表覆盖 100% required job（机器可查）+ 单测用 fixture workflow 注入带 provider import 的 required job 能红灯。证伪 = 若 CI job 集漂移使注册表持续过期（如 3 个 cycle 内 >50% 条目失配），维护成本超收益，退回文档禁令并记录。

**成本与依赖**：1 yaml + 1 脚本 + 定向测试，半天级；需维护者逐 job 认定 decision_source（人工确认项）。

**与 E1–E4**：无关。与 R5 互补：R5 管运行时验证记录，B 管 CI/流程层。

### 方向 C：优化循环的收敛度量（零新模型跑动）

**要解决的问题**：`.vibe/optimization-plan*.md` 四份同日、无共享账本（requirements R1 缺口证据）；`.omx/artifacts/gate*` 45+ 轮从未被统计。问：不新跑任何模型，能否从历史算出重复伪影占比？

**可行性判定：部分能**。发现以带标签列表存在于 gate 文件（gate1-review-claude.md:15 起 `[P1]` 编号列表 + 「门禁结论」行），可确定性抽取 (gate, reviewer, severity, title)。但标签体系异构（`[P0/P1/P2]` 与 `MAJOR/MINOR/NIT` 两套并存，gate10-claude.md 后者仅计 2 处）【实测：抽查 2 份】，需双套映射 + 每文件覆盖率上报。

**提案**：新增 `scripts/parse_gate_findings.py`（纯文本解析，零模型）：抽取 → 标题归一化（小写、去标点、去路径）→ 两级去重（精确匹配 = 保守下界；token-Jaccard ≥ 0.8 = 上界）→ 输出每轮去重前后新增数与重复占比区间，按 severity 分层。先做 10 文件人工对答案 pilot。

**观察性声明（强制）**：gate 的模型组合并非随机分配（requirements §5.5 同款混杂），结论只能写「观察性」，不得支持因果主张；因果需 R7 的受控回测。

**成功判据 / 证伪**：成功 = pilot 抽取精确率 ≥ 0.9（10 文件人工对答案）+ 产出重复占比区间。证伪 = pilot < 0.9 → 确定性路线死，改写型伪影的量化只能靠 R2 的 ≥30/30 对标注先行——那也是真实答案。

**成本与依赖**：零模型成本；成本 = 解析器 + 人工 pilot（10 文件量级）。

**与 E1–E4**：无关。与 R1/R2/R7：C 是它们的回溯孪生；C 的重复占比直接决定 R2 标注投资是否值得先花。

### 方向 D：no-match 率作为一等指标（双向误差）

**要解决的问题**：产品命题已改口「找不到匹配是成功」（ROADMAP:11），无任何度量在测 no-match 发生率是否合理。

**现状盘点**：过度命中侧——`must_not_inject` 负例闸（hermetic YAML + runtime 两层）已存在，但最低集全是「明显不该有技能」类（写总结/翻译/闲聊），**近失类空白**【实测：核对 next-opt-design D3 最低集清单】；过度拒绝侧——positive 条目（`expect` 非空）的 no-match 已隐含在 ok1 失败里，但没有聚合成率、没有分层、没有生产侧数字。

**提案（三件，全部零模型）**：
1. report-only 扩展：eval_routing 输出混淆计数——N_pos / N_neg / 过拒数（expect 非空 → 无 primary）/ 过灌数（must_not_inject → 有 primary 或 fallback_llm）/ 各 layer no-match 率。零新标签。
2. 负例补强：`must_not_inject` 增 `near_miss` 子类（与某技能触发词形近但域外，≥10 条）；「最低集可增不可减」允许增量。
3. 生产侧：route span 已在生产落盘（behavior_consistency.py:120–131 按 `route:` 前缀 join 是既有口径），新增聚合脚本读 spans.jsonl 输出窗口化 no-match 率 + Wilson CI。

**与 R3 的区分（不可互替）**：R3 = LLM 分析/评审路径的空报告率（发射偏差，「敢说没有」在评审层）；D = 路由层拒判正确性（「敢说没有」在检索层）。同命题两层两指标。

**与 E1**：D 是 E1 的判据前置——E1 两臂的「命中/拒判」比较需要 D 的指标定义与生产基线，否则「弱模型拒判是否异常」无从判定。

**成功判据 / 证伪**：成功 = 一份报告同时呈现两向误差 + 生产基线。证伪 = 若既有题集两向误差恒 0 且 near_miss 也全绿，则门内侧已饱和，D 缩为生产监测单项。

**成本与依赖**：report 扩展 + 10 条负例 + 1 个聚合脚本。

### 方向 E：产物持久化收口（机制，不是规范）

**要解决的问题**：`.omx/` 在 `.git/info/exclude`（机器本地、协作者不可见、克隆即无）；`.claude/` 在 `.gitignore:143`；新写入被静默忽略，而 HEAD 已有 356 个 `.omx/` 文件靠历史强制入库幸存【实测】。R3/R4 prereg 本轮靠 `git add -f` 抢救。requirements R2 已把这条写成硬教训：「账本位于 gitignored 路径等于没有账本」。

**提案（三件）**：
1. 把边界搬进仓库可见的 `.gitignore`：删除 `.git/info/exclude` 的 `.omx/` 行，改为显式规则——忽略 `.omx/tmp/`、`.omx/scratch/` 等短命目录，**默认跟踪** `.omx/artifacts/`。效果：新 artifact 出现在 `git status`，「我以为记录了」从静默丢失变成显式决策。
2. 断链守卫：脚本扫描 tracked 文档（ROADMAP/specs）对 `.omx/artifacts/*` 的引用（如 ROADMAP:5 引用 next-opt-design-v1.md），核对被引用文件在 `git ls-files` 中；不在 → 红灯。防止引用一个换机器即消失的文件。
3. `.claude/` 拆分：跟踪 `settings.json` 与 `skills/`，继续忽略 `settings.local.json`。

**分类依据**：承载决策证据的（prereg / 标定报告 / 评审结论 / 基线 / R3 的原始产出留档）→ 跟踪；scratch/tmp → 忽略。原则：凡被 tracked 文档引用或作为验收证据的，必须在 tracked 路径。

**成功判据 / 证伪**：成功 = 改完后 fresh clone + 断链守卫全绿；单测里人为 untrack 一个被引用文件 → 守卫红灯。证伪 = 若默认跟踪导致仓库膨胀不可接受（如单个 artifact > 5MB 且高频新增），退回「显式 add -f + 断链守卫」折中，把静默丢失交给守卫兜底。

**成本与依赖**：gitignore 改写 + 1 脚本 + 定向测试，小时级。是 R1 账本、R3 留档、A 的画像产物的共同前置。

**与 E1–E4**：无直接关系；是全部 R 系与 A 的落地前提。

## 4. 优先级与理由

**E → D → C → A → B**（E/D/C 可并行）。

- **E 先行**：最便宜（小时级），且是其他一切产物的落地前提——账本纪律已有条文，缺的只是机制。
- **D 次之**：零模型成本，解锁 E1 的判据框架；「找不到匹配是成功」从口号变数字。
- **C 第三**：零模型成本，直接回答标题问题（重复伪影占比），并决定 R2 标注投资的先后。
- **A 第四**：需重复路由跑动（中等成本）；是 E1 的方差基线前置，依赖 E 的产物落点。
- **B 最后**：主要成本是流程设计 + 维护者逐 job 认定（人际确认），不阻塞任何线。
- **必须等人的**：B1 的 decision_source 逐 job 认定；A 的单线程确定性假设由控制组判决后才解释语义层数字。
- **与在途工作的边界**：R3/R4 按 prereg + 交接任务书执行，本提案不改其判据与范围；D 与 R3 是两层两指标，不吞并。

## 5. 不做什么，以及为什么

1. **不做语义层门禁或阈值化**：违反 ROADMAP:35 禁令；研究结论判定其不可判定；report-only 是既有先例（routing-benchmark.md:4–7）。
2. **不做常驻默认注入、不扩编排/市场/专家团/协同过滤/主动推荐**：next-opt-design L2/L3/L5 与 ROADMAP 冻结清单。
3. **不把 C 的观察性结论当因果**：模型组合非随机分配（混杂已声明）。
4. **不为 C 新跑任何模型**：C 的全部价值就在零成本回溯；要跑新的属于 R1（N=40 轮）的事。
5. **不动 R3/R4 在途判据与范围**：prereg 已写死（「跑完不得改判据」）。
6. **不做整机「设计院→施工队」**：L4 明确 E4 没绿禁止。
7. **不自动调参**：severity/佐证/去重阈值均人工所有（R 系约束沿用）。
8. **不为叙事跑墙钟时间对比**：ROADMAP:35。

## 6. 我们不知道什么

| # | 未验证前提 | 影响哪个方向 | 最小验证代价 |
|---|---|---|---|
| 1 | 语义层在固定输入下的实际方差 | A | 控制组 + N=10 单题集先跑（1 次会话） |
| 2 | CPU embedding 单线程是否运行间确定 | A | 同 commit 双跑逐条对比 primary 序列 |
| 3 | gate 全库标签可解析率（抽查 2 份不能外推） | C | 10 文件人工对答案 pilot |
| 4 | 生产 no-match 基线率 | D | 聚合脚本跑一个窗口 |
| 5 | near_miss 负例的拒判表现 | D | 构造 ≥10 条后即知 |
| 6 | CI job 集漂移速率（决定 B1 维护成本） | B | 观察 2–3 个变更 cycle |
| 7 | torch/HF 版本升级是否破坏可复现性 | A | 画像产物里记录版本，升级后复跑对比 |

## 7. 我读到但没有采纳的东西，以及原因

- **R6 指纹扩展（提示词模板纳入指纹）**：正确且已结构化，但属 R 系排队项，本提案不重复立项；A/D 的产物自带 env/版本记录，部分覆盖其动机。
- **r3-r4 交接任务书的执行细节**（/tmp MCP 路径坑、handback 格式）：执行层细节，不进设计提案。
- **verification-contract 的 verifier_skill_id / 计划交付链**：产品功能线（A–D 路已交付），与「度量可信」正交。
- **ROADMAP 指标表（4066 tests / 73% cov / P95）**：存量自述数字，本次未复跑，不基于它做任何主张。
- **routing-benchmark.md:57–59 registry.yaml 指纹过近似**：文档已声明 accepted 的保守取舍，维持。
- **L4/E4 整机假设、SkillMarket 维持项、gate38 auto-deprecate**：冻结/维持清单，本提案零接触。
- **benchmark.py 的逐行实现**：只读了函数清单（:50、:97 等）与文档口径；凡涉实现细节的主张已降级为【文档】或避开。

---

本提案未实现任何代码、未跑任何实验；所有「待测」处均无数字。下一步：人评审通过后按 §4 顺序逐项立 prereg/任务书。
