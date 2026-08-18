#!/usr/bin/env python3
"""Build an extended routing eval set from production logs (M1c).

Extracts candidate queries from a project's analytics.jsonl, stratified-
samples them by length bucket, weak-labels them with the AI triage log's
query -> selected_skill mapping, and writes a new YAML eval file. The
hand-curated tests/benchmark/routing_eval.yaml is never overwritten;
--merge appends human-confirmed entries (needs_review: false) into it.

Usage:
    uv run python scripts/build_eval_from_logs.py \
        --analytics /path/.vibe/analytics.jsonl \
        --triage /path/.vibe/ai_triage_log.jsonl
    uv run python scripts/build_eval_from_logs.py --merge
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from vibesop.utils import atomic_writer  # noqa: E402
from vibesop.utils.redaction import redact_sensitive  # noqa: E402

MAIN_EVAL = ROOT / "tests" / "benchmark" / "routing_eval.yaml"
DEFAULT_OUTPUT = ROOT / "tests" / "benchmark" / "routing_eval_extended.yaml"

_USER_QUERY_RE = re.compile(r"<user_query>\s*(.*?)\s*</user_query>", re.DOTALL)
_WS_RE = re.compile(r"\s+")

# Length buckets (chars): short / medium / long.
BUCKETS = ("short", "medium", "long")


def normalize(text: str) -> str:
    """Collapse all whitespace runs so dedup is formatting-insensitive."""
    return _WS_RE.sub(" ", text).strip()


def strip_wrapper(query: str) -> str:
    """Remove the <user_query>...</user_query> wrapper if present."""
    m = _USER_QUERY_RE.search(query)
    return m.group(1) if m else query


def extract_queries(analytics_path: Path) -> list[str]:
    """Extract unique candidate queries from an analytics.jsonl file."""
    seen: set[str] = set()
    queries: list[str] = []
    for raw_line in analytics_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        raw = record.get("query")
        if not isinstance(raw, str):
            continue
        if "<system-reminder" in raw:
            continue
        query = normalize(strip_wrapper(raw))
        if not query or query in seen:
            continue
        seen.add(query)
        queries.append(query)
    return queries


def bucket_of(query: str) -> str:
    n = len(query)
    if n <= 15:
        return "short"
    if n <= 50:
        return "medium"
    return "long"


def stratified_sample(queries: list[str], n: int, seed: int = 42) -> list[str]:
    """Sample ~n queries, allocating per bucket proportionally to the real
    distribution so the short-query share (~30%) is preserved."""
    by_bucket: dict[str, list[str]] = {b: [] for b in BUCKETS}
    for q in queries:
        by_bucket[bucket_of(q)].append(q)

    rng = random.Random(seed)
    total = len(queries)
    sampled: list[str] = []
    for bucket in BUCKETS:
        pool = by_bucket[bucket]
        quota = min(len(pool), round(n * len(pool) / total)) if total else 0
        sampled.extend(rng.sample(pool, quota))
    rng.shuffle(sampled)
    return sampled


def load_triage_labels(triage_path: Path) -> dict[str, str]:
    """Build normalized query -> selected_skill map; latest record wins.

    The triage log stores raw queries while analytics.jsonl stores them
    redacted, so redact here too or redaction-hit queries never join."""
    labels: dict[str, str] = {}
    if not triage_path.exists():
        return labels
    for raw_line in triage_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        query, skill = record.get("query"), record.get("selected_skill")
        if isinstance(query, str) and isinstance(skill, str) and skill:
            labels[normalize(strip_wrapper(redact_sensitive(query)))] = skill
    return labels


def build_entries(
    queries: list[str], labels: dict[str, str]
) -> list[dict]:
    """Weak-label sampled queries. Every entry needs human review."""
    entries = []
    for q in queries:
        skill = labels.get(normalize(q))
        entry: dict = {
            "query": q,
            "expect": [skill] if skill else [],
            "category": "production_log",
            "needs_review": True,
        }
        if skill:
            entry["weak_label"] = True
        entries.append(entry)
    return entries


def merge_confirmed(extended_path: Path, main_path: Path = MAIN_EVAL) -> int:
    """Append human-confirmed entries (needs_review: false, expect set)
    from the extended file into the main eval set, and drop them from the
    extended file. Returns the number of merged entries."""
    extended = yaml.safe_load(extended_path.read_text(encoding="utf-8")) or []
    main = yaml.safe_load(main_path.read_text(encoding="utf-8")) or []
    main_bad = [e for e in main if not isinstance(e.get("query"), str)]
    if main_bad:
        # Hand-edited main entries missing "query" can't be keyed — skip
        # them for dedup instead of crashing with KeyError.
        print(
            f"Warning: skipped {len(main_bad)} main entries missing 'query'.",
            file=sys.stderr,
        )
    main_queries = {normalize(e["query"]) for e in main if isinstance(e.get("query"), str)}

    confirmed, remaining, skipped = [], [], 0
    for e in extended:
        if not isinstance(e.get("query"), str):
            # Hand-edited entries missing "query" can't be keyed — keep them
            # in the extended file instead of crashing mid-merge.
            skipped += 1
            remaining.append(e)
        elif e.get("needs_review") is False and e.get("expect"):
            if normalize(e["query"]) not in main_queries:
                confirmed.append(
                    {k: v for k, v in e.items() if k not in ("needs_review", "weak_label")}
                )
                main_queries.add(normalize(e["query"]))
        else:
            remaining.append(e)
    if skipped:
        print(
            f"Warning: skipped {skipped} extended entries missing 'query'.",
            file=sys.stderr,
        )

    if confirmed:
        if main:
            main_text = main_path.read_text(encoding="utf-8")
            # A main file without a trailing newline would glue the last entry
            # onto the first appended line and corrupt the YAML.
            if not main_text.endswith("\n"):
                main_text += "\n"
            atomic_writer.write_text(
                main_path,
                main_text + yaml.safe_dump(confirmed, allow_unicode=True, sort_keys=False),
            )
        else:
            # An empty or "[]" main file can't be text-appended to (the
            # result would be invalid YAML); rewrite it from the parsed
            # entry list instead. safe_dump always ends with a newline.
            atomic_writer.write_text(
                main_path,
                yaml.safe_dump(confirmed, allow_unicode=True, sort_keys=False),
            )
        atomic_writer.write_text(
            extended_path,
            yaml.safe_dump(remaining, allow_unicode=True, sort_keys=False),
        )
    return len(confirmed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analytics", type=Path, help="path to analytics.jsonl")
    parser.add_argument("--triage", type=Path, help="path to ai_triage_log.jsonl")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--n", type=int, default=130, help="sample size")
    parser.add_argument("--seed", type=int, default=42, help="sampling seed")
    parser.add_argument(
        "--merge",
        action="store_true",
        help="merge human-confirmed entries from --output into the main eval set",
    )
    args = parser.parse_args()

    if args.merge:
        merged = merge_confirmed(args.output)
        print(f"Merged {merged} confirmed entries into {MAIN_EVAL.name}.")
        return 0

    if not args.analytics:
        parser.error("--analytics is required unless --merge is passed")

    queries = extract_queries(args.analytics)
    sampled = stratified_sample(queries, args.n, args.seed)
    labels = load_triage_labels(args.triage) if args.triage else {}
    entries = build_entries(sampled, labels)

    labeled = sum(1 for e in entries if e.get("weak_label"))
    args.output.write_text(
        "# Extended routing eval set, weak-labeled from production logs (M1c).\n"
        "# All entries need human review; confirm via --merge after fixing "
        "expect/needs_review.\n"
        + yaml.safe_dump(entries, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(
        f"extracted: {len(queries)} | sampled: {len(sampled)} "
        f"(short/medium/long: "
        + "/".join(str(sum(1 for e in entries if bucket_of(e["query"]) == b)) for b in BUCKETS)
        + f") | weak-labeled: {labeled} -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
