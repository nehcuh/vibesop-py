#!/usr/bin/env python3
"""Calibration for the M3 behavior-consistency bigram-Jaccard threshold.

M12 design (``.omx/artifacts/m12-product-design.md``, 阈值哲学):
"行为一致性 bigram-Jaccard ≥ 0.5(标定后固化)". Discipline mirrors
``scripts/calibrate_discovery_threshold.py``: report distributions and a
decision *band*, never a bare point estimate, and record the blade pairs
closest to the boundary. If the sample is too thin, say so — and exit
non-zero (2) so future gated callers fail-closed (gate24 pi#8a).

Labeling is self-supervised: M2 cluster results are the labels. Every
tool-bearing trace is attributed to a candidate cluster via the pool's
``task_ids``; two traces from the SAME cluster form a positive pair
(same workflow), traces from DIFFERENT clusters form a negative pair.

Anti-leak rules (gate24 MAJOR-A): candidate pools overlap across scan
windows — cmspark's pool has task_ids shared by ≥2 candidates, so one
trace can be attributed to multiple clusters. Without guards that trace
would pair WITH ITSELF as a "negative" at Jaccard 1.0 and poison the
decision band. Therefore:
- ``collect_cluster_sequences`` dedups by (cluster_id, trace group key)
  — repeated rows of one cluster can't self-pair as positives either;
- ``score_pairs`` skips ANY pair whose two entries share a trace group
  key — same-trace pairs enter neither the positive nor the negative
  pool, regardless of cluster labels.

Folded/unfolded dual reporting (gate24 MINOR-C / pi): consecutive
same-tool folding is the production behavior, but it inflates scores
for traces with long repeat runs; the report shows both口径 side by
side so a recalibration can quantify the bias.

Data
----
- ``--spans``: a spans.jsonl (route spans + tool_call spans).
- ``--candidates``: a cluster_candidates.jsonl (cluster labels).

Usage:
    uv run python scripts/calibrate_behavior_threshold.py \
        --spans .vibe/observability/spans.jsonl \
        --candidates .vibe/observability/cluster_candidates.jsonl
    uv run python scripts/calibrate_behavior_threshold.py --self-test
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from vibesop.core.observability.behavior_consistency import (
    _bigrams,
    _jaccard,
    tool_sequence_items_for_tasks,
)


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _task_keys_for_candidate(task_ids: list[str], spans: list[dict]) -> list[tuple[str, str]]:
    """Expand bare candidate task_ids to (project_id, task_id) composites.

    Candidate rows don't persist ``task_keys`` — the project dimension is
    recovered from the SAME spans file the pool was scanned from (route
    spans carrying that task_id). A task_id seen under several projects
    expands to all of them (conservative: same-file attribution is exact).
    """
    wanted = set(task_ids)
    pids_by_tid: dict[str, set[str]] = {}
    for span in spans:
        name = span.get("name")
        if not isinstance(name, str) or not name.startswith("route:"):
            continue
        tid = span.get("task_id")
        if tid in wanted:
            pids_by_tid.setdefault(tid, set()).add(str(span.get("project_id") or "default"))
    return [(pid, tid) for tid in task_ids for pid in sorted(pids_by_tid.get(tid, ()))]


def collect_cluster_sequences(
    spans: list[dict], candidates: list[dict], *, collapse: bool = True
) -> dict[str, list[tuple[str, list[str]]]]:
    """cluster_id → [(trace group key, tool sequence)], deduped.

    Dedup by (cluster_id, group key): a cluster appearing in multiple
    pool rows (rescan artifacts) must not self-pair the same trace as a
    positive (gate24 MAJOR-A). Terminal rows (promoted/dismissed) are
    included — their clusters are still valid workflow labels.
    """
    by_cluster: dict[str, list[tuple[str, list[str]]]] = {}
    seen: set[tuple[str, str]] = set()
    for candidate in candidates:
        cluster_id = candidate.get("cluster_id")
        task_ids = candidate.get("task_ids") or []
        if not isinstance(cluster_id, str) or not task_ids:
            continue
        task_keys = _task_keys_for_candidate(task_ids, spans)
        for group, seq in tool_sequence_items_for_tasks(task_keys, spans, collapse=collapse):
            if (cluster_id, group) in seen:
                continue
            seen.add((cluster_id, group))
            by_cluster.setdefault(cluster_id, []).append((group, seq))
    return by_cluster


def score_pairs(
    by_cluster: dict[str, list[tuple[str, list[str]]]],
) -> tuple[list[tuple[str, float]], list[tuple[str, float]]]:
    """→ (positive pairs, negative pairs) as (pair-label, jaccard) lists.

    Only non-empty-bigram sequences pair up (same rule as
    ``assess_behavior_consistency``). Pairs sharing a trace group key
    are SKIPPED entirely (gate24 MAJOR-A) — a trace attributed to two
    overlapping candidates must not become a cross-cluster "negative"
    at Jaccard 1.0 against itself.
    """
    positives: list[tuple[str, float]] = []
    negatives: list[tuple[str, float]] = []
    entries: list[tuple[str, str, set]] = []
    for cluster_id, items in sorted(by_cluster.items()):
        for group, seq in items:
            bg = _bigrams(seq)
            if bg:
                entries.append((cluster_id, group, bg))
    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            ci, gi, bi = entries[i]
            cj, gj, bj = entries[j]
            if gi == gj:
                continue  # same trace — never a pair, whatever the labels
            label = f"{ci[:8]}@{gi[:8]} × {cj[:8]}@{gj[:8]}"
            score = _jaccard(bi, bj)
            if ci == cj:
                positives.append((label, score))
            else:
                negatives.append((label, score))
    return positives, negatives


def _quantiles(values: list[float]) -> str:
    vals = sorted(values)
    n = len(vals)

    def q(p: float) -> float:
        return vals[min(n - 1, int(p * n))]

    return f"min={q(0):.3f} p25={q(0.25):.3f} median={q(0.5):.3f} p75={q(0.75):.3f} max={q(1):.3f}"


def _report_one(by_cluster: dict[str, list[tuple[str, list[str]]]], *, title: str) -> None:
    total_seqs = sum(len(v) for v in by_cluster.values())
    print(f"\n### {title}")
    print(f"clusters with tool sequences: {len(by_cluster)}")
    for cluster_id, items in sorted(by_cluster.items()):
        print(
            f"  {cluster_id[:8]}: {len(items)} sequence(s), "
            f"lengths {sorted(len(s) for _g, s in items)}"
        )
    print(f"total sequences: {total_seqs}")
    positives, negatives = score_pairs(by_cluster)
    print(
        f"pairs: positive (same cluster) = {len(positives)}, "
        f"negative (cross cluster) = {len(negatives)}"
    )
    if positives:
        print(f"positive jaccards: {_quantiles([s for _, s in positives])}")
    if negatives:
        print(f"negative jaccards: {_quantiles([s for _, s in negatives])}")


def report(
    folded: dict[str, list[tuple[str, list[str]]]],
    unfolded: dict[str, list[tuple[str, list[str]]]],
) -> int:
    """Print the dual-口径 calibration report.

    Returns 0 when a decision band is emitted, 2 when the sample is too
    thin (fail-closed for future gated callers, gate24 pi#8a). The band
    decision is driven by the FOLDED (production)口径; unfolded is a
    bias-control对照.
    """
    _report_one(folded, title="folded (production口径 — consecutive same-tool collapsed)")
    _report_one(unfolded, title="unfolded (对照 — raw sequences)")

    positives, negatives = score_pairs(folded)
    print(f"\n## folded pairs: positive = {len(positives)}, negative = {len(negatives)}")
    if not positives or not negatives:
        print(
            "\nSAMPLE TOO THIN: decision-band evidence insufficient "
            f"(positive={len(positives)}, negative={len(negatives)}). "
            "0.5 stays as the provisional, unverified starting threshold — "
            "re-run once more hook-bearing traces land in candidate clusters."
        )
        return 2

    print(
        "\n## threshold scan, folded (errors = negative≥t false-consistency + "
        "positive<t false-divergence)"
    )
    print("| threshold | false-consistent | false-divergent | total errors |")
    print("|---|---|---|---|")
    best_err, band = None, []
    for t_bp in range(5, 96, 5):
        t = t_bp / 100
        fc = sum(1 for _, s in negatives if s >= t)
        fd = sum(1 for _, s in positives if s < t)
        err = fc + fd
        print(f"| {t:.2f} | {fc} | {fd} | {err} |")
        if best_err is None or err < best_err:
            best_err, band = err, [t]
        elif err == best_err:
            band.append(t)
    assert band is not None
    print(f"\ndecision band (min errors = {best_err}): {band[0]:.2f} .. {band[-1]:.2f}")

    print("\n## blade pairs, folded (closest to the boundary)")
    label, score = min(positives, key=lambda p: p[1])
    print(f"lowest positive pair:  {score:.3f}  {label}")
    label, score = max(negatives, key=lambda p: p[1])
    print(f"highest negative pair: {score:.3f}  {label}")
    return 0


def _synthetic_spans() -> tuple[list[dict], list[dict]]:
    spans: list[dict] = []

    def route(rid: str, tid: str, trace: str) -> None:
        spans.append(
            {
                "id": rid,
                "name": f"route:{tid}",
                "task_id": tid,
                "trace_id": trace,
                "project_id": "test",
                "span_kind": "task",
                "started_at": "2026-08-01T00:00:00+00:00",
            }
        )

    def tool(tid_span: str, trace: str, parent: str, tool_name: str, ts: str) -> None:
        spans.append(
            {
                "id": tid_span,
                "name": f"tool:{tool_name}",
                "span_kind": "tool_call",
                "trace_id": trace,
                "parent_span_id": parent,
                "started_at": ts,
            }
        )

    # cluster A: two traces, same workflow (Read→Grep→Read, consecutive dupes folded)
    route("r1", "taskA1", "tr1")
    tool("t1", "tr1", "r1", "Read", "2026-08-01T00:01:00+00:00")
    tool("t2", "tr1", "r1", "Read", "2026-08-01T00:02:00+00:00")
    tool("t3", "tr1", "r1", "Grep", "2026-08-01T00:03:00+00:00")
    tool("t4", "tr1", "r1", "Read", "2026-08-01T00:04:00+00:00")
    route("r2", "taskA2", "tr2")
    tool("t5", "tr2", "r2", "Read", "2026-08-02T00:01:00+00:00")
    tool("t6", "tr2", "r2", "Grep", "2026-08-02T00:02:00+00:00")
    tool("t7", "tr2", "r2", "Read", "2026-08-02T00:03:00+00:00")
    # cluster B: one trace, different workflow
    route("r3", "taskB1", "tr3")
    tool("t8", "tr3", "r3", "Bash", "2026-08-03T00:01:00+00:00")
    tool("t9", "tr3", "r3", "Write", "2026-08-03T00:02:00+00:00")

    candidates = [
        {"cluster_id": "a" * 16, "task_ids": ["taskA1", "taskA2"], "status": "pending"},
        {"cluster_id": "b" * 16, "task_ids": ["taskB1"], "status": "pending"},
    ]
    return spans, candidates


def _self_test() -> int:
    """Synthetic sanity: 2 clusters, one consistent, plus divergent cross pairs."""
    spans, candidates = _synthetic_spans()
    by_cluster = collect_cluster_sequences(spans, candidates)
    positives, negatives = score_pairs(by_cluster)
    ok = True
    if len(positives) != 1 or positives[0][1] != 1.0:
        print(f"SELF-TEST FAIL: positives={positives} (want 1 pair @ 1.0)")
        ok = False
    if len(negatives) != 2 or any(s >= 0.5 for _, s in negatives):
        print(f"SELF-TEST FAIL: negatives={negatives} (want 2 pairs < 0.5)")
        ok = False
    print("self-test:", "OK" if ok else "FAILED")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spans", default=".vibe/observability/spans.jsonl")
    parser.add_argument("--candidates", default=".vibe/observability/cluster_candidates.jsonl")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run a synthetic sanity check instead of reading data files",
    )
    args = parser.parse_args()

    if args.self_test:
        return _self_test()

    spans = _load_jsonl(Path(args.spans))
    candidates = _load_jsonl(Path(args.candidates))
    print(f"spans: {len(spans)}  candidates: {len(candidates)}")
    if not spans or not candidates:
        print("FATAL: empty spans or candidates file.", file=sys.stderr)
        return 1
    return report(
        collect_cluster_sequences(spans, candidates, collapse=True),
        collect_cluster_sequences(spans, candidates, collapse=False),
    )


if __name__ == "__main__":
    sys.exit(main())
