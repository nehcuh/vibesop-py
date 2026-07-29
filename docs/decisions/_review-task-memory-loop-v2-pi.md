# pi Review v2: Task-Anchored Memory（复审）

> 评审时间：2026-07-29
> 模式：pi -nt -p < brief（stdin redirect, no tools）

## Q1 — task_id 派生函数

**P0** · `project_path` 作盐使同一 query 在不同项目算出不同 task_id，直接摧毁 v2 的核心卖点「跨项目 cluster」（同一问题永远聚不到一起）。
→ 替代：以 `hash(normalize(query))` 作基础锚点，`project_path` 仅用作可选的命名空间前缀。

## Q2 — Embedding 模型选择

**P1** · paraphrase-multilingual-MiniLM 的中文问题描述质量未经验证，而 Finding 3 已证明该领域对语义模型有硬要求。好在 W1 kill switch 用真实 cluster 验证了该模型，风险已被控制，但模型一旦选错返工成本不小。
→ 替代：W0 先跑 3 个候选模型的 mini-benchmark（截图权限 cluster 10 条 query），选定后进入 W1。

## Q3 — 跨项目 scope

**P0（安全） + P1（语义）** · 跨项目读取 `~/.vibe/observability/spans.jsonl` 将项目 A 的 span 数据暴露给项目 B 的 recall 结果，商业敏感信息无隔离；同一 "部署问题" 在不同项目解法截然相反，合并 cluster 会给出错误 cue。MVP 阶段无必要冒这一双重风险。
→ 替代：MVP 只做单项目；或跨项目限定于同一 org/repo family 的白名单。

## Q4 — dev/prod 隔离机制

**P1** · 环境变量依赖人工记忆，开发者 `pytest` 忘记设 → 测试 `spans` 污染 prod → 聚类质量劣化。自动检测（检测 pytest runner、`PYTEST_CURRENT_TEST`）比 env var 健壮得多，且实现成本极低。
→ 替代：`is_dev = ("PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.argv[0])`，自动路由。

## Q5 — kill switch 单一 cluster 验证

**P1** · `cmspark 截图权限 cluster ≥10 query` 是好的方向（把模型选择从信仰变成数据驱动），但单一硬性规则的问题：(a) 聚类边界模糊时判据不明确，(b) 聚多了不相关 query（高召回低精度）仍算通过，(c) 模型一次随机性波动可能误杀整个方向。
→ 替代：至少 2 个以上真实 cluster + 人工抽检 5 条看 precision；同时设「连续 2 周不达标才 kill」。

## 最严的新风险（开放题）

**跨项目数据合并模型** — Q1 的 task_id 盐冲突 + Q3 的语义污染叠加：同一 query 跨项目算出不同 anchor → 「跨项目能找到同类问题」的承诺从设计根子上就不可实现，v2 最高层级的差异化主张是虚假的。若带着这个设计进入开发，W0–W2 的全部跨项目工作在架构上即为无效工程。此风险的严重程度超过任何单一技术选择问题。
