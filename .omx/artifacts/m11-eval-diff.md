# M11 实施验证：eval diff（生产代码实跑）

> 日期：2026-08-20  实施：按 `.omx/artifacts/m11-design-a.md`（设计 A v5）
> 命令：
> - `uv run python scripts/eval_routing.py --file tests/benchmark/routing_eval.yaml --json-out /tmp/m11-after-base.json`
> - `uv run python scripts/eval_routing.py --file tests/benchmark/routing_eval_oneshot.yaml --json-out /tmp/m11-after-oneshot.json`
> - `uv run python scripts/eval_routing.py --file tests/benchmark/routing_eval_extended.yaml --json-out /tmp/m11-after.json`

## 三集成绩（before → after）

| 集合 | before | after | Δ |
|---|---|---|---|
| base (routing_eval.yaml) | 31/34 | **31/34** | 0 |
| oneshot (routing_eval_oneshot.yaml) | 10/11 | **10/11** | 0 |
| extended (routing_eval_extended.yaml) | 81/107 (75.7%) | **98/107 (91.6%)** | **+17** |

逐 query diff（/tmp/m11-baseline.json vs /tmp/m11-after.json，按 ok1 判定）：

- **FIX (error → OK)：17 条**，全部落到 fallback_llm（干净弃权），无任何 OK → BAD。
- **OK → BAD：0 条。**

修复明细（基线 error 索引 → 误中 → 机制）：

| # | 原误中 | 原层:分 | 机制 |
|---|---|---|---|
| 1 | superpowers/finishing-a-development-branch | keyword 0.67 | 无锚点封顶 0.25 |
| 4 | superpowers/receiving-code-review | keyword 0.89 | 唯一锚点 "not" 被停用词排除 |
| 5 | mattpocock/prototype | keyword 0.65 | 无锚点（type w=0.72<0.78） |
| 6 | omx/review | tfidf 0.75 | TFIDF 锚点闸门 |
| 7 | kimi-gated-fix | keyword 0.92 | 单锚点 + cov 0.13 门控 |
| 10 | kimi-gated-fix | keyword 0.67 | 同上（nk 锚点仅 1） |
| 12 | kimi-gated-fix | keyword 0.98 | cov 0.04 门控 |
| 13 | mattpocock/grill-with-docs | keyword 0.68 | with/to 停用词，无锚点 |
| 15 | superpowers/verification-before-completion | keyword 0.65 | 无锚点 + cov 0.05 |
| 16 | omx/code-review | keyword 0.63 | 无锚点（code w=0.52） |
| 17 | mattpocock/improve-codebase-architecture | keyword 0.63 | 无锚点 |
| 18 | ui-ux-pro-max-skill/design | keyword 0.82 | name 守卫 + 无锚点 |
| 19 | superpowers/receiving-code-review | keyword 0.63 | 无锚点 |
| 22 | ui-ux-pro-max-skill/design | keyword 0.90 | 同 18 |
| 23 | builtin/deep-diagnosis-optimization | keyword 0.64 | 单锚点 + cov 门控 |
| 24 | mattpocock/setup-pre-commit | tfidf 0.63 | TFIDF 锚点闸门（commit w=0.72<0.78） |
| 25 | builtin/skill-craft | keyword 0.70 | 2 锚点但 cov 0.049 < 0.08 地板 |

## 残余 9 条（均不在本次机制射程内）

| query 摘要 | 层 | 说明 |
|---|---|---|
| 会议只能通过 / 输入 meeting… | scenario | scenario 固定 0.9 regex，未动 |
| docs reorg Phase 1… | scenario | 同上 |
| A -> 可以打开微信… | scenario | 同上 |
| 删掉 mission-pack-p0 worktree… | fallback_llm | 假阴性（召回问题，非评分） |
| 首先我需要你使用 fanout… | fallback_llm | 假阴性 |
| 清 worktree/stash | fallback_llm | 假阴性 |
| 走一遍 dual-review 对 diff 再 | semantic_index | M10 trusted-floor 边界 |
| ❌ 安全阻断: Security Block… | semantic_index | 同上 |
| 根据评审意见，使用 workflow…（E21） | fallback_llm | baseline 即错（假阴性）；设计阶段曾预警多锚点豁免可能把它变误接，**实测生产代码中它仍是弃权（fallback_llm），误接未发生** |

## base/oneshot 正例核验

base 3 条 miss 与基线完全一致（2× deep-diagnosis→fuck-my-shit-mountain scenario 误中、1× experience-evolution→fallback）；oneshot 唯一 miss（oneshot_spec_heldout）不变。9 条走 matcher pipeline 的 keyword 正例全部存活（0.69-1.00），见设计文档 §5。

## gate14 复审修复后复验（2026-08-20，第二轮）

修复内容：ANCHOR_STOPWORDS 扩表（BLOCK-1）、find_anchors 拉丁词界、sorted query_lower、TFIDF fit 守卫、warm_up 显式重置、eps 守卫（明细见 m11-design-a.md 附录 B）。

- base 31/34、oneshot 10/11、extended **98/107**（/tmp/m11-g14-{base,oneshot,extended}.json）
- 对 /tmp/m11-baseline.json 逐 query diff：**17 修 / 0 回归**（与第一轮相同）
- 对 gate14 前 M11 结果（/tmp/m11-after-{base,oneshot}.json）逐 query diff：**零差异**
- pi BLOCK 复现 query "get this working on the new branch before the deadline"：修复前 warm 态对 grill-me 0.343 → 修复后 **0.25**（< 0.3），端到端 fallback
- REF 带全机制复跑（/tmp/m11_refband.py，生产代码）：REF ∈ {0.4,0.45,0.5,0.55,0.6} → extended 全档 98/107

## gate14b 复审修复后复验（2026-08-20，第三轮）

修复内容：ANCHOR_STOPWORDS 补全剩余虚词类（as/like/together/fully/today/despite 等 50+ 词，superset 属性由测试钉死）+ **停用词不参与任何证据累积**（anchor/bonus/coverage 分子分母全排除，strategies.py `_score_evidence`）+ claude 3 nits（substring_bonus 注释、rewarm 测试断言收紧、TFIDF warm_up([]) 显式重置）。

- base 31/34、oneshot 10/11、extended **98/107**（/tmp/m11c-{base,oneshot,ext}.json）
- 对 /tmp/m11-baseline.json 逐 query diff：**17 修 / 0 OK→BAD**（与第一、二轮相同）
- pi gate14b 复现 query：
  - "can you together update today before friday" → 修复后 matcher 层无结果（弃权）✅
  - "can you together update the website before friday" → 0.706 → **0.408**（残余由内容词 "website" 锚点支撑——它是该技能的策展 keyword，且 query 字面要求"update the website"，语义相邻，判定为可辩护路由而非虚词泄漏；虚词类（can/together/before/friday）已零贡献）
  - "get this working on the new branch before the deadline" → 无结果（弃权）✅
