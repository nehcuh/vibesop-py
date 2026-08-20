#!/usr/bin/env python3
"""Calibration for the M12 Discovery miss-clustering cosine threshold.

M12 design (``.omx/artifacts/m12-product-design.md``, 阈值哲学): the Union-Find
soft-merge threshold starts at 0.82 **to be calibrated** — 0.80 was calibrated
for gold-cluster nearest-neighbor matching; miss-vs-miss is a different
distribution. This script follows the M11 calibration discipline
(``scripts/calibrate_index_threshold.py`` / ``bigram-threshold-calibration.md``):
report distributions and a decision *band*, never a bare point estimate, and
record the blade pairs that sit closest to the boundary.

Data
----
1. Real miss pool: extracted live from ``.vibe/observability/spans.jsonl``
   (route spans, ``has_match is False``, ``mode != not_intercepted`` excluded,
   has_match missing treated as unknown → excluded). Pool size and the pool's
   own pairwise cosine spread are reported as secondary evidence.
2. Labeled pair set (baked in below, SCRUBBED paraphrases — no paths, URLs,
   project names, or conversation IDs from the dogfood history): pairs drawn
   from the real miss pool, low-confidence/weak-layer hits, and the extended
   eval set's ``expect=[]`` queries. Label convention:
   ``cluster``  = same workflow intent — if one became a skill, the other
                  should route to it;
   ``separate`` = different workflow intent — must NOT merge into one
                  discovery cluster.

Usage:
    uv run python scripts/calibrate_discovery_threshold.py
    uv run python scripts/calibrate_discovery_threshold.py --spans .vibe/observability/spans.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from vibesop.core.observability.embedding import EmbeddingCache

# --- Labeled pair set (scrubbed paraphrases; see module docstring) ----------
# Tuple shape: (query_a, query_b, label, note).

LABELED_PAIRS: list[tuple[str, str, str, str]] = [
    # --- should cluster (20) ---
    ("现在进展如何？", "我们现阶段状态如何？", "cluster", "progress-check paraphrase"),
    ("我们现阶段状态如何？", "检查下当前项目进展", "cluster", "progress-check paraphrase"),
    ("项目当前进展如何？", "当前项目整体进展如何了？", "cluster", "progress-check paraphrase"),
    ("现在进展如何？", "当前进展如何，还有未完成工作么？", "cluster", "progress-check paraphrase"),
    (
        "现在回归的情况如何了？",
        "检查下当前项目进展",
        "cluster",
        "progress status vs regression status",
    ),
    ("帮我合并到 main 吧", "帮我合并到主分支吧", "cluster", "merge-to-main paraphrase"),
    ("帮我合并到主分支吧", "然后帮我合并到主分支吧", "cluster", "merge-to-main near-duplicate"),
    (
        "帮我合并到 main 吧",
        "CI 绿了以后帮我合并到 main",
        "cluster",
        "merge-to-main with precondition",
    ),
    (
        "然后帮我合并到主分支吧",
        "创建并打开 PR，没问题就帮我合并到 main",
        "cluster",
        "merge-to-main with PR step",
    ),
    ("做一轮 dual-review", "先让 pi 和 claude 进行双路复审", "cluster", "dual-review zh/en mix"),
    (
        "先让 pi 和 claude 进行双路复审",
        "使用 Claude + Pi 的双路评审",
        "cluster",
        "dual-review paraphrase",
    ),
    (
        "让 grok 和 pi 进行复审",
        "做一轮 dual-review",
        "cluster",
        "dual-review, different reviewer pair",
    ),
    ("帮我 push 吧", "push到远程", "cluster", "git push paraphrase"),
    ("push到远程", "保存并提交远程", "cluster", "git push paraphrase"),
    (
        "当前代码是否保存并提交远程了？",
        "保存并提交远程",
        "cluster",
        "blade: interrogative vs imperative, same git-sync intent",
    ),
    ("清理吧", "帮我把备份的旧文件都清理了吧", "cluster", "cleanup terse vs explicit"),
    (
        "把最近踩过的坑沉淀下来，以后别再犯了",
        "accumulate what we learned from practice into project knowledge",
        "cluster",
        "blade: bilingual experience-distillation",
    ),
    ("全面审查这个仓库的代码质量", "来一次全维度代码库审计", "cluster", "repo-audit paraphrase"),
    (
        "我们在文档中是否说明了这些？",
        "当前项目的文档是否更新了？",
        "cluster",
        "docs-status question",
    ),
    (
        "帮我洞察下 ../other-project 项目呢？",
        "我的意思是帮我在 ../other-project 这个项目应用我们最新的修改，方便后续洞察",
        "cluster",
        "blade: real miss + its in-session clarification",
    ),
    # --- should NOT cluster (28) ---
    ("可以", "继续", "separate", "degenerate continuation tokens, no clusterable intent"),
    ("可以", "全量 import 吧", "separate", "continuation token vs real intent"),
    (
        "继续",
        "继续按照之前的流程，把所有其他工作都完成",
        "separate",
        "blade: bare token vs substantive continue-instruction",
    ),
    (
        "我发现有个开源项目似乎做了和我们产品 dashboard 和 loop 相关的内容和思考？",
        "帮我洞察下 ../other-project 项目呢？",
        "separate",
        "competitive observation vs apply-to-other-project",
    ),
    ("帮我写一个贪吃蛇单页游戏的任务书", "帮我合并到 main 吧", "separate", "unrelated domains"),
    ("现在进展如何？", "帮我合并到 main 吧", "separate", "progress vs merge"),
    ("项目当前进展如何？", "push到远程", "separate", "progress vs push"),
    (
        "CI 绿了以后帮我合并到 main",
        "先让 pi 和 claude 进行双路复审",
        "separate",
        "merge vs dual-review",
    ),
    (
        "做一轮 dual-review",
        "拉取最新变更并进行评审",
        "separate",
        "blade: adversarial dual review vs pull-and-review",
    ),
    (
        "帮我 commit 并发起 PR",
        "帮我合并到 main 吧",
        "separate",
        "blade: publish stages — open PR vs merge",
    ),
    ("保存并提交远程", "帮我合并到 main 吧", "separate", "push vs merge"),
    ("按批次拆 commit", "保存并提交远程", "separate", "commit-splitting vs push"),
    (
        "让 agent 自主运行一组实验并汇报评估结果",
        "把这段对话提炼成一个新技能",
        "separate",
        "experiment vs skill-craft",
    ),
    ("收工了", "清理吧", "separate", "session-end vs cleanup"),
    ("vibe 这个工具怎么用", "帮我安装一个技能包", "separate", "usage help vs install"),
    (
        "列出所有可用技能",
        "帮我安装一个技能包",
        "separate",
        "blade: both skill-mgmt — list vs install",
    ),
    ("评估一下这些技能的使用质量和效果", "列出所有可用技能", "separate", "evaluate vs list skills"),
    (
        "这个 bug 在 router.py 第 123 行，修复它并验证",
        "验证这个 prompt chain 各阶段是否符合规范",
        "separate",
        "fix-and-verify vs validate-chain",
    ),
    (
        "show my coding instincts and their confidence",
        "评估一下这些技能的使用质量和效果",
        "separate",
        "instinct introspection vs skill quality",
    ),
    ("全量 import 吧", "帮我重新编译并替换当前运行的程序吧", "separate", "import vs rebuild"),
    (
        "review and commit",
        "帮我 commit 并发起 PR",
        "separate",
        "blade: cross-lingual adjacent publish workflow",
    ),
    (
        "帮我找找中文视觉模型，记得有几家大厂都开源了不少视觉小模型",
        "全面审查这个仓库的代码质量",
        "separate",
        "model research vs code audit",
    ),
    ("我们在文档中是否说明了这些？", "检查下当前项目进展", "separate", "docs vs progress"),
    (
        "我的意思是帮我在 ../other-project 这个项目应用我们最新的修改，方便后续洞察",
        "帮我重新编译并替换当前运行的程序吧",
        "separate",
        "apply-to-other-project vs rebuild",
    ),
    (
        "我发现有个开源项目似乎做了和我们产品 dashboard 和 loop 相关的内容和思考？",
        "帮我找找中文视觉模型，记得有几家大厂都开源了不少视觉小模型",
        "separate",
        "both research-flavored, different objects",
    ),
    (
        "全面审查这个仓库的代码质量",
        "审计一下第三方依赖的供应链安全",
        "separate",
        "blade: audit scope — code quality vs supply-chain security",
    ),
    (
        "把最近踩过的坑沉淀下来，以后别再犯了",
        "把这段对话提炼成一个新技能",
        "separate",
        "blade: learning outputs — knowledge vs skill",
    ),
    ("vibe 这个工具怎么用", "列出所有可用技能", "separate", "help vs list"),
]


def _extract_real_miss_queries(spans_path: Path) -> list[str]:
    """Distinct queries from route spans with has_match is False.

    Mirrors the M12 miss rule: ``mode == "not_intercepted"`` spans (no
    has_match key anyway) are excluded; spans without has_match are unknown
    and stay out of the pool (conservative direction).
    """
    queries: list[str] = []
    seen: set[str] = set()
    if not spans_path.exists():
        return queries
    with spans_path.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                span = json.loads(line)
            except json.JSONDecodeError:
                continue
            name = span.get("name", "")
            if not name.startswith("route:"):
                continue
            md = span.get("metadata") or {}
            if isinstance(md, str):
                try:
                    md = json.loads(md)
                except json.JSONDecodeError:
                    md = {}
            if md.get("has_match") is not False:
                continue
            if md.get("mode") == "not_intercepted":
                continue
            query = md.get("query") or name.removeprefix("route:").strip()
            if query and query not in seen:
                seen.add(query)
                queries.append(query)
    return queries


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


def _quantiles(values: list[float]) -> str:
    arr = np.asarray(values)
    qs = np.percentile(arr, [0, 25, 50, 75, 100])
    return "min={:.3f} p25={:.3f} median={:.3f} p75={:.3f} max={:.3f}".format(*qs)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spans", default=".vibe/observability/spans.jsonl")
    parser.add_argument("--cache-path", default=".vibe/cache/embeddings.npz")
    args = parser.parse_args()

    cache = EmbeddingCache(cache_path=args.cache_path)
    probe = cache.embed("embedding smoke probe")
    if probe is None:
        print(
            "FATAL: embed() returned None — fastembed/model unavailable; "
            "refusing to calibrate on an empty signal.",
            file=sys.stderr,
        )
        return 1

    # --- real miss pool (secondary evidence) ---
    pool = _extract_real_miss_queries(Path(args.spans))
    print(
        f"## real miss pool: {len(pool)} distinct queries "
        f"(has_match=False, not_intercepted excluded)"
    )
    pool_vecs = cache.embed_batch(pool) if pool else []
    pool_pairs: list[tuple[str, str, float]] = []
    for i in range(len(pool)):
        for j in range(i + 1, len(pool)):
            vi, vj = pool_vecs[i], pool_vecs[j]
            if vi is None or vj is None:
                continue
            pool_pairs.append((pool[i], pool[j], _cosine(vi, vj)))
    if pool_pairs:
        scores = [s for _, _, s in pool_pairs]
        print(f"pool self-pairs: {len(pool_pairs)}  {_quantiles(scores)}")
        for a, b, s in sorted(pool_pairs, key=lambda p: -p[2]):
            print(f"  {s:.3f}  {a[:40]!r} × {b[:40]!r}")
    else:
        print("pool self-pairs: <2 queries — no pool-internal distribution.")

    # --- labeled pairs ---
    texts = sorted({q for pair in LABELED_PAIRS for q in pair[:2]})
    vecs = dict(zip(texts, cache.embed_batch(texts), strict=True))
    missing = [t for t, v in vecs.items() if v is None]
    if missing:
        print(f"FATAL: {len(missing)} queries failed to embed.", file=sys.stderr)
        return 1

    scored: list[tuple[str, str, str, str, float]] = []
    for a, b, label, note in LABELED_PAIRS:
        scored.append((a, b, label, note, _cosine(vecs[a], vecs[b])))

    cluster = sorted((s for s in scored if s[2] == "cluster"), key=lambda p: p[4])
    separate = sorted((s for s in scored if s[2] == "separate"), key=lambda p: -p[4])
    print(f"\n## labeled pairs: {len(scored)} (cluster={len(cluster)}, separate={len(separate)})")
    print(f"cluster  cosines: {_quantiles([p[4] for p in cluster])}")
    print(f"separate cosines: {_quantiles([p[4] for p in separate])}")

    # --- decision band scan ---
    print("\n## threshold scan (errors = separate≥t false-merges + cluster<t false-splits)")
    print("| threshold | false-merges | false-splits | total errors |")
    print("|---|---|---|---|")
    best_err, band = None, []
    for t_bp in range(30, 96):
        t = t_bp / 100
        fm = sum(1 for p in separate if p[4] >= t)
        fs = sum(1 for p in cluster if p[4] < t)
        err = fm + fs
        print(f"| {t:.2f} | {fm} | {fs} | {err} |")
        if best_err is None or err < best_err:
            best_err, band = err, [t]
        elif err == best_err:
            band.append(t)
    print(f"\ndecision band (min errors = {best_err}): {band[0]:.2f} .. {band[-1]:.2f}")

    # --- blade pairs ---
    print("\n## blade pairs (closest to the boundary)")
    lo_cluster = cluster[0]
    hi_separate = separate[0]
    print(f"lowest cluster pair:  {lo_cluster[4]:.3f}  {lo_cluster[0]!r} × {lo_cluster[1]!r}")
    print(f"  note: {lo_cluster[3]}")
    print(f"highest separate pair: {hi_separate[4]:.3f}  {hi_separate[0]!r} × {hi_separate[1]!r}")
    print(f"  note: {hi_separate[3]}")
    if band:
        edge = [p for p in scored if band[0] - 0.05 <= p[4] <= band[-1] + 0.05]
        if edge:
            print("\nall pairs within ±0.05 of the band:")
            for a, b, label, note, s in sorted(edge, key=lambda p: p[4]):
                mark = "OK " if (label == "cluster") == (s >= band[0]) else "ERR"
                print(f"  [{mark}] {s:.3f} {label:8s} {a!r} × {b!r}  ({note})")

    # --- full dump for the artifact ---
    print("\n## full pair dump (sorted by cosine)")
    for a, b, label, note, s in sorted(scored, key=lambda p: -p[4]):
        print(f"{s:.3f}  {label:8s}  {a!r} × {b!r}  ({note})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
