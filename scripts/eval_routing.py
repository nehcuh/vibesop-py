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

Hermetic mode (gate45 P1) pins the routed universe so numbers are
machine-independent and CI can gate routing quality:
    uv run python scripts/eval_routing.py --hermetic --check
    uv run python scripts/eval_routing.py --hermetic --update-baseline
The router runs with cwd/project_root/HOME all pinned to a tmp dir (no
~/.vibe config or skill-index leak, no repo .vibe/ leak), embedding + AI
triage off, the SCENARIO layer pinned empty (install-mode-independent),
load_sentence_transformer patched to null (kills warm-HF-cache
divergence), and the candidate universe pinned to checkout builtins +
tests/fixtures/benchmark-pack. --update-baseline refuses to absorb ok1
true→false flips vs the old baseline unless --force is passed and every
flip is justified in the PR.

Baseline gate exit codes (--hermetic --check):
    0 — no new top-1 fails (primary/layer drift on passing entries warns)
    1 — new top-1 fail(s): an entry that passed in the baseline now fails
    3 — stale baseline: missing/unreadable/schema-version mismatch, or the
        content fingerprint changed (registry/skills/dataset/posture) —
        refresh with --update-baseline instead of comparing across universes

Usage:
    uv run python scripts/eval_routing.py [--file PATH] [--record] [--json]
                                          [--json-out PATH]
    uv run python scripts/eval_routing.py --hermetic [--check | --update-baseline]
                                          [--baseline PATH]
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

from vibesop.core.routing.benchmark import (  # noqa: E402
    HERMETIC_POSTURE,
    check_update_absorption,
    compute_fingerprint,
    evaluate_against_baseline,
    write_baseline,
)
from vibesop.core.routing.unified import UnifiedRouter  # noqa: E402


def _build_hermetic_router() -> tuple[UnifiedRouter, dict[str, Path], set[str]]:
    """Machine-independent router + pinned candidate universe (gate45 P1).

    Order matters:
    1. chdir to a fresh tmp — InstinctLearner and other stores resolve
       ``.vibe/*`` against the process cwd, and the repo root carries a
       real ``.vibe/`` that must not leak into the benchmark. The tmp dir
       is intentionally left for OS cleanup: atexit flushes may still
       reference it during interpreter shutdown.
    2. Pin HOME/USERPROFILE to the same tmp. Two home-dependent readers
       would otherwise diverge between a developer machine and CI:
       the INDEX layer merges the GLOBAL skill index at
       ``Path.home()/.vibe/skill-index.json`` (locally built, absent on
       CI), and config/external discovery consults ``~``. Both
       ``Path.home()`` and ``expanduser()`` read the env at call time, so
       setting the env var covers both mechanisms.
    3. Null out load_sentence_transformer — machines with a warm HF cache
       would activate the semantic_index embedding fallback that CI (no
       cache) can never take; null forces the deterministic TFIDF path.
    4. RoutingConfig with every layer toggle explicit — CLI-override
       semantics mean unset fields could otherwise leak from ~/.vibe/config.
    5. Pin the SCENARIO layer empty (router._scenario_cache = {}): editable
       installs read it empty by accident (bundled registry only exists in
       wheels); pinning keeps a wheel-installed env from silently
       regenerating the baseline into a different universe.
    6. pin_search_paths pins the universe to checkout builtins + the
       checked-in benchmark fixture pack: no user/project/external
       discovery, no candidates disk cache.

    Returns (router, skill_roots-for-fingerprint, resolvable-skill-ids).
    """
    import os
    import tempfile

    import vibesop.core.embedding_loader as embedding_loader_module
    from vibesop.core.config import RoutingConfig
    from vibesop.core.skills import SkillLoader
    from vibesop.utils.bundled import resolve_builtin_skills_dir

    tmp_root = Path(tempfile.mkdtemp(prefix="vibe-routing-bench-"))
    os.chdir(tmp_root)
    os.environ["HOME"] = str(tmp_root)
    os.environ["USERPROFILE"] = str(tmp_root)

    def _no_model(*_args: object, **_kwargs: object) -> None:
        return None

    embedding_loader_module.load_sentence_transformer = _no_model  # type: ignore[assignment]

    router = UnifiedRouter(
        project_root=tmp_root,
        config=RoutingConfig(enable_embedding=False, enable_ai_triage=False),
    )
    # Pin the SCENARIO layer empty. In an editable install it reads empty
    # by accident (the bundled registry only exists in wheels), but a
    # wheel-installed env would activate it and silently regenerate the
    # baseline into a different universe — pin it so the posture is
    # explicit and install-mode-independent (review F-3/MINOR-3).
    router._scenario_cache = {}

    skill_roots = {
        "builtin": resolve_builtin_skills_dir(ROOT),
        "benchmark-pack": ROOT / "tests" / "fixtures" / "benchmark-pack",
    }
    router._candidate_manager.pin_search_paths(list(skill_roots.values()), enable_external=False)

    # Resolvability check for requires_packs entries must use the pinned
    # universe, not ExternalSkillLoader discovery (machine-dependent).
    pinned = SkillLoader(
        project_root=tmp_root,
        search_paths=list(skill_roots.values()),
        enable_external=False,
        strict_search_paths=True,
    )
    return router, skill_roots, set(pinned.discover_all())


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
    parser.add_argument(
        "--hermetic",
        action="store_true",
        help="pin the routed universe (tmp cwd/project_root, embedding+AI-triage "
        "off, builtin+benchmark-pack only) for reproducible, CI-gateable numbers",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare against the baseline (requires --hermetic): exit 0 ok / "
        "1 new top-1 fail / 3 stale baseline",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="(re)write the baseline from this run (requires --hermetic); refuses "
        "to absorb ok1 true→false flips vs the old baseline unless --force",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="with --update-baseline: knowingly absorb regressions the old "
        "baseline recorded as passing (every flip must be justified in the PR)",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=ROOT / "tests" / "benchmark" / "routing_baseline.json",
        help="baseline file for --check/--update-baseline "
        "(default: tests/benchmark/routing_baseline.json)",
    )
    args = parser.parse_args()

    if (args.check or args.update_baseline) and not args.hermetic:
        parser.error("--check/--update-baseline require --hermetic")
    if args.check and args.update_baseline:
        parser.error("--check and --update-baseline are mutually exclusive")
    if args.hermetic and args.record:
        parser.error("--record is incompatible with --hermetic (no repo-side writes)")

    # Normalize every output path BEFORE a possible chdir into the hermetic
    # tmp — relative paths would otherwise land inside the scratch dir.
    json_out = args.json_out.resolve() if args.json_out else None
    baseline_path = args.baseline.resolve()

    eval_file = args.file if args.file.is_absolute() else ROOT / args.file
    entries = yaml.safe_load(eval_file.read_text(encoding="utf-8"))

    skill_roots: dict[str, Path] | None = None
    if args.hermetic:
        router, skill_roots, pinned_ids = _build_hermetic_router()
        builtin_ids = external_ids = pinned_ids
    else:
        router = UnifiedRouter(project_root=ROOT)
        builtin_ids, external_ids = _load_resolvable_ids()

    skipped_env_count = 0
    hits1 = hits3 = 0
    errors: list[dict] = []
    per_query: list[dict] = []
    baseline_records: list[dict] = []
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
        baseline_records.append(
            {
                "query": query,
                "expect": expect,
                "reject": reject,
                "primary": primary,
                "layer": layer,
                "ok1": bool(ok1),
            }
        )
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

    if json_out:
        out = json_out
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

    if args.update_baseline:
        assert skill_roots is not None  # guarded by argparse above
        fingerprint = compute_fingerprint(
            registry_file=ROOT / "core" / "registry.yaml",
            skill_roots=skill_roots,
            dataset_file=eval_file,
            posture=HERMETIC_POSTURE,
        )
        # Absorption guard (review F-1): refreshing after a fingerprint
        # change must not silently fold regressions into the new baseline.
        guard = None if args.force else check_update_absorption(baseline_path, baseline_records)
        if guard is not None and guard.exit_code == 1:
            print(
                f"\nREFUSED: writing {baseline_path} would absorb "
                f"{len(guard.new_fails)} regression(s) the old baseline "
                "recorded as passing:",
                file=sys.stderr,
            )
            for nf in guard.new_fails:
                print(
                    f"  {nf['query'][:60]!r}: {nf['baseline']} -> {nf['current']}",
                    file=sys.stderr,
                )
            print(
                "Fix the regression, or re-run with --force and justify every flip in the PR.",
                file=sys.stderr,
            )
            return 1
        write_baseline(baseline_path, fingerprint, baseline_records)
        print(f"\nbaseline written -> {baseline_path}")
        print(
            f"  entries: {len(baseline_records)}  "
            f"fingerprint: {fingerprint['sha'][:16]}  "
            f"top-1: {hits1}/{total}"
        )
        if guard is not None:
            for np_entry in guard.new_passes:
                print(f"  newly passing: {np_entry['query'][:60]!r} -> {np_entry['primary']}")
        return 0

    if args.check:
        assert skill_roots is not None  # guarded by argparse above
        fingerprint = compute_fingerprint(
            registry_file=ROOT / "core" / "registry.yaml",
            skill_roots=skill_roots,
            dataset_file=eval_file,
            posture=HERMETIC_POSTURE,
        )
        outcome = evaluate_against_baseline(baseline_path, fingerprint, baseline_records)
        status = {0: "OK", 1: "NEW FAILS", 3: "STALE"}.get(outcome.exit_code, "?")
        # Gate verdict goes to stderr: stdout stays parseable for --json
        # consumers even when combined with --check (review NIT-4).
        say = lambda *a: print(*a, file=sys.stderr)  # noqa: E731
        say(f"\n=== Routing Baseline Check: {status} (exit {outcome.exit_code}) ===")
        say(f"baseline: {baseline_path}")
        say(
            f"entries matched: {outcome.matched_entries} | new-fails: "
            f"{len(outcome.new_fails)} | new-passes: {len(outcome.new_passes)} | "
            f"drift: {len(outcome.drift_warnings)} | known-fails: {outcome.known_fails}"
        )
        say(outcome.reason)
        for nf in outcome.new_fails:
            say(f"  FAIL {nf['query'][:60]!r}")
            say(f"       expect:  {nf['expect'] or '<no-match>'}")
            say(f"       baseline: {nf['baseline']}  current: {nf['current']}")
        for np_entry in outcome.new_passes:
            say(
                f"  PASS(new) {np_entry['query'][:60]!r} -> {np_entry['primary']}"
                "  (refresh recommended)"
            )
        for warning in outcome.drift_warnings:
            say(f"  drift: {warning}")
        return outcome.exit_code

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
