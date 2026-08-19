#!/usr/bin/env python3
"""One-off calibration for ``index_match_threshold`` after the M3 CJK-bigram
tokenization change (pi review follow-up).

Loads the production skill index (``~/.vibe/skill-index.json``) and scores the
routing eval sets with BOTH tokenization schemes:

- bigram  (current production ``_tokenize_query``, imported from
  ``vibesop.core.routing._layers`` so the script cannot drift from prod)
- unigram (pre-M3 logic: every CJK char is its own token; reproduced here
  in-script — production code is NOT touched)

For each scheme and each threshold in 0.05..0.50 (step 0.05) it reports top-1
accuracy: a query counts as correct iff its best-scoring profile is in
``expect`` AND the best score clears the threshold (below threshold the index
layer abstains and routing falls through, i.e. not an index hit).

Usage:
    uv run python scripts/calibrate_index_threshold.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

from vibesop.core.routing._layers import _score_overlap, _tokenize_query

INDEX_PATH = Path.home() / ".vibe" / "skill-index.json"
MAIN_EVAL = Path("tests/benchmark/routing_eval.yaml")
EXTENDED_EVAL = Path("tests/benchmark/routing_eval_extended.yaml")

THRESHOLDS = [round(0.05 * i, 2) for i in range(1, 11)]  # 0.05 .. 0.50


def _tokenize_unigram(query: str) -> set[str]:
    """Pre-M3 tokenization: English words + one token per CJK character."""
    tokens: set[str] = set()
    for word in re.findall(r"[a-zA-Z]{2,}", query.lower()):
        tokens.add(word)
    for run in re.findall(r"[一-鿿]+", query):
        tokens.update(run)
    return tokens


def _profile_text(profile: dict) -> str:
    return " ".join(
        profile.get("query_patterns", [])
        + profile.get("scenarios", [])
        + profile.get("confidence_boosters", [])
    )


def _is_hit(top1: str | None, expect: list[str]) -> bool:
    """Hit on exact canonical id match only. The last-path-segment tolerance
    was removed after the 2026-08-19 label audit: labels are canonical
    `namespace/name` now, so tolerating namespace-less matches would hide
    id-form bugs instead of weak-label sloppiness."""
    if top1 is None:
        return False
    return top1 in expect


def _load_eval_entries() -> tuple[list[dict], list[dict]]:
    main = [
        e
        for e in yaml.safe_load(MAIN_EVAL.read_text(encoding="utf-8"))
        if e.get("expect")
    ]
    # Extended set was human-audited 2026-08-19 (see file header /
    # .omx/artifacts/tier3-eval-label-audit.md): labels are confirmed, no
    # longer weak — select confirmed positives (expect non-empty).
    extended = yaml.safe_load(EXTENDED_EVAL.read_text(encoding="utf-8"))
    confirmed = [e for e in extended if e.get("expect")]
    return main, confirmed


def _top1_scores(
    entries: list[dict],
    profile_tokens: dict[str, set[str]],
    tokenize,
) -> list[tuple[dict, str | None, float, bool]]:
    """Return (entry, top1_skill, top1_score, hit) per query."""
    rows = []
    for entry in entries:
        q_tokens = tokenize(entry["query"])
        best_id, best_score = None, 0.0
        for skill_id, p_tokens in profile_tokens.items():
            score = _score_overlap(q_tokens, p_tokens)
            if score > best_score:
                best_id, best_score = skill_id, score
        rows.append((entry, best_id, best_score, _is_hit(best_id, entry["expect"])))
    return rows


def _accuracy_curve(rows: list[tuple[dict, str | None, float, bool]]) -> list[float]:
    """Accuracy per threshold: top1 must be a hit AND clear the threshold."""
    return [
        sum(1 for _, _, score, hit in rows if hit and score >= thr) / len(rows)
        for thr in THRESHOLDS
    ]


def _precision_table(title: str, rows_by_scheme: dict[str, list]) -> None:
    """Per threshold: accepted coverage, wrong accepts, precision of accepts.

    A wrong accept (top1 not in expect, score >= threshold) routes to the
    wrong skill at confidence ~0.65 — worse than abstaining, which falls
    through to the scenario/keyword/LLM layers. This is the cost side that
    raw accuracy ignores.
    """
    print(f"\n## {title} — accepted-coverage / wrong-accepts / precision")
    print("| threshold | " + " | ".join(f"{n}: cov | {n}: wrong | {n}: prec" for n in rows_by_scheme) + " |")
    print("|" + "---|" * (1 + 3 * len(rows_by_scheme)))
    for thr in THRESHOLDS:
        cells: list[str] = []
        for rows in rows_by_scheme.values():
            accepted = [(s, h) for _, _, s, h in rows if s >= thr]
            wrong = sum(1 for _, h in accepted if not h)
            cov = len(accepted) / len(rows)
            prec = (len(accepted) - wrong) / len(accepted) if accepted else 0.0
            cells += [f"{cov:.3f}", str(wrong), f"{prec:.3f}"]
        print(f"| {thr:.2f} | " + " | ".join(cells) + " |")


def _print_table(title: str, curves: dict[str, list[float]]) -> None:
    print(f"\n## {title}")
    header = "| threshold | " + " | ".join(curves) + " |"
    print(header)
    print("|" + "---|" * (len(curves) + 1))
    for thr, vals in zip(THRESHOLDS, zip(*curves.values(), strict=True), strict=True):
        print(f"| {thr:.2f} | " + " | ".join(f"{v:.3f}" for v in vals) + " |")


def main() -> int:
    if not INDEX_PATH.exists():
        print(f"index not found: {INDEX_PATH}", file=sys.stderr)
        return 1

    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))["skills"]
    print(f"profiles: {len(index)}")

    main_entries, extended_entries = _load_eval_entries()
    print(f"main eval entries: {len(main_entries)}  extended (audited) entries: {len(extended_entries)}")

    schemes = {"bigram": _tokenize_query, "unigram": _tokenize_unigram}
    results: dict[str, dict[str, list]] = {}
    for name, tokenize in schemes.items():
        profile_tokens = {sid: tokenize(_profile_text(p)) for sid, p in index.items()}
        results[name] = {
            "main": _top1_scores(main_entries, profile_tokens, tokenize),
            "extended": _top1_scores(extended_entries, profile_tokens, tokenize),
        }

    # Score-direction sanity check (pi's example): "提交" vs "提交代码".
    print("\n## score-direction spot check (pi example)")
    for name, tokenize in schemes.items():
        a = tokenize("提交")
        b = tokenize("提交代码")
        print(f"{name}: score('提交' vs '提交代码') = {_score_overlap(a, b):.3f}")

    curves_main = {n: _accuracy_curve(r["main"]) for n, r in results.items()}
    curves_ext = {n: _accuracy_curve(r["extended"]) for n, r in results.items()}
    _print_table("main eval (strong-labeled)", curves_main)
    _print_table("extended (audited labels)", curves_ext)
    _precision_table("main eval", {n: r["main"] for n, r in results.items()})
    _precision_table("extended (audited)", {n: r["extended"] for n, r in results.items()})

    # Unthresholded top-1 accuracy + score distribution summary.
    print("\n## unthresholded top-1 accuracy / mean top-1 score")
    for name, r in results.items():
        for label in ("main", "extended"):
            rows = r[label]
            acc = sum(1 for *_, hit in rows if hit) / len(rows)
            mean = sum(score for _, _, score, _ in rows) / len(rows)
            print(f"{name} {label}: top1-acc={acc:.3f} mean-top1-score={mean:.3f}")

    # Best threshold per scheme on the main set (highest accuracy; ties →
    # higher threshold, since abstaining falls through to embedding/LLM layers
    # which are stronger than a marginal token overlap).
    print("\n## best threshold per scheme (main set)")
    for name, curve in curves_main.items():
        best_acc = max(curve)
        best_thr = max(thr for thr, acc in zip(THRESHOLDS, curve, strict=True) if acc == best_acc)
        print(f"{name}: best threshold {best_thr:.2f} (accuracy {best_acc:.3f})")

    # Per-query diff where the two schemes disagree on the main set.
    print("\n## main-set queries where schemes disagree (unthresholded top1)")
    for (entry, bid, bscore, bhit), (_, uid, uscore, uhit) in zip(
        results["bigram"]["main"], results["unigram"]["main"], strict=True
    ):
        if bhit != uhit:
            print(
                f"- {entry['query']!r}: bigram {bid} ({bscore:.2f}) hit={bhit} | "
                f"unigram {uid} ({uscore:.2f}) hit={uhit}"
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
