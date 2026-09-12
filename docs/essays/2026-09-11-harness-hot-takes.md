# VibeSOP Harness 说明：五条爆论，以及怎么用这个项目

> 证据来自 2026-08 至 09 的预注册 A/B、gate 循环、以及 2026-09-11 的 Linux 容器复跑。
> 凡声称「已测」的，文中标 [executed]；观察性结论不升级成因果。

本文不是功能手册。功能手册在 `docs/user/`。本文回答三句话：

1. 技能是不是真的有效？
2. 编程智能体能不能把仓库「审到收敛」？
3. 那 VibeSOP 到底什么时候该用、怎么用？

---

## 爆论 1：Skill 并不像你以为的那样有效

**流行叙事**：给 agent 一个技能库，在合适时机注入，它会明显更强。

**测过的格子** [executed，A/B R1–R6 / R7]：

| 格子 | 结果 | 可信度 |
|---|---|---|
| 好 harness + 强模型 + 方法论技能 | 四轮产物打平（含喷气发动机网页 23.5 vs 23.5） | 高，n=4 |
| 过程层 | 技能组更爱补测试、写自验；产物分数仍打平 | 中 |
| 差路由 + 技能 | 7 个不该注入的查询 5 个被硬塞，技能是负资产 | 高 |
| 弱模型 + 技能「碾压」 | 处理组 10 文件 / 对照两次零产物；但处理组 **0 次读 SKILL.md**，2/2 路由 no-match | 机制清楚，归因不能写成「技能抬升」 |
| 信息型技能（项目 runbook） | **未测**，矩阵里最后的存疑格 | — |

**假说（harness 假说）**：技能是提示词层的规范；好的 agent 运行时是结构层的规范。两者并存时，结构层赢。强模型在好 harness 里本来就会补测试、写模块，技能只是复述。

**建议**：不要用「装了技能包」当产品证明。先证明路由干净（不该注入的不注入），再谈技能内容。VibeSOP 现在把「找不到匹配」定义为成功，就是被这组实验改了口。

---

## 爆论 2：编程智能体无法收敛代码仓库质量

**流行叙事**：多审几轮、多修几轮，质量会收敛到可发布。

**测过的格子**：

- 同日四份优化计划，无共享账本（`.vibe/optimization-plan{,-p1,-p2,-auto-opt}.md`，2026-07-20）。
- gate1..45+ 轮评审，每轮都能交卷。
- 2026-09-11 零模型解析 191 个 gate 文件：310 条 finding，标题精确去重后 307，字面重复率 ~1%。这是下界。改写型伪影的上界未知。
- 需求文档把发现分成 D（可判定）/ T（可检验）/ J（主观）。J 类空间无限，「建议更优雅」没有终点。

**第一性原理**：真新发现有限；改写型伪影每轮近似常数。你看见的「永远有新 P1」，主要是后一项加上标准漂移。

**建议**：

- 机器闸只认 D/T：ruff、pytest、hermetic 路由基线、`decision_source` 守卫。
- LLM 评审标 `human`，永远不要 `continue-on-error: false`。
- 第二轮「全面诊断」如果没有账本，默认当作新的幻觉生成器。

VibeSOP 不提供「再扫描直到 0 finding」的产品。它提供「这一跳路由是否干净」的产品。

---

## 爆论 3：「找不到技能」才是合格输出

**流行叙事**：路由应该总命中点什么，空结果是失败。

**测过的格子** [executed，2026-09-11]：

- 产品命题已改口（ROADMAP）：技能是可点名方法卡，不是常驻专家编制。
- hermetic 题集：`must_not_inject` 最低集 5/5 绿；近失 14 条里 2 条仍过灌（「收工下班」→ `session-end` 0.95；`herd instinct` → `instinct` 0.50）。
- 生产 898 条 `route:` span，no-match **32.18%**，Wilson 95% **[29.21%, 35.31%]**。
- Docker 复跑：查询「今天天气怎么样」→ `has_match=false`（对）；「工地上的工人六点准时收工下班」→ 仍命中 session-end（近失，已知）。
- Docker AB（hermetic vs live `vibe route`，同一 19 条负例 + 16 条正例）[executed 2026-09-11]：最低集 5/5 两臂都不注入；近失过灌 hermetic 2 / live 1；正例命中 15/16 vs 14/16。详见 `.omx/artifacts/ab-routing-hygiene-20260911.md`。

**建议**：

| 你想做的事 | 该看到什么 | 不该做什么 |
|---|---|---|
| 闲聊 / 翻译 / 写公众号 | no-match，exit 当成功 | 不要为了「有技能」去降阈值 |
| 点名一个方法（TDD、session-end） | 命中对应 skill_id | 不要再叠一个专家团 |
| 评审合入 | 机器闸 + 人读模型意见 | 不要把模型意见写成 required job |

命令：

```bash
vibe route --json "今天天气怎么样"
# 期望 has_match=false

uv run python scripts/eval_routing.py --hermetic --check
# 期望 exit 0；这是机器闸，不是 LLM
```

---

## 爆论 4：弱模型缺的不是技能正文，是路由和脚手架

R6 [executed]：27B 双臂同模型。对照两次思考循环到死、零产物。处理组交付接近强模型分数的喷气发动机网页——但路由 2/2 no-match，SKILL.md 读取 0。

多出来的东西是：`~/.grok/rules/routing.md`、技能目录的存在、`vibe` CLI、一次结构化的 Routing Decision Report。这些是 **harness**，不是卡片正文。

另外：处理组的路由模型曾经静默 404 回退，表面一切正常。没有「处理是否发生」的三验，我们会写出完全反了的论文。

**建议**：小模型场景先测「命中/拒判」，不要测「成品质量」。Roadmap W2-E1 就是这个实验，还没做。在那之前，不要宣称 VibeSOP 能让 27B 打过 Claude。

---

## 爆论 5：评测仪器比模型更会说谎

- 墙钟时间四轮方向乱跳，正式撤回「技能有时间成本」。
- WebGen 配对方案被五路独立评审 5/5 否决：n 太小、捆包处理无法归因、没有失败状态。
- 语义层在 CI 里长期不可见；本机 N=10 画像稳定度 1.0——不是「随机」，是「没测」。
- Wilson 下界在 Linux 上是 `2e-17` 不是 `0.0`，macOS 碰巧是 0。Docker 端到端才看见。仪器也要跨机器。
- `enable_embedding=True` 时 `LazyEmbeddingMatcher` 不接 `top_k`，产品路径 TypeError。画像能跑是因为 harness 做了适配器。没仪器会把它当「语义层很稳」。

**建议**：预注册、有效性三验、跨机器复跑。VibeSOP 自己的 hermetic 六步（cwd/HOME/pin 宇宙/关 embedding/关 triage/空 SCENARIO）就是把仪器从宿主里拔出来。

```bash
# 仪器自检，不是「模型测分」
uv run python scripts/eval_routing.py --hermetic --check
uv run python scripts/check_ci_decision_source.py
uv run python scripts/check_artifact_links.py
uv run python scripts/aggregate_nomatch.py --spans .vibe/observability/spans.jsonl
```

---

## 按场景使用 VibeSOP

| 场景 | 用 | 不用 |
|---|---|---|
| Claude / Grok / Kimi / Pi 日常编码 | `vibe build --platform …` 装路由 hook；让 no-match 发生 | 不要开角色词自动专家团（已撤回） |
| 合入前 | hermetic check + pytest + decision-source 守卫 | 不要加「LLM 评审通过才能 merge」 |
| 怀疑路由乱灌 | 跑 `must_not_inject` / 自己的近失句；看 `has_match` | 不要靠墙钟或「感觉变聪明了」 |
| 弱模型 / 本地 27B | 先看 route 日志是不是真命中；命中再谈技能 | 不要拿成品质量当技能效果 |
| 项目私有约束、runbook | **这是尚未用 A/B 证实的价值格**；可以当信息卡点名 | 不要承诺「装了就涨分」 |
| 再做一轮「全面优化」 | 先打开上一轮账本 | 不要从零生成第四份 optimization-plan |

一句话：**VibeSOP 是图书管理员，不是施工队，更不是永动机质检仪。** 管理员的职业荣誉是该拒绝的时候拒绝。
