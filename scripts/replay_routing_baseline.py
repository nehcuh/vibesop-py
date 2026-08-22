#!/usr/bin/env python3
"""Offline routing-replay baseline measurement (gate32 v3, A3).

Reads a project's recorded route spans (``.vibe/observability/spans.jsonl``),
classifies misses with the gold-detection predicate
(``is_route_miss_span`` — deliberately NOT ``tool_call_bridge._is_miss``,
whose stricter CLI/slash exclusions serve a different consumer), and
measures what the proposed P0 trigger rules WOULD have caught. Purely
offline: zero LLM calls, zero routing-behavior changes, and no writes to
the target project except the report file itself.

P0 shadow rules (record-only, never fed back into routing), applied to the
normalized query (lowercase + whitespace-collapsed):

- exact: normalized query == normalized trigger (any trigger length)
- containment: normalized trigger of >= 6 chars is a substring of the
  normalized query

Agent-prompt-shaped "queries" (system prompts, serialized tool results
that leaked into the route span) are misses by construction and are
counted separately, excluded from the P0-shadow benefit denominator —
but their would-fire pairs are still counted (``agent_shape_would_fire``)
as the misfire metric. The precision side is completed by
``hit_hijack_risks``: spans that already routed correctly are replayed
against the P0 rules, and any would-fire target different from the
observed skill is a hijack risk (gate32 pi MAJOR-1).

Usage:
    uv run python scripts/replay_routing_baseline.py --project-root <path> \
        [--out report.json] [--sample-adjudicate N] [--no-semantic]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from vibesop.core.observability.gold_detection import is_route_miss_span  # noqa: E402

# 刻意复用渲染器的卫生谓词(单一真源,gate32 pi NIT-1):同一文本类必须
# 两个组件同判——skill_promote 用它过滤草稿 trigger 预填,本脚本用它剔除
# 收益分母里的垃圾查询。前缀/长度规则演进时只改 skill_promote 一处。
from vibesop.core.observability.skill_promote import (  # noqa: E402
    _is_agent_prompt_shape,
)
from vibesop.core.routing.triage_recall import (  # noqa: E402
    MODEL_NAME,
    EmbeddingRecall,
    _cosine_similarity,
)

# SpanWriter caps metadata["query"] at 200 chars (agent_runtime.py); a query
# at the cap may be truncated, so its replay fidelity is suspect.
QUERY_CAP = 200
# Containment fires only for triggers of at least this many normalized chars
# (short triggers like "go" would substring-match everything).
CONTAINMENT_MIN_TRIGGER = 6


def parse_metadata(raw: Any) -> dict[str, Any] | None:
    """Tolerantly parse span metadata: dict, JSON string, or None."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _is_route_span(span: dict[str, Any]) -> bool:
    name = span.get("name")
    return span.get("span_kind") == "task" and isinstance(name, str) and name.startswith("route:")


def load_route_records(spans_path: Path) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Extract route-task records from spans.jsonl.

    Returns (records, counters). Each record carries the real query from
    ``metadata["query"]`` (the span name is a truncated display string and
    is never used), its truncation flag, the miss verdict, and the parsed
    metadata. Unparseable lines and route spans without a usable query are
    skipped and counted — repo storage convention: skip bad rows, never
    take down the batch.
    """
    records: list[dict[str, Any]] = []
    counters = {"bad_lines": 0, "non_route_spans": 0, "no_query": 0}
    with spans_path.open("r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue
            try:
                span = json.loads(line)
            except json.JSONDecodeError:
                counters["bad_lines"] += 1
                continue
            if not isinstance(span, dict):
                counters["bad_lines"] += 1
                continue
            if not _is_route_span(span):
                counters["non_route_spans"] += 1
                continue
            meta = parse_metadata(span.get("metadata"))
            query = meta.get("query") if meta else None
            if not isinstance(query, str) or not query.strip():
                counters["no_query"] += 1
                continue
            records.append(
                {
                    "query": query,
                    "truncated": len(query) >= QUERY_CAP,
                    "is_miss": is_route_miss_span(span),
                    "metadata": meta or {},
                }
            )
    return records, counters


def normalize(text: str) -> str:
    """Lowercase + collapse all whitespace runs to single spaces."""
    return " ".join(text.lower().split())


# 本模块内一律用 ``_is_agent_prompt_shape``(导入自 skill_promote),不再
# 持有本地副本。


def build_trigger_index(skills: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Flatten skills into (skill_id, raw_trigger, normalized_trigger) rows."""
    index: list[tuple[str, str, str]] = []
    for skill_id, skill in skills.items():
        for trigger in getattr(skill.metadata, "triggers", None) or []:
            raw = str(trigger)
            norm = normalize(raw)
            if norm:
                index.append((skill_id, raw, norm))
    return index


def p0_shadow(query: str, trigger_index: list[tuple[str, str, str]]) -> list[dict[str, str]]:
    """Offline P0 verdict for one query: which skills would have fired.

    A skill matching both rules is recorded once, as exact (the stronger
    signal). Multiple skills matching the same query is a collision.

    gate32 claude impl NIT-1 — 与生产谓词 ``triage_service.
    explicit_guarded_skill_match`` 的口径刻意分歧(同 is_route_miss_span
    vs tool_call_bridge._is_miss 的记录惯例):生产版 lowercase + 撇号
    剥离、无空白折叠、containment 无长度下限、first-hit-wins;本 shadow
    lowercase + 空白折叠、不剥撇号、≥6 字符下限、全记录 + collision。
    双向系统性偏差存在(撇号变体、<6 字符 trigger、多空格 query),但
    entries 保留 raw query + rule + trigger,未来带护栏的 P0-lite 规则
    可从原始记录重派生——本基线定位是"信号存在性",不是激活数据集。
    """
    qn = normalize(query)
    if not qn:
        return []
    matches: list[dict[str, str]] = []
    for skill_id, raw, norm in trigger_index:
        if qn == norm:
            matches.append({"skill_id": skill_id, "rule": "exact", "trigger": raw})
        elif len(norm) >= CONTAINMENT_MIN_TRIGGER and norm in qn:
            matches.append({"skill_id": skill_id, "rule": "containment", "trigger": raw})
    return matches


def build_identity_diff(
    records: list[dict[str, Any]],
    trigger_index: list[tuple[str, str, str]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """The "verdict change" list: misses the P0 rules would have caught.

    Only non-agent-shaped misses are evaluated for the benefit side. Each
    entry pairs the observed routing outcome (whatever the span metadata
    recorded) with the would-fire targets, for human adjudication.

    Agent-shaped misses stay excluded from the benefit denominator, but
    their would-fire pairs are counted separately
    (``agent_shape_would_fire``) — the precision-side answer to "how often
    would P0 misfire on garbage queries" (gate32 pi MAJOR-1).
    """
    entries: list[dict[str, Any]] = []
    counters = {
        "misses": 0,
        "agent_prompt_shape_misses": 0,
        "agent_shape_would_fire_queries": 0,
        "agent_shape_would_fire_pairs": 0,
        "misses_evaluated": 0,
    }
    for rec in records:
        if not rec["is_miss"]:
            continue
        counters["misses"] += 1
        if _is_agent_prompt_shape(rec["query"]):
            counters["agent_prompt_shape_misses"] += 1
            agent_matches = p0_shadow(rec["query"], trigger_index)
            if agent_matches:
                counters["agent_shape_would_fire_queries"] += 1
                counters["agent_shape_would_fire_pairs"] += len(agent_matches)
            continue
        counters["misses_evaluated"] += 1
        matches = p0_shadow(rec["query"], trigger_index)
        if not matches:
            continue
        meta = rec["metadata"]
        entries.append(
            {
                "query": rec["query"],
                "truncated": rec["truncated"],
                "observed": {
                    "skill_id": meta.get("skill_id"),
                    "has_match": meta.get("has_match"),
                    "layer": meta.get("layer"),
                },
                "would_fire": matches,
                "collision": len({m["skill_id"] for m in matches}) > 1,
            }
        )
    return entries, counters


def build_hit_hijack_risks(
    records: list[dict[str, Any]],
    trigger_index: list[tuple[str, str, str]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Precision side (gate32 pi MAJOR-1): would P0 hijack existing hits?

    For spans that already routed to a skill (``has_match`` is True with an
    observed skill_id), run the same P0-shadow rules. A would-fire target
    different from the observed skill is a hijack risk — activating P0
    could steal a query that today routes correctly. Only the differing
    matches are recorded per entry.

    ``observed == "fallback-llm"`` is the fallback sentinel, not a correct
    hit (same convention as ``is_route_miss_span``: a fallback is not a
    match). A would-fire there is upside, not hijack — those are excluded
    from hits_evaluated and counted separately as
    ``fallback_hits_with_would_fire``.
    """
    entries: list[dict[str, Any]] = []
    counters = {"hits_evaluated": 0, "hijack_risks": 0, "fallback_hits_with_would_fire": 0}
    for rec in records:
        meta = rec["metadata"]
        observed = meta.get("skill_id")
        if rec["is_miss"] or meta.get("has_match") is not True or not observed:
            continue
        if observed == "fallback-llm":
            if p0_shadow(rec["query"], trigger_index):
                counters["fallback_hits_with_would_fire"] += 1
            continue
        counters["hits_evaluated"] += 1
        diverging = [m for m in p0_shadow(rec["query"], trigger_index) if m["skill_id"] != observed]
        if not diverging:
            continue
        counters["hijack_risks"] += 1
        entries.append(
            {
                "query": rec["query"],
                "truncated": rec["truncated"],
                "observed_skill_id": observed,
                "hijack_by": diverging,
            }
        )
    return entries, counters


def build_candidate_texts(skills: dict[str, Any]) -> dict[str, str]:
    """Per-skill recall text via EmbeddingRecall._candidate_text (same text
    the production semantic recall embeds, so scores are comparable)."""
    texts: dict[str, str] = {}
    for skill_id, skill in skills.items():
        spec = skill.metadata
        texts[skill_id] = EmbeddingRecall._candidate_text(
            {
                "id": spec.id,
                "description": spec.description,
                "intent": spec.intent or "",
                "triggers": list(spec.triggers or []),
                "keywords": list(getattr(spec, "keywords", None) or []),
                "scenarios": list(getattr(spec, "scenarios", None) or []),
            }
        )
    return texts


def load_embedding_model() -> Any | None:
    """Lazy-load the recall embedding model; any failure → None (skipped).

    Loads SentenceTransformer directly instead of instantiating
    EmbeddingRecall so the replay never touches the project's on-disk
    embedding cache.
    """
    try:
        from sentence_transformers import (
            SentenceTransformer,  # pyright: ignore[reportMissingImports]
        )

        return SentenceTransformer(MODEL_NAME)
    except Exception as e:
        print(f"Semantic scoring skipped: embedding model unavailable ({e})", file=sys.stderr)
        return None


def semantic_scores(
    entries: list[dict[str, Any]],
    candidate_texts: dict[str, str],
    model: Any | None,
) -> dict[str, Any]:
    """Verbatim-semantic spot check: query vs would-fire skill text cosine.

    For each would-fire (query, skill) pair, embed both verbatim and score
    with the production cosine. Distribution only (min/median/max) — this
    is a plausibility signal for adjudication, not a threshold proposal.
    """
    if model is None:
        return {"available": False, "reason": "embedding model unavailable"}
    pairs = [
        (entry["query"], match["skill_id"])
        for entry in entries
        for match in entry["would_fire"]
        if match["skill_id"] in candidate_texts
    ]
    if not pairs:
        return {"available": True, "scored_pairs": 0}
    unique_queries = sorted({q for q, _ in pairs})
    unique_skills = sorted({sid for _, sid in pairs})
    try:
        raw = model.encode(
            unique_queries + [candidate_texts[sid] for sid in unique_skills],
            show_progress_bar=False,
        )
        vectors = [v.tolist() if hasattr(v, "tolist") else list(v) for v in raw]
    except Exception as e:
        return {"available": False, "reason": f"encoding failed: {e}"}
    q_vecs = dict(zip(unique_queries, vectors[: len(unique_queries)], strict=True))
    s_vecs = dict(zip(unique_skills, vectors[len(unique_queries) :], strict=True))
    scores = [round(_cosine_similarity(q_vecs[q], s_vecs[s]), 4) for q, s in pairs]
    return {
        "available": True,
        "scored_pairs": len(scores),
        "min": min(scores),
        "median": round(statistics.median(scores), 4),
        "max": max(scores),
    }


def deterministic_sample(entries: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    """Pick n entries deterministically via sha1 content digests.

    Builtin hash() is process-randomized (PYTHONHASHSEED) and banned for
    reproducibility; sha1 of the canonical JSON is stable across runs and
    machines, and independent of input ordering. Duplicate (query, skills)
    verdicts collapse to one row — labeling the same verdict twice wastes
    adjudication effort.
    """
    keyed = sorted(
        entries,
        key=lambda e: hashlib.sha1(
            json.dumps(e, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest(),
    )
    picked: list[dict[str, Any]] = []
    seen: set[tuple[str, frozenset[str]]] = set()
    for entry in keyed:
        verdict_key = (
            normalize(entry["query"]),
            frozenset(m["skill_id"] for m in entry["would_fire"]),
        )
        if verdict_key in seen:
            continue
        seen.add(verdict_key)
        picked.append(entry)
        if len(picked) >= n:
            break
    return picked


def write_adjudication_md(path: Path, entries: list[dict[str, Any]]) -> None:
    """Write the sampled would-fire entries as a human-labeling table."""

    def _cell(text: Any) -> str:
        return " ".join(str(text).split()).replace("|", "\\|")

    lines = [
        "# P0-shadow adjudication sample",
        "",
        "Mark `verdict` with `correct` (would-fire skill is the right route) or",
        "`wrong`; add notes as needed. Queries marked `(truncated?)` hit the",
        f"{QUERY_CAP}-char metadata cap and may be cut off.",
        "",
        "| # | query | observed_skill | would_fire_skills | rules | truncated | verdict | notes |",
        "|---|-------|----------------|-------------------|-------|-----------|---------|-------|",
    ]
    for i, entry in enumerate(entries, 1):
        skills = ", ".join(m["skill_id"] for m in entry["would_fire"])
        rules = ", ".join(m["rule"] for m in entry["would_fire"])
        observed = entry["observed"].get("skill_id") or "(miss)"
        lines.append(
            f"| {i} | {_cell(entry['query'])} | {_cell(observed)} | {_cell(skills)} "
            f"| {rules} | {'yes' if entry['truncated'] else 'no'} |  |  |"
        )
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def load_skills(project_root: Path) -> dict[str, Any]:
    """Discover the project's skills with the production loader."""
    from vibesop.core.skills.loader import SkillLoader

    return SkillLoader(project_root=project_root).discover_all()


def run(
    project_root: Path,
    spans_path: Path | None = None,
    out: Path | None = None,
    sample_adjudicate: int | None = None,
    no_semantic: bool = False,
    skills: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the baseline measurement and write the report (plus the
    adjudication sample when requested). Returns the report dict."""
    if spans_path is None:
        spans_path = project_root / ".vibe" / "observability" / "spans.jsonl"
    if out is None:
        out = project_root / ".vibe" / "observability" / "replay_baseline.json"
    if skills is None:
        skills = load_skills(project_root)

    records, counters = load_route_records(spans_path)
    trigger_index = build_trigger_index(skills)
    entries, diff_counters = build_identity_diff(records, trigger_index)
    hijack_entries, hijack_counters = build_hit_hijack_risks(records, trigger_index)

    misses = [r for r in records if r["is_miss"]]
    model = None if no_semantic else load_embedding_model()
    semantic = semantic_scores(entries, build_candidate_texts(skills), model)

    report: dict[str, Any] = {
        "tool": "replay_routing_baseline",
        "project_root": str(project_root),
        "spans_path": str(spans_path),
        "baseline": {
            "total_route_spans": len(records),
            "bad_lines": counters["bad_lines"],
            "non_route_spans": counters["non_route_spans"],
            "no_query": counters["no_query"],
            "misses": diff_counters["misses"],
            "truncated_queries": sum(1 for r in records if r["truncated"]),
            "unique_miss_queries": len({normalize(r["query"]) for r in misses}),
            "agent_prompt_shape_misses": diff_counters["agent_prompt_shape_misses"],
        },
        "p0_shadow": {
            "skills_loaded": len(skills),
            "triggers_indexed": len(trigger_index),
            "misses_evaluated": diff_counters["misses_evaluated"],
            "would_fire_queries": len(entries),
            "would_fire_pairs": sum(len(e["would_fire"]) for e in entries),
            "collisions": sum(1 for e in entries if e["collision"]),
            "rules": {
                "exact": sum(1 for e in entries for m in e["would_fire"] if m["rule"] == "exact"),
                "containment": sum(
                    1 for e in entries for m in e["would_fire"] if m["rule"] == "containment"
                ),
            },
            "agent_shape_would_fire": {
                "queries": diff_counters["agent_shape_would_fire_queries"],
                "pairs": diff_counters["agent_shape_would_fire_pairs"],
            },
            "hit_hijack": {
                "hits_evaluated": hijack_counters["hits_evaluated"],
                "hijack_risks": hijack_counters["hijack_risks"],
                "fallback_hits_with_would_fire": hijack_counters["fallback_hits_with_would_fire"],
            },
            "entries": entries,
            "hit_hijack_risks": hijack_entries,
        },
        "semantic": semantic,
    }

    report["report_path"] = str(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if sample_adjudicate is not None:
        adjudicate_path = Path(str(out) + ".adjudicate.md")
        write_adjudication_md(adjudicate_path, deterministic_sample(entries, sample_adjudicate))
        report["adjudication_sample"] = str(adjudicate_path)

    return report


def _print_summary(report: dict[str, Any]) -> None:
    b = report["baseline"]
    p = report["p0_shadow"]
    print("\n=== Routing Replay Baseline (P0 shadow, offline) ===")
    print(
        f"route spans: {b['total_route_spans']} | misses: {b['misses']} "
        f"| truncated: {b['truncated_queries']} | unique miss queries: "
        f"{b['unique_miss_queries']}"
    )
    print(
        f"skipped: {b['bad_lines']} bad lines, {b['no_query']} without query, "
        f"{b['non_route_spans']} non-route spans"
    )
    print(
        f"agent-prompt-shaped misses excluded: {b['agent_prompt_shape_misses']} "
        f"(evaluated: {p['misses_evaluated']})"
    )
    print(
        f"P0-shadow would-fire: {p['would_fire_queries']} queries, "
        f"{p['would_fire_pairs']} pairs "
        f"(exact: {p['rules']['exact']}, containment: {p['rules']['containment']}), "
        f"collisions: {p['collisions']}"
    )
    a = p["agent_shape_would_fire"]
    h = p["hit_hijack"]
    print(
        f"precision: agent-shaped misfires {a['queries']} queries / {a['pairs']} pairs "
        f"| hit hijack risks: {h['hijack_risks']} of {h['hits_evaluated']} hits "
        f"(+{h['fallback_hits_with_would_fire']} fallback-llm rescues)"
    )
    s = report["semantic"]
    if s.get("available") and s.get("scored_pairs"):
        print(
            f"semantic verbatim cosine ({s['scored_pairs']} pairs): "
            f"min {s['min']:.4f} | median {s['median']:.4f} | max {s['max']:.4f}"
        )
    else:
        print(f"semantic verbatim cosine: unavailable ({s.get('reason', 'no pairs')})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        required=True,
        help="project whose spans and skills to replay against",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="write JSON report here "
        "(default: <project-root>/.vibe/observability/replay_baseline.json)",
    )
    parser.add_argument(
        "--sample-adjudicate",
        type=int,
        default=None,
        metavar="N",
        help="also write N deterministically-sampled would-fire entries "
        "to <out>.adjudicate.md for human labeling",
    )
    parser.add_argument(
        "--no-semantic",
        action="store_true",
        help="skip verbatim semantic scoring (no embedding model load)",
    )
    args = parser.parse_args()

    report = run(
        project_root=args.project_root,
        out=args.out,
        sample_adjudicate=args.sample_adjudicate,
        no_semantic=args.no_semantic,
    )
    _print_summary(report)
    print(f"\nReport written to {report['report_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
