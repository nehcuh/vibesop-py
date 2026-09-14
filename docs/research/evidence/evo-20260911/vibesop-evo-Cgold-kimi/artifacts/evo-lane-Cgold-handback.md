# Lane Cgold Handback — 10 文件人工金标

日期：2026-09-11 · 执行：kimi（第二路）· worktree `vibesop-evo-Cgold-kimi` @ `feat/evo-Cgold`
金标文件：`.omx/artifacts/gate-findings-gold-10.json`（schema `gate-findings-gold-v1`，observational）
源文件均从主仓 `/Users/huchen/Projects/vibesop-py/.omx/artifacts/` 只读读取，未改主仓任何文件。

## 选了哪 10 个文件（满足异构要求）

| # | 文件 | gate | reviewer | 类别要求 |
|---|------|------|----------|----------|
| 1 | gate1-review-claude.md | gate1 | claude | review-claude ①（[P1]/[nit] 编号列表） |
| 2 | gate2-review-claude.md | gate2 | claude | review-claude ② |
| 3 | gate8-claude.md | gate8 | claude | 非 review- claude ①（VERDICT/NITS 代码块） |
| 4 | gate10-claude.md | gate10 | claude | 非 review- claude ② |
| 5 | gate11-claude.md | gate11 | claude | 负例（单段散文 verdict） |
| 6 | gate12-pi.md | gate12 | pi | pi ① |
| 7 | gate13-pi.md | gate13 | pi | pi ② |
| 8 | gate34-grok.md | gate34 | grok | grok（[MAJOR]/[NIT]） |
| 9 | gate34-synthesis.md | gate34 | synthesis | synthesis |
| 10 | gate10-instructions.md | gate10 | instructions | 负例（任务书，含 Verdict 模板陷阱） |

## 各抽出几条

| 文件 | parseable | findings | severity 分布 |
|------|-----------|----------|---------------|
| gate1-review-claude.md | true | 5 | P1×2, NIT×3 |
| gate2-review-claude.md | true | 3 | P1×2, NIT×1 |
| gate8-claude.md | true | 6 | NIT×6 |
| gate10-claude.md | true | 6 | NIT×6 |
| gate11-claude.md | **false** | 0 | — |
| gate12-pi.md | true | 4 | NIT×4 |
| gate13-pi.md | true | 4 | NIT×4 |
| gate34-grok.md | true | 10 | P1×4, NIT×6 |
| gate34-synthesis.md | **false** | 0 | — |
| gate10-instructions.md | **false** | 0 | — |

合计：38 条 finding（P1×8, NIT×30）；parseable=false 3 个。

## 标签体系（各文件实际用的）

- **gate1/gate2-review-claude**：`[P1]` / `[nit]` 中文编号列表；gate2 结构松（逐文件观察+「最重要发现」+专答），显式标签仅 2 处，L16「最重要发现（非阻塞但应排最前修）」无标签、按语义推为 P1（已在 notes 声明此推断）。
- **gate8/gate10-claude、gate12/gate13-pi**：英文 `VERDICT / BLOCKS / NITS / NOTES` 代码块；NITS 条目不自带 severity 词，统一映射 NIT；NOTES 段一律不算 finding。pi 文件 bullet 跨多行，line 取 bullet 起始行；pi 文件开头 L1-2 有路由 shell 报错噪声行。
- **gate34-grok**：`[MAJOR]` / `[NIT]` 列表；按规则 MAJOR→P1、NIT→NIT。

## parseable=false 的 3 个（含判断理由）

1. **gate11-claude.md**：单段散文，确实提到一个可行动项（e2e_llm_routing.py T1/T2/T4 需 retarget），但无 severity 标签、无条目结构——抽出来就得编造 severity，判 false。
2. **gate34-synthesis.md**：裁决/收敛稿。修订 A–K 引用各 lane 的 finding 编号（pi-MAJOR-1 等），条目本身是“处置”而非独立 finding，且单条混合多 severity；当 finding 抽会跨文件重复计数，判 false。
3. **gate10-instructions.md**：任务书，零 finding；L28-37 的 Verdict 格式模板（`- [severity] file:line — issue — why`）是 parser 的 false-positive 陷阱，判 false。

## 给 parser 路的提示（观察，非要求）

- 「VERDICT 代码块」家族的 NITS 条目都**没有显式 severity 词**，是否一律记 NIT 需要 parser 与金标对齐口径。
- gate2 这类半结构化评审的条目边界靠语义不靠标记，precision/recall 在这类文件上应预期较低。
- 行号语义：跨行 bullet 取起始行。

## 边界声明

这不是 parser 精确率评测（本路没有 parser），金标是「单文件人工能抽到什么」。未做跨文件去重。未编任何精确率/召回率数字。
