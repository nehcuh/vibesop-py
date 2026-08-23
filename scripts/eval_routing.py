#!/usr/bin/env python3
"""Routing accuracy evaluation harness (SOP §6).

Runs a routing eval dataset (default: tests/benchmark/routing_eval.yaml;
override with --file) against UnifiedRouter and reports top-1 accuracy,
Recall@3, and the confusion pairs. Misroutes are appended to
memory/routing-errors.jsonl when --record is passed (error-to-knowledge
loop, step 1).

Entry semantics:
- expect: [ids...]           — pass iff primary is one of the ids (top-1);
                               recall@3 also checks the first 2 alternatives.
- expect: [] + reject: [...] — pass iff primary is NOT any rejected id.
- expect: [] with no reject  — explicit NO-MATCH assertion: pass iff the
                               router produced no real skill match, i.e.
                               RoutingResult.has_match is False (primary is
                               None or its layer is fallback_llm; the
                               "fallback-llm" skill id counts as no match).
- requires_packs: [ns...]    — environment annotation (gate38): the entry's
                               expect labels live in an external skill pack.
                               An annotated entry with non-empty expect whose
                               expect ids are ALL unresolvable in this
                               environment is scored as skipped_env: excluded
                               from total/denominator and from errors, and
                               recorded with ok1: null in per_query. If the
                               presence check itself fails, ids count as
                               resolvable (conservative: a false error is
                               reported rather than a regression hidden).
                               requires_packs with expect: [] never skips —
                               reject/no-match assertions stay scored.

Usage:
    uv run python scripts/eval_routing.py [--file PATH] [--record] [--json]
                                          [--json-out PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from vibesop.core.routing.unified import UnifiedRouter  # noqa: E402


def _builtin_skill_ids() -> set[str]:
    """Resolvable builtin-side skill ids, parsed from core/registry.yaml in
    canonical `namespace/name` form (already-namespaced ids kept as-is)."""
    registry = yaml.safe_load((ROOT / "core" / "registry.yaml").read_text(encoding="utf-8"))
    ids: set[str] = set()
    for skill in (registry or {}).get("skills", []):
        sid = skill.get("id")
        if not sid:
            continue
        ids.add(sid if "/" in sid else f"{skill.get('namespace', 'builtin')}/{sid}")
    return ids


def _external_skill_ids() -> set[str]:
    """Resolvable external-side skill ids from ExternalSkillLoader discovery
    (keys are already in `pack/name` form)."""
    from vibesop.core.skills.external_loader import ExternalSkillLoader

    return set(ExternalSkillLoader(project_root=ROOT).discover_all())


def _load_resolvable_ids() -> tuple[set[str] | None, set[str] | None]:
    """(builtin_ids, external_ids); a source is None when its presence check
    itself raised — that source then counts every id as resolvable
    (conservative: better a false error than a regression hidden as
    skipped_env)."""
    try:
        builtin = _builtin_skill_ids()
    except Exception:
        builtin = None
    try:
        external = _external_skill_ids()
    except Exception:
        external = None
    return builtin, external


def _is_resolvable(
    skill_id: str, builtin_ids: set[str] | None, external_ids: set[str] | None
) -> bool:
    return any(ids is None or skill_id in ids for ids in (builtin_ids, external_ids))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--record", action="store_true", help="append misroutes to memory/routing-errors.jsonl"
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="write metrics plus per-query records (query, expect, reject, "
        "primary, top3, layer, confidence, ok1, ok3) to this JSON file — "
        "for byte-level failing-set diffs",
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=ROOT / "tests" / "benchmark" / "routing_eval.yaml",
        help="eval dataset YAML; relative paths resolve against the repo root "
        "(default: tests/benchmark/routing_eval.yaml)",
    )
    args = parser.parse_args()

    eval_file = args.file if args.file.is_absolute() else ROOT / args.file
    entries = yaml.safe_load(eval_file.read_text(encoding="utf-8"))
    router = UnifiedRouter(project_root=ROOT)
    builtin_ids, external_ids = _load_resolvable_ids()

    skipped_env_count = 0
    hits1 = hits3 = 0
    errors: list[dict] = []
    per_query: list[dict] = []
    for e in entries:
        query = e["query"]
        expect: list[str] = e.get("expect", [])
        reject: list[str] = e.get("reject", [])

        # skipped_env (gate38): annotated with requires_packs AND a scored
        # positive (expect non-empty — all([]) is True, so the emptiness
        # check must come first) AND every expect id unresolvable here.
        skipped_env = bool(
            e.get("requires_packs")
            and expect
            and not any(_is_resolvable(s, builtin_ids, external_ids) for s in expect)
        )
        if skipped_env:
            skipped_env_count += 1
            per_query.append(
                {
                    "query": query[:80],
                    "expect": expect,
                    "reject": reject,
                    "primary": None,
                    "top3": [],
                    "layer": None,
                    "confidence": None,
                    "ok1": None,
                    "ok3": None,
                    "skipped_env": True,
                }
            )
            continue

        result = router.route(query, record_telemetry=False)
        primary = result.primary.skill_id if result.primary else None
        layer = result.primary.layer.value if result.primary else None
        confidence = result.primary.confidence if result.primary else 0.0
        alts = [a.skill_id for a in (result.alternatives or [])][:2]
        top3 = ([primary] if primary else []) + alts

        ok1 = (
            (primary in expect)
            if expect
            else (primary not in reject)
            if reject
            else not result.has_match  # empty expect + empty reject = no-match assertion
        )
        ok3 = (any(s in expect for s in top3)) if expect else ok1
        hits1 += ok1
        hits3 += ok3
        per_query.append(
            {
                "query": query[:80],
                "expect": expect,
                "reject": reject,
                "primary": primary,
                "top3": top3,
                "layer": layer,
                "confidence": round(confidence, 3),
                "ok1": bool(ok1),
                "ok3": bool(ok3),
                "skipped_env": False,
            }
        )
        if not ok1:
            errors.append(
                {
                    "query": query,
                    "expect": expect,
                    "reject": reject,
                    "actual": primary,
                    "top3": top3,
                    "layer": layer,
                    "confidence": round(confidence, 3),
                    "category": e.get("category"),
                    "note": e.get("note", ""),
                }
            )

    confusion: dict[str, int] = {}
    for err in errors:
        key = f"{(err['expect'] or ['<no-match>'])[0]} -> {err['actual']}"
        confusion[key] = confusion.get(key, 0) + 1

    # skipped_env entries count in neither total (denominator) nor errors;
    # guard against an all-skipped dataset dividing by zero.
    total = len(entries) - skipped_env_count
    metrics = {
        "total": total,
        "skipped_env": skipped_env_count,
        "top1_accuracy": round(hits1 / total, 4) if total else 0.0,
        "recall_at_3": round(hits3 / total, 4) if total else 0.0,
        "errors": errors,
        "confusion_pairs": confusion,
    }

    if args.record and errors:
        log = ROOT / "memory" / "routing-errors.jsonl"
        log.parent.mkdir(exist_ok=True)
        with log.open("a", encoding="utf-8") as f:
            for err in errors:
                err["recorded_at"] = datetime.now(UTC).isoformat()
                f.write(json.dumps(err, ensure_ascii=False) + "\n")

    if args.json_out:
        out = args.json_out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {**metrics, "dataset": str(eval_file), "per_query": per_query},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"saved -> {out}", file=sys.stderr)

    if args.json:
        print(json.dumps(metrics, ensure_ascii=False, indent=2))
    else:
        print(f"\n=== Routing Eval ({eval_file.name}) ===")
        pct1 = hits1 / total if total else 0.0
        pct3 = hits3 / total if total else 0.0
        print(
            f"queries: {total} (skipped_env: {skipped_env_count}) | top-1: {hits1}/{total} ({pct1:.1%}) | recall@3: {hits3}/{total} ({pct3:.1%})"
        )
        if errors:
            print(f"\nMisroutes ({len(errors)}):")
            for err in errors:
                print(f"  [{err['layer']}] {err['query'][:50]!r}")
                print(
                    f"      expect: {err['expect'] or err['reject']}  actual: {err['actual']} ({err['confidence']:.0%})"
                )
            print("\nConfusion pairs:")
            for pair, n in sorted(confusion.items(), key=lambda kv: -kv[1]):
                print(f"  {n}x  {pair}")
        else:
            print("No misroutes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
