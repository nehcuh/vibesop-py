#!/usr/bin/env python3
"""Build an extended routing eval set from production logs (M1c).

Extracts candidate queries from a project's analytics.jsonl, stratified-
samples them by length bucket, weak-labels them with the AI triage log's
query -> selected_skill mapping, and writes a new YAML eval file. The
hand-curated tests/benchmark/routing_eval.yaml is never overwritten;
--merge appends human-confirmed entries (needs_review: false, expect set)
into it and moves EXPLICITLY-marked dismissals (needs_review: false,
expect empty, plus a ``dismissed: true`` flag or a ``retention_reason``
field) into routing_eval_retention.yaml (insight-mining pool, not scored).
An unmarked ``expect: []`` entry is a scored no-match assertion and is
left untouched. All persisted queries are forced through redact_sensitive
— at export time and again at merge time (gate37 修订 I).

Flow: export → extended (needs_review: true, redacted) → human reviews
expect/needs_review (dismissals additionally get an explicit marker) →
--merge. The main yaml is append-only via this script — never hand-edited
(human edits belong in the extended file).

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
RETENTION_EVAL = ROOT / "tests" / "benchmark" / "routing_eval_retention.yaml"

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


def build_entries(queries: list[str], labels: dict[str, str]) -> list[dict]:
    """Weak-label sampled queries. Every entry needs human review.

    gate37 (修订 I): queries are FORCED through ``redact_sensitive``
    before they are persisted — the cmspark export path has no upstream
    redaction, so sanitising "at the source" cannot be relied on. Label
    lookup happens on the redacted form (labels are redacted too, so the
    join semantics are unchanged).
    """
    entries = []
    for q in queries:
        safe_q = redact_sensitive(q)
        skill = labels.get(normalize(safe_q))
        entry: dict = {
            "query": safe_q,
            "expect": [skill] if skill else [],
            "category": "production_log",
            "needs_review": True,
        }
        if skill:
            entry["weak_label"] = True
        entries.append(entry)
    return entries


def _is_comment_only(text: str) -> bool:
    """True when every non-blank line is a YAML comment (header-only file)."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return bool(lines) and all(ln.lstrip().startswith("#") for ln in lines)


def _header_comments(text: str) -> str:
    """The leading comment/blank block of a YAML file (provenance header)."""
    lines = []
    for ln in text.splitlines():
        if ln.strip() == "" or ln.lstrip().startswith("#"):
            lines.append(ln)
        else:
            break
    return "\n".join(lines).rstrip("\n")


def _rewrite_preserving_header(path: Path, entries: list[dict]) -> None:
    """Full-rewrite a YAML eval file but carry over its leading comment
    header — a plain safe_dump rewrite would silently drop the provenance
    block (the extended file's label-audit provenance / environment
    notes), claude NIT. Inline comments BETWEEN entries are not preserved
    by any full rewrite (accepted — same as before)."""
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    header = _header_comments(old)
    body = yaml.safe_dump(entries, allow_unicode=True, sort_keys=False)
    atomic_writer.write_text(path, (header + "\n\n" + body) if header else body)


def _redact_free_text(entry: dict) -> None:
    """Redact free-text annotation fields in place before persistence
    (claude NIT: ``note:`` is human free text and carries the same leak
    surface as ``query``)."""
    note = entry.get("note")
    if isinstance(note, str) and note:
        entry["note"] = redact_sensitive(note)


def _append_entries(path: Path, existing: list[dict], new: list[dict]) -> None:
    """Append ``new`` entries to a YAML eval file, preserving any header
    comment block (text-append; re-dumping the whole file would drop the
    provenance comments). A file that exists but parses empty yet carries
    a comment header (pure comments) is ALSO appended to — rewriting it
    would silently drop the header (pi NIT). Falls back to a full rewrite
    only when the file is empty or "[]" (text-append would produce
    invalid YAML there)."""
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if existing or _is_comment_only(text):
        # A file without a trailing newline would glue the last line onto
        # the first appended entry and corrupt the YAML.
        if text and not text.endswith("\n"):
            text += "\n"
        atomic_writer.write_text(
            path,
            text + yaml.safe_dump(new, allow_unicode=True, sort_keys=False),
        )
    else:
        # safe_dump always ends with a newline.
        atomic_writer.write_text(
            path,
            yaml.safe_dump(new, allow_unicode=True, sort_keys=False),
        )


def merge_confirmed(
    extended_path: Path,
    main_path: Path = MAIN_EVAL,
    retention_path: Path = RETENTION_EVAL,
) -> int:
    """Append human-confirmed entries (needs_review: false, expect set)
    from the extended file into the main eval set, move EXPLICITLY-marked
    human dismissals into the retention pool, and drop both from the
    extended file. Returns the number of entries merged into the main set.

    gate37 (修订 I): every persisted query is FORCED through
    ``redact_sensitive`` again at merge time — human edits to the
    extended file are part of the flow, and nothing upstream guarantees
    they stay sanitised. Redaction happens BEFORE dedup/backfill so two
    raw queries that redact to the same text cannot both land (claude
    NIT).

    Dismissal requires an explicit marker — ``dismissed: true`` or a
    ``retention_reason`` field — alongside needs_review: false and an
    empty expect (pi MAJOR). An UNMARKED ``expect: []`` entry is a scored
    no-match assertion (eval_routing.py counts it), NOT a dismissal; it
    stays in the extended flow. Consequence: the first ``--merge`` over
    the pre-gate37 extended file is a zero migration.
    """
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

    retention: list[dict] = []
    if retention_path.exists():
        retention = yaml.safe_load(retention_path.read_text(encoding="utf-8")) or []
    retention_queries = {
        normalize(e["query"]) for e in retention if isinstance(e.get("query"), str)
    }

    confirmed, retained, remaining, skipped, handled_dupes = [], [], [], 0, 0
    for e in extended:
        if not isinstance(e.get("query"), str):
            # Hand-edited entries missing "query" can't be keyed — keep them
            # in the extended file instead of crashing mid-merge.
            skipped += 1
            remaining.append(e)
            continue
        # Redact FIRST, then dedup/backfill on the redacted form (the form
        # that gets persisted).
        safe_query = redact_sensitive(e["query"])
        key = normalize(safe_query)
        if e.get("needs_review") is False and e.get("expect"):
            if key not in main_queries:
                # Strip review metadata AND any dismissal marker keys —
                # a contradictory entry (expect set + dismissed: true)
                # must not leak the marker into the main-set schema
                # (claude NIT: strip, the smaller change vs rejecting).
                entry = {
                    k: v
                    for k, v in e.items()
                    if k not in ("needs_review", "weak_label", "dismissed", "retention_reason")
                }
                entry["query"] = safe_query
                _redact_free_text(entry)
                confirmed.append(entry)
                main_queries.add(key)
            else:
                # Already in the main set — drop from extended (recorded).
                handled_dupes += 1
        elif (
            e.get("needs_review") is False
            and not e.get("expect")
            and (e.get("dismissed") is True or e.get("retention_reason"))
        ):
            # Explicitly-marked human dismiss → retention pool, never the
            # scored main set. Retention entries KEEP needs_review: false
            # and always carry retention_reason. (Being precise: the
            # pre-existing pool keeps needs_review: true + weak_label —
            # only the dedup-key semantics align, not the full schema.)
            # A dismiss already present in the pool is simply dropped from
            # the extended file (already recorded).
            if key not in retention_queries:
                entry = {k: v for k, v in e.items() if k != "dismissed"}
                entry["query"] = safe_query
                entry["needs_review"] = False
                entry.setdefault(
                    "retention_reason",
                    "dismissed during eval review (no routing ground truth)",
                )
                _redact_free_text(entry)
                retained.append(entry)
                retention_queries.add(key)
            else:
                handled_dupes += 1
        else:
            remaining.append(e)
    if skipped:
        print(
            f"Warning: skipped {skipped} extended entries missing 'query'.",
            file=sys.stderr,
        )
    if handled_dupes:
        # Dedup drops are otherwise silent — including post-redaction
        # collisions where two raw queries redact to the same text but
        # carry DIFFERENT expect labels (pi NIT: surface the count so the
        # reviewer knows to look).
        print(
            f"Warning: dropped {handled_dupes} extended entries already present "
            "in main/retention (dedup; possible post-redaction collisions).",
            file=sys.stderr,
        )

    if confirmed:
        _append_entries(main_path, main, confirmed)
    if retained:
        _append_entries(retention_path, retention, retained)
        print(f"Moved {len(retained)} dismissed entries into {retention_path.name}.")
    if confirmed or retained or handled_dupes:
        _rewrite_preserving_header(extended_path, remaining)
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
        "expect/needs_review.\n" + yaml.safe_dump(entries, allow_unicode=True, sort_keys=False),
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
