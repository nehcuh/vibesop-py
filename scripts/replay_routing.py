#!/usr/bin/env python3
"""Offline replay harness for historical routing decisions (M1b).

Re-routes queries from a project's analytics.jsonl with the current code
and diffs the new decisions against the recorded ones: agreement rate,
old-vs-new layer distribution, and the top changed queries. Use --no-llm
to disable AI triage and replay only the deterministic layers (the config
knob RoutingConfig.enable_ai_triage=False, same as eval_routing.py's
record_telemetry=False escape hatch, keeps replay from writing telemetry).

Warning: without --no-llm, replay makes REAL LLM calls (costs money) and
writes real entries to the project's .vibe/triage_cache.json — the
record_telemetry=False flag only suppresses analytics telemetry, it does
not isolate the persistent triage cache.

Usage:
    uv run python scripts/replay_routing.py \
        --log /path/.vibe/analytics.jsonl [--project-root /path] \
        [--limit 200] [--no-llm] [--output replay-report.json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

_USER_QUERY_RE = re.compile(r"<user_query>\s*(.*?)\s*</user_query>", re.DOTALL)
TOP_CHANGES = 20


def strip_wrapper(query: str) -> str:
    """Remove the <user_query>...</user_query> wrapper if present."""
    m = _USER_QUERY_RE.search(query)
    return (m.group(1) if m else query).strip()


def load_records(log_path: Path, limit: int | None = None) -> tuple[list[dict], int]:
    """Load replayable records from analytics.jsonl.

    Returns (records, skipped). Each record carries the cleaned query plus
    the historical decision (old_primary / old_layer, the last layer in the
    recorded routing path). Lines that are unparseable, lack a query, or
    contain system-reminder junk are skipped.
    """
    records: list[dict] = []
    skipped = 0
    for raw_line in log_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            skipped += 1
            continue
        raw = entry.get("query")
        if not isinstance(raw, str) or "<system-reminder" in raw:
            skipped += 1
            continue
        query = strip_wrapper(raw)
        if not query:
            skipped += 1
            continue
        layers = entry.get("routing_layers")
        old_layer = layers[-1] if isinstance(layers, list) and layers else None
        records.append(
            {
                "query": query,
                "old_primary": entry.get("primary_skill"),
                "old_layer": old_layer,
            }
        )
        if limit is not None and len(records) >= limit:
            break
    return records, skipped


def replay(router: Any, records: list[dict]) -> list[dict]:
    """Re-route each record's query with the given router, in place.

    The router only needs a ``route(query, record_telemetry=False)`` method
    returning an object with a ``primary`` SkillRoute (or None) — tests pass
    a stub. Each record gains new_primary / new_layer / new_confidence.
    """
    for rec in records:
        result = router.route(rec["query"], record_telemetry=False)
        primary = result.primary
        rec["new_primary"] = primary.skill_id if primary else None
        rec["new_layer"] = primary.layer.value if primary else "no_match"
        rec["new_confidence"] = round(primary.confidence, 4) if primary else 0.0
    return records


def build_report(records: list[dict], skipped: int, *, no_llm: bool) -> dict:
    """Diff old vs new decisions into a JSON-serializable report."""
    total = len(records)
    changed = [r for r in records if r["new_primary"] != r["old_primary"]]
    old_dist: dict[str, int] = {}
    new_dist: dict[str, int] = {}
    for r in records:
        old_dist[r["old_layer"] or "unknown"] = old_dist.get(r["old_layer"] or "unknown", 0) + 1
        new_dist[r["new_layer"]] = new_dist.get(r["new_layer"], 0) + 1

    # "Largest" changes = the most confident flips (a high-confidence new
    # decision overriding the log is the most consequential drift).
    top_changes = sorted(changed, key=lambda r: -r["new_confidence"])[:TOP_CHANGES]

    return {
        "no_llm": no_llm,
        "total": total,
        "skipped": skipped,
        "agreement": {
            "matches": total - len(changed),
            "changed": len(changed),
            "rate": round((total - len(changed)) / total, 4) if total else 0.0,
        },
        "layer_distribution": {"old": old_dist, "new": new_dist},
        "top_changes": top_changes,
    }


def _print_summary(report: dict) -> None:
    ag = report["agreement"]
    print("\n=== Routing Replay ===")
    print(
        f"replayed: {report['total']} | skipped: {report['skipped']} | no_llm: {report['no_llm']}"
    )
    print(
        f"agreement: {ag['matches']}/{report['total']} ({ag['rate']:.1%}) | "
        f"changed: {ag['changed']}"
    )
    print("\nLayer distribution (old -> new):")
    for layer, n in sorted(report["layer_distribution"]["old"].items(), key=lambda kv: -kv[1]):
        new_n = report["layer_distribution"]["new"].get(layer, 0)
        print(f"  {layer}: {n} -> {new_n}")
    for layer, n in sorted(report["layer_distribution"]["new"].items(), key=lambda kv: -kv[1]):
        if layer not in report["layer_distribution"]["old"]:
            print(f"  {layer}: 0 -> {n}")
    if report["top_changes"]:
        print(f"\nTop changes ({len(report['top_changes'])}):")
        for r in report["top_changes"]:
            print(f"  {r['old_primary']} -> {r['new_primary']} ({r['new_confidence']:.0%})")
            print(f"      {r['query'][:70]!r}")


def _resolve_project_root(log_path: Path, project_root: Path | None) -> Path:
    """Pick the project whose skills/config the replay should route against.

    Explicit --project-root wins; otherwise derive it from the log location
    (a log at <proj>/.vibe/analytics.jsonl belongs to <proj>). Falls back to
    this repo's ROOT with a warning so cross-project replays don't silently
    run against the wrong skill set.
    """
    if project_root is not None:
        return project_root
    if log_path.parent.name == ".vibe":
        return log_path.parent.parent
    print(
        f"Warning: cannot derive project root from {log_path} "
        f"(not <proj>/.vibe/...); falling back to {ROOT}.",
        file=sys.stderr,
    )
    return ROOT


def _build_router(no_llm: bool, project_root: Path):
    """Build a UnifiedRouter; --no-llm disables the AI triage layer via the
    existing RoutingConfig.enable_ai_triage knob (no production changes)."""
    from vibesop.core.config import ConfigManager
    from vibesop.core.routing.unified import UnifiedRouter

    config_manager = ConfigManager(project_root=project_root)
    config = config_manager.get_routing_config()
    if no_llm:
        config = config.model_copy(update={"enable_ai_triage": False})
    return UnifiedRouter(project_root=project_root, config=config)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True, help="path to analytics.jsonl")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="project to route against (default: derived from --log, falling back to this repo)",
    )
    parser.add_argument("--limit", type=int, default=None, help="max records to replay")
    parser.add_argument("--output", type=Path, default=None, help="write JSON report here")
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="disable AI triage; replay deterministic layers only",
    )
    args = parser.parse_args()

    records, skipped = load_records(args.log, args.limit)
    project_root = _resolve_project_root(args.log, args.project_root)
    router = _build_router(args.no_llm, project_root)
    replay(router, records)
    report = build_report(records, skipped, no_llm=args.no_llm)
    report["log"] = str(args.log)
    report["project_root"] = str(project_root)

    _print_summary(report)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"\nReport written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
