#!/usr/bin/env python3
"""Measure the INDEX-layer embedding score/margin shift between two index
snapshots (gate32 MAJOR: A2 added ``triggers`` to ``_compute_profile_text``,
which moves the 0.45-door input text for EVERY skill — "可以不改阈值,
不能不测" per grok M2/M5, pi BLOCK-3, claude NIT-5).

Loads two index files (e.g. pre-A2 and post-A2 snapshots of
``~/.vibe/skill-index.json``), encodes the routing eval queries with the
SAME model the indexer uses (``paraphrase-multilingual-MiniLM-L12-v2`` via
sentence-transformers), and reports for each snapshot:

- top-1 cosine score distribution (min/median/mean/max) over all queries
- margin (top1 - top2) distribution — the fragile gate is
  ``index_embedding_min_margin`` (calibration record: sole passing entry
  margin 0.071 vs nearest noise 0.0702)
- per-positive (expect non-empty) top-1 score + margin before→after
- flips at the production threshold (0.45): hit→miss, miss→hit, and
  top-1 identity changes (A→B re-routes — claude NIT-5's "大概率" event)

Usage:
    uv run python scripts/measure_index_embedding_shift.py \
        --before /tmp/gate32-global-index-before.json \
        --after ~/.vibe/skill-index.json

Read-only against both files. No LLM calls.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

import yaml

EVAL_FILES = [
    Path("tests/benchmark/routing_eval.yaml"),
    Path("tests/benchmark/routing_eval_extended.yaml"),
]
PROD_THRESHOLD = 0.45
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def _load_index(path: Path) -> dict[str, list[float]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for sid, profile in data.get("skills", {}).items():
        emb = profile.get("embedding")
        if emb:
            out[sid] = emb
    return out


def _load_queries() -> list[dict]:
    entries: list[dict] = []
    for path in EVAL_FILES:
        if path.exists():
            entries.extend(yaml.safe_load(path.read_text(encoding="utf-8")) or [])
    return entries


def _score_all(query_vec: list[float], index: dict[str, list[float]]) -> list[tuple[str, float]]:
    scores = [(sid, _cosine(query_vec, emb)) for sid, emb in index.items()]
    scores.sort(key=lambda kv: kv[1], reverse=True)
    return scores


def _dist(values: list[float]) -> dict[str, float]:
    return {
        "min": round(min(values), 4),
        "median": round(statistics.median(values), 4),
        "mean": round(statistics.mean(values), 4),
        "max": round(max(values), 4),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    before = _load_index(args.before)
    after = _load_index(args.after)
    if not before or not after:
        print("ERROR: one of the indexes has no embeddings", file=sys.stderr)
        return 1
    print(f"index sizes: before={len(before)} after={len(after)}")

    queries = _load_queries()
    print(f"eval queries: {len(queries)}")

    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(MODEL_NAME)
    query_texts = [str(e["query"]) for e in queries]
    vecs = [v.tolist() for v in model.encode(query_texts, show_progress_bar=False)]

    report: dict = {"before": str(args.before), "after": str(args.after), "queries": len(vecs)}
    per_snapshot = {}
    per_query = []
    for label, index in (("before", before), ("after", after)):
        top1s, margins = [], []
        for qv in vecs:
            scored = _score_all(qv, index)
            top1s.append(scored[0][1])
            margins.append(scored[0][1] - scored[1][1] if len(scored) > 1 else scored[0][1])
        per_snapshot[label] = {"top1": _dist(top1s), "margin": _dist(margins)}
    report["distribution"] = per_snapshot

    positives = {"both_hit": 0, "lost_hit": 0, "gained_hit": 0, "identity_change": 0, "rows": []}
    for entry, qv in zip(queries, vecs, strict=True):
        expect = [str(x) for x in (entry.get("expect") or [])]
        sb = _score_all(qv, before)
        sa = _score_all(qv, after)
        b_top, b_score = sb[0]
        a_top, a_score = sa[0]
        b_margin = b_score - (sb[1][1] if len(sb) > 1 else 0.0)
        a_margin = a_score - (sa[1][1] if len(sa) > 1 else 0.0)
        b_hit = b_top in expect and b_score >= PROD_THRESHOLD
        a_hit = a_top in expect and a_score >= PROD_THRESHOLD
        if expect:
            if b_hit and a_hit:
                positives["both_hit"] += 1
            elif b_hit and not a_hit:
                positives["lost_hit"] += 1
            elif a_hit and not b_hit:
                positives["gained_hit"] += 1
            if b_top != a_top and (b_hit or a_hit):
                positives["identity_change"] += 1
            positives["rows"].append(
                {
                    "query": entry["query"],
                    "expect": expect,
                    "before": {"top1": b_top, "score": round(b_score, 4), "margin": round(b_margin, 4)},
                    "after": {"top1": a_top, "score": round(a_score, 4), "margin": round(a_margin, 4)},
                }
            )
    report["positives"] = positives

    print("\n=== top-1 score distribution ===")
    for label in ("before", "after"):
        d = per_snapshot[label]
        print(f"{label}: top1 {d['top1']}  margin {d['margin']}")
    print("\n=== positives (expect non-empty) ===")
    print(
        f"both_hit={positives['both_hit']} lost_hit={positives['lost_hit']} "
        f"gained_hit={positives['gained_hit']} identity_change={positives['identity_change']}"
    )
    print("\nworst positive margins after (ascending):")
    worst = sorted(positives["rows"], key=lambda r: r["after"]["margin"])[:8]
    for r in worst:
        print(
            f"  margin {r['before']['margin']:.4f} → {r['after']['margin']:.4f} "
            f"| score {r['before']['score']:.4f} → {r['after']['score']:.4f} "
            f"| {r['after']['top1']} | {r['query'][:40]}"
        )

    if args.out:
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nreport written: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
