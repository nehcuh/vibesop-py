# W0.C — Embedding Model Mini-Benchmark

> 2026-07-29 — gates W1 model selection
> Script: `scripts/benchmark_embeddings.py`
> Raw data: `docs/decisions/w0-embedding-benchmark.json`
> **Revision**: post grok+pi review (P1.4) — gold cluster cleaned, near-miss set added

---

## TL;DR

**Winner: `paraphrase-multilingual-MiniLM-L12-v2` + threshold 0.80**

- Best separation (−0.285, improved from −0.274 after gold cleanup)
- Sweet spot at threshold 0.80: recall=0.643, precision=0.818, FPR=0.05
- Smallest (384-dim, ~120MB) and fastest of the three
- **Caveat (new)**: near-miss queries (screenshot-adjacent but different task)
  still pull toward the gold cluster (p90=0.894). Threshold 0.80 will
  absorb some near-miss items — acceptable for `vibe recall` (over-recall
  is fine, user rejects), risky for cluster purity (may need 0.85 if W1
  kill switch fails on multi-cluster validation).

**W1 design revision (in addendum §8.1)**: soft-cluster default lowered
from 0.85 → **0.80** (kill-switch tunable).

---

## Revision history

### v1 (initial W0.C)
- 10 gold queries (mixed: permission-popup + post-permission 定位 + multi-issue + login-error)
- 10 distractor queries
- Result: MiniLM sep=−0.274, bge-small-zh=−0.245, bge-base-en=−0.209
- Verdict: MiniLM wins, threshold 0.80 sweet spot
- **Reviewer feedback (P1.4)**: gold is a "family", not a clique.
  Within-gold p10 (0.479) was below cross p90 (0.728) — contamination.

### v2 (current, post-review)
- Gold tightened to **8 pure permission-popup queries** (dropped 3 impure)
- New **NEAR_MISS** set: 3 screenshot-adjacent but different-task queries
  (post-permission 定位, multi-issue, login-caused)
- Same 10 distractors
- Result: MiniLM sep=**−0.285** (better), recall@0.80 up to **0.643**
- New finding: **near-miss p90 = 0.894** — impure items semantically close

---

## Deviation from v3 design

| Spec | Actual | Reason |
|---|---|---|
| `paraphrase-multilingual-MiniLM-L12-v2` | ✓ | matches |
| `bge-m3` | `bge-small-zh-v1.5` | fastembed has no `bge-m3`; `bge-small-zh` is the CJK-specialised substitute |
| `e5-multilingual-small` | `bge-base-en-v1.5` | fastembed only has `multilingual-e5-large` (2.2GB download, skip); substituted `bge-base-en` as EN-baseline to round out the 3-way comparison |

Substitution risk noted in design addendum §8.3.

---

## Data

- **Gold cluster** (8 queries, CLEAN): pure CMspark screenshot-permission
  popup issue. Extracted from
  `/Users/huchen/Projects/cmspark/.vibe/observability/spans.jsonl`.
- **Near-miss cluster** (3 queries): screenshot-ADJACENT but different
  task — post-permission 定位 issues, multi-issue queries, login-caused
  errors. Kept to stress-test precision.
- **Distractor cluster** (10 queries): real cmspark spans on unrelated
  tasks (code review, lid sleep, /session-end, multi-agent worktree, etc.).

---

## Results (v2, clean gold)

### Separation + near-miss metrics

| Model | Dim | within mean | within p50 | within p10 | cross mean | cross p90 | near-miss mean | near-miss p90 | separation |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **MiniLM-L12-v2** | 384 | 0.760 | 0.848 | 0.421 | 0.474 | 0.733 | 0.759 | **0.894** | **−0.285** |
| bge-small-zh-v1.5 | 512 | 0.740 | 0.769 | 0.550 | 0.481 | 0.562 | 0.742 | 0.839 | −0.259 |
| bge-base-en-v1.5 | 768 | 0.848 | 0.897 | 0.626 | 0.608 | 0.785 | 0.806 | 0.929 | −0.239 |

### Threshold sweep (gold vs distractors only)

| Model | thresh | recall | precision | false-pos-rate |
|---|---:|---:|---:|---:|
| **MiniLM** | 0.75 | 0.750 | 0.778 | 0.075 |
| **MiniLM** | **0.80** | **0.643** | **0.818** | **0.050** |
| MiniLM | 0.85 | 0.464 | 1.000 | 0.000 |
| MiniLM | 0.90 | 0.179 | 1.000 | 0.000 |
| bge-small-zh | 0.75 | 0.536 | 1.000 | 0.000 |
| bge-small-zh | 0.80 | 0.429 | 1.000 | 0.000 |
| bge-small-zh | 0.85 | 0.286 | 1.000 | 0.000 |
| bge-base-en | 0.75 | 0.750 | 0.618 | 0.163 |
| bge-base-en | 0.80 | 0.750 | 0.750 | 0.087 |
| bge-base-en | 0.85 | 0.750 | 0.808 | 0.062 |

---

## Per-model verdict

### MiniLM-L12-v2 — WINNER

- Best separation (-0.285, improved from v1 after gold cleanup).
- **Threshold 0.80 = sweet spot** for `vibe recall`: 64% recall, 82% precision.
- **New concern**: near-miss p90=0.894 means screenshot-adjacent queries
  will be absorbed into the gold cluster at threshold 0.80. For `vibe
  recall` this is acceptable (over-recall lets the user reject); for
  cluster purity it's a risk. W1 should monitor this — if multi-cluster
  validation fails, raise threshold to 0.85 (kills near-miss absorption
  but cuts recall to 0.464).
- Smallest (384-dim) → fastest embedding + cosine, smallest cache.

### bge-small-zh-v1.5

- Cleanest distractor separation (cross p90 = 0.562, very tight).
- But within-gold p50 = 0.769 — model sees same-task queries as less
  similar than MiniLM. Clusters too loosely.
- At threshold 0.85, recall collapses to 0.286. Useless for our case.

### bge-base-en-v1.5

- Tightest within-gold cluster (p50 = 0.897).
- But English-trained model generalises sloppily to mixed CJK/EN — pulls
  distractors in too (cross p90 = 0.785, near-miss p90 = 0.929).
- Larger (768-dim) → slower + bigger cache. No upside over MiniLM.

---

## Implications for W1

1. **Use MiniLM-L12-v2** as the embedding model.
2. **Soft-cluster threshold: 0.80** (kill-switch tunable, retry allowed
   per v3 design §5).
3. **Multi-cluster validation is the real W1 risk**: this benchmark only
   tests one gold family. W1 must validate ≥2 clusters (screenshot-permission
   + lid-sleep + optionally one more) before declaring the approach works.
4. **Near-miss absorption is a known trade-off**: at threshold 0.80, some
   screenshot-adjacent queries will pollute the gold cluster. Watch this
   in W1 evaluation. If precision collapses on second cluster, raise θ.
5. **Cache by** `hash("minilm-l12-v2" + normalize(query))` — model_id in
   the cache key so future model swaps invalidate gracefully.

---

## Open risks (deferred to W1 evaluation)

- **Single distractor cluster** — 10 unrelated cmspark queries, but not
  tested against queries from completely different domains.
- **Sample size** — 8 gold + 3 near-miss + 10 distractor = 21 total.
  W1 should re-test with the full ~20 screenshot-permission queries
  observed in real cmspark data + a second gold cluster.
- **No cross-language test** — didn't include English paraphrases of the
  Chinese screenshot queries. MiniLM's multilingual training *should*
  handle it, but untested.
- **Near-miss behavior at threshold 0.80** — will absorb some adjacent
  queries. Acceptable for `vibe recall`; risky for cluster purity.
  W1 evaluation must check both.
