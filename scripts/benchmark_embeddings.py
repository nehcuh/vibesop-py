"""W0.C embedding mini-benchmark.

Goal: pick the best embedding model for ``vibe recall`` to recognise
"same task, different wording" across Chinese + English mixed queries.

Methodology:
- Gold standard cluster: 10 real cmspark queries about the same recurring
  screenshot-permission popup bug (extracted from .vibe/observability/spans.jsonl)
- Distractor cluster: 10 real cmspark queries on unrelated tasks
  (code review, lid sleep, /session-end, etc.)
- Metric: cosine separation
    = mean(gold-distractor cosine) - mean(within-gold cosine)
- Higher separation = better at grouping "same task" together while
  pushing "different task" apart.

Design deviation note (post-review):
- Design specified: MiniLM + bge-m3 + e5-multilingual-small
- FastEmbed has: MiniLM + bge-small-zh + multilingual-e5-LARGE (2.2GB, skip)
- Substituted: bge-base-en-v1.5 (to compare CJK-specialised vs EN-baseline)
- This still answers the core question: which strategy separates
  Chinese screenshot-permission queries best.

Output: ``docs/decisions/w0-embedding-benchmark.md`` with table + verdict.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from fastembed import TextEmbedding

# === Gold cluster (CLEAN, post-review): pure screenshot-permission-popup queries ===
# Tightened per W0 review (P1.4): dropped impure items that mixed permission with
# other concerns (post-permission 定位 issues, multi-issue queries, login-caused
# errors). Those moved to NEAR_MISS for precision stress testing.
GOLD = [
    "当前项目在chrome插件中，当执行到截图的时候，会弹窗提示 CMspark.app 需要截图权限，实际已经给了，但是还是会弹窗，然后失败",
    "测试下来，还是弹窗提示需要给 CMspark.app 授权，然后失败了",
    "插件内弹窗已经允许了，但是外面有个弹窗，提示 CMspark.app 需要权限，点击后可以看到已经给 CMspark.app 相应权限了",
    '目前验证下来，还是弹窗提示："CMspark.app"想要录制此电脑的屏幕和音频。在"系统设置"的"隐私与安全性"设置中允许此应用程序访问。',
    "现在更差了，再次弹窗说 CMspark.app 需要授权，打开后，显示已经授权了，chrome 插件内部弹窗，点击允许后，直接失败",
    "又一次出现之前反复出现的问题，chrome 插件执行过程中反复弹窗提示 CMspark.app 需要截屏权限，实际打开都已经有权限的",
    "❌ 不可恢复错误: screenshot: Screen Recording permission denied",
    "弹窗需要授权，CMspark.app 已经授权了还是失败",
]

# === Near-miss cluster (impure gold, kept for precision stress) ===
# These are screenshot-ADJACENT but not the same task: post-permission 定位 issues,
# multi-issue queries, login-caused errors. A good model should NOT cluster these
# with GOLD at threshold 0.80.
NEAR_MISS = [
    "弹窗需要授权，这是给了 CMspark.app 授权后，可以截图了，但是截图后定位似乎有问题",
    "现在有两个问题：1. 弹窗授权，需要单独点击 CMspark.app, 重启应用，是不是每次都要这么搞？",
    "登陆后现在出现下面问题：❌ 不可恢复错误: screenshot: ScreenCapture...",
]

# === Distractor cluster: 10 unrelated cmspark queries ===
DISTRACTORS = [
    "You are an independent senior code reviewer. Read the prompt file and the attached diff.",
    "Adversarially VERIFY this CMspark multi-agent design proposal. Default to skepticism.",
    "You are a senior staff engineer doing a READ-ONLY deep audit of the CMspark monorepo.",
    "有点奇怪，现在电脑合盖以后似乎不会关机，然后会异常发热",
    "WORKTREE=/Users/huchen/Projects/cmspark/.claude/worktrees/multi-agent-p0. Apply the patch.",
    "CMspark 是一个浏览器 AI Agent，包含 TinyClick 本地视觉定位（实验层 L2 候选）",
    "You must run the DUAL EXTERNAL REVIEW helper. Do not re-implement code.",
    "# 独立 Code Review 请求（Pi 替身）。你是 fresh session，没有上文。",
    "刚才意外中断了，我重新安装了 CMspark.app, 现在需要做什么？",
    "确认",  # very short unrelated
]

MODELS = [
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "BAAI/bge-small-zh-v1.5",
    "BAAI/bge-base-en-v1.5",
]


def cosine(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Row-wise cosine similarity between two equal-length matrices."""
    na = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-12)
    nb = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-12)
    return na @ nb.T


def pair_stats(gold: np.ndarray, distractor: np.ndarray) -> dict:
    """Compute separation + threshold-recall metrics for one model.

    - within_gold: cosine between every pair of gold queries (off-diagonal)
    - gold_distractor: cosine between each gold and each distractor
    - separation = gold_distractor_mean - within_gold_mean  (more negative = better)
    - recall_at_X: fraction of gold pairs whose cosine >= X
    - precision_at_X: of all (gold-gold + gold-distractor) pairs >= X, what
      fraction are gold-gold? Higher = threshold X cleanly separates clusters.
    """
    g_sim = cosine(gold, gold)
    idx = np.triu_indices(len(gold), k=1)
    within_pairs = g_sim[idx]
    cross_pairs = cosine(gold, distractor).flatten()

    sep = float(cross_pairs.mean() - within_pairs.mean())

    out: dict = {
        "within_mean": float(within_pairs.mean()),
        "within_p50": float(np.percentile(within_pairs, 50)),
        "within_p10": float(np.percentile(within_pairs, 10)),
        "cross_mean": float(cross_pairs.mean()),
        "cross_p90": float(np.percentile(cross_pairs, 90)),
        "separation": sep,
    }

    for thresh in (0.75, 0.80, 0.85, 0.90):
        gold_hits = float((within_pairs >= thresh).mean())
        distractor_hits = float((cross_pairs >= thresh).mean())
        # Precision: of all pairs >= thresh, how many are within-gold?
        total_hits = (within_pairs >= thresh).sum() + (cross_pairs >= thresh).sum()
        precision = (
            float((within_pairs >= thresh).sum() / total_hits)
            if total_hits > 0
            else 0.0
        )
        out[f"recall_at_{thresh}"] = round(gold_hits, 3)
        out[f"precision_at_{thresh}"] = round(precision, 3)
        out[f"false_positive_rate_at_{thresh}"] = round(distractor_hits, 3)

    return out


def separation(gold: np.ndarray, distractor: np.ndarray) -> tuple[float, float, float]:
    """Back-compat shim for the original 3-tuple return."""
    g_sim = cosine(gold, gold)
    idx = np.triu_indices(len(gold), k=1)
    within = g_sim[idx].mean()
    cross = cosine(gold, distractor).mean()
    return float(within), float(cross), float(cross - within)


def run() -> None:
    out: list[dict] = []
    for model_id in MODELS:
        print(f"\n=== {model_id} ===")
        print("(first run downloads weights, please wait)")
        emb = TextEmbedding(model_name=model_id)
        g = np.array(list(emb.embed(GOLD)))
        d = np.array(list(emb.embed(DISTRACTORS)))
        nm = np.array(list(emb.embed(NEAR_MISS)))
        stats = pair_stats(g, d)
        # Precision stress: how does the model treat NEAR_MISS (screenshot-adjacent
        # but different task)? Ideally cross-similar to distractors, NOT pulled
        # into the gold cluster.
        near_miss_to_gold = cosine(g, nm).flatten()
        stats["near_miss_to_gold_mean"] = float(near_miss_to_gold.mean())
        stats["near_miss_to_gold_p90"] = float(np.percentile(near_miss_to_gold, 90))
        print(f"  within-gold: mean={stats['within_mean']:.3f} p50={stats['within_p50']:.3f} p10={stats['within_p10']:.3f}")
        print(f"  cross:       mean={stats['cross_mean']:.3f} p90={stats['cross_p90']:.3f}")
        print(f"  near-miss:   mean={stats['near_miss_to_gold_mean']:.3f} p90={stats['near_miss_to_gold_p90']:.3f}")
        print(f"  separation:  {stats['separation']:+.3f}")
        print(f"  recall@0.80: {stats['recall_at_0.8']}  precision@0.80: {stats['precision_at_0.8']}")
        out.append(
            {
                "model": model_id,
                "dim": int(g.shape[1]),
                **stats,
            }
        )

    out_path = Path("docs/decisions/w0-embedding-benchmark.json")
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"\nResults written to: {out_path}")


if __name__ == "__main__":
    run()
