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

Two-sided error counts (report-only; never affect exit codes or the
baseline gate):
- n_pos / n_neg     — scored positives (expect non-empty) vs negatives
                      (must_not_inject, or explicit no-match assertion:
                      empty expect and no reject)
- over_reject       — positives where the router produced no real match
- over_inject       — must_not_inject / near_miss negatives where it did
- no_match_by_layer — matched entries by primary layer plus a "no_match"
                      bucket; no_match_rate = no_match / total
- n_near_miss / near_miss_over_inject — entries with `subclass:
                      near_miss` or `category: near_miss` (0 when the
                      dataset has none). near_miss counts as a negative
                      for over_inject but is NOT added to
                      --update-baseline's must_not_inject hard-refuse list.

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
    1 — new top-1 fail(s): an entry that passed in the baseline now fails,
        OR a known-fail entry degraded from the no-match/fallback class into
        an active wrong-skill match (ok1 stays false both ways; the gate
        keys the degradation on the recorded primary/layer so a router that
        starts injecting a real wrong skill where it used to fall back
        honestly does not pass silently)
    3 — stale baseline: missing/unreadable/schema-version mismatch, or the
        content fingerprint changed (registry/skills/dataset/posture) —
        refresh with --update-baseline instead of comparing across universes

Semantic profile mode (lane A, report-only):
    uv run python scripts/eval_routing.py --profile-semantic [--profile-runs N]
Keeps the hermetic 1/2/6 pins (tmp cwd/HOME, pinned candidate universe, empty
SCENARIO layer) and releases step 3/4 for the EMBEDDING layer only: the real
offline-first model loader, enable_embedding=True. AI triage stays OFF — the
profile isolates embedding variance, not LLM variance. A null-embedding
control group runs the same N passes first and must be exactly 100% stable,
otherwise the verdict is CONTROL_BLOCKED (the harness measured its own
noise, not semantic-layer variance). Exit code is always 0 when the profile
ran — exit 2 only means "could not run at all" (embedding model/packages
unavailable offline), never a quality verdict; no threshold ever gates.
Artifacts land in docs/benchmark/semantic_profile/ only after the passes
actually ran.

Usage:
    uv run python scripts/eval_routing.py [--file PATH] [--record] [--json]
                                          [--json-out PATH]
    uv run python scripts/eval_routing.py --hermetic [--check | --update-baseline]
                                          [--baseline PATH]
    uv run python scripts/eval_routing.py --profile-semantic [--profile-runs N]
                                          [--profile-out DIR]
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import platform
import subprocess
import sys
from collections import Counter
from collections.abc import Callable
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

# Posture of the --profile-semantic run, hashed into the artifact filename's
# fingerprint. Records which hermetic pins stay (universe/cwd/HOME/SCENARIO),
# what is released (real offline-first embedding loader, EMBEDDING layer on,
# AI triage still off) and the determinism pins this posture adds: HF_HOME
# pinned to the real user cache (captured before HOME is redirected) and
# single-thread CPU inference (OMP_NUM_THREADS=1 + torch.set_num_threads(1)).
SEMANTIC_PROFILE_POSTURE: dict[str, object] = {
    "enable_embedding": True,
    "enable_ai_triage": False,
    "enable_external": False,
    "strict_search_paths": True,
    "load_sentence_transformer": "real-offline-first",
    "scenario_layer": "disabled",
    "cwd": "tmp",
    "project_root": "tmp",
    "home_env": "tmp",
    "hf_home": "pinned-to-real-user-cache",
    "omp_num_threads": "1",
    "torch_num_threads": "1",
    # In-process harness adapter (zero product-code changes): the matcher
    # pipeline calls match(..., top_k=...) but LazyEmbeddingMatcher does not
    # accept top_k — enable_embedding=True currently TypeErrors inside
    # route() for any query that reaches the EMBEDDING layer. The adapter
    # forwards 1:1 to the real EmbeddingMatcher with the pipeline's top_k.
    "embedding_matcher_adapter": "lazy-top-k-forwarding-in-process",
}


class ProfileUnavailableError(RuntimeError):
    """The semantic profile cannot run (model or packages unavailable offline).

    Raised by the offline preflight so the caller reports PARTIAL honestly
    instead of profiling the deterministic fallback path in disguise.
    """


class _LazyMatcherAdapter:
    """Profile-harness-only adapter: make LazyEmbeddingMatcher callable the
    way MatcherPipeline actually calls it (match with a top_k kwarg).

    The product path crashes today (TypeError: unexpected keyword 'top_k')
    the moment a query falls through to the EMBEDDING layer — see the
    posture note. Forwarding is 1:1 to the real EmbeddingMatcher; no scoring
    or model behavior is changed by this adapter.
    """

    def __init__(self, lazy_matcher: object) -> None:
        self._lazy = lazy_matcher

    def match(self, query: str, candidates: list, context: object = None, top_k: int = 10):
        real = self._lazy._ensure_real()
        return real.match(query, candidates, context, top_k=top_k)

    def warm_up(self, candidates: list) -> None:
        self._lazy.warm_up(candidates)

    def preprocess(self, query: str) -> str:
        return self._lazy.preprocess(query)

    def __getattr__(self, name: str) -> object:
        return getattr(self._lazy, name)


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


# ---------------------------------------------------------------------------
# --profile-semantic (lane A): semantic-layer reliability profile. Everything
# below is report-only — a profile is never a gate.
# ---------------------------------------------------------------------------


def _embedding_model_name() -> str:
    """The model the router's EMBEDDING matcher will actually load (its
    constructor default) — recorded in the profile instead of a guess."""
    from vibesop.core.matching.strategies import EmbeddingMatcher

    return str(EmbeddingMatcher()._model_name)


def _build_profile_router(
    *, enable_embedding: bool
) -> tuple[UnifiedRouter, dict[str, Path], Callable[[], int]]:
    """Pinned-universe router for the semantic profile.

    Mirrors the hermetic builder's steps 1/2/6 (fresh tmp cwd + HOME, pinned
    search paths with external discovery off, empty SCENARIO cache) with
    steps 3/4 released when enable_embedding=True: load_sentence_transformer
    stays the real offline-first loader and the EMBEDDING matcher joins the
    pipeline. AI triage stays off either way. HF_HOME is pinned to the REAL
    user cache (resolved before HOME is redirected — the second build in the
    same process re-reads it from the env, so it keeps resolving the real
    cache) and CPU inference is pinned single-threaded. Deliberately a
    separate function from _build_hermetic_router: the CI gate's posture
    must not gain a branch.

    Returns (router, skill_roots-for-fingerprint, loader-call probe).
    """
    import tempfile

    import vibesop.core.embedding_loader as embedding_loader_module
    from vibesop.core.config import RoutingConfig
    from vibesop.utils.bundled import resolve_builtin_skills_dir

    hf_cache = os.environ.get("HF_HOME") or str(Path.home() / ".cache" / "huggingface")

    tmp_root = Path(tempfile.mkdtemp(prefix="vibe-routing-profile-"))
    os.chdir(tmp_root)
    os.environ["HOME"] = str(tmp_root)
    os.environ["USERPROFILE"] = str(tmp_root)
    os.environ["HF_HOME"] = hf_cache
    os.environ["OMP_NUM_THREADS"] = "1"
    try:
        import torch

        torch.set_num_threads(1)
    except ImportError:
        pass

    loads: dict[str, int] = {"n": 0}
    if enable_embedding:
        original_loader = embedding_loader_module.load_sentence_transformer

        def _counting_loader(model_name: str) -> object:
            loads["n"] += 1
            return original_loader(model_name)

        embedding_loader_module.load_sentence_transformer = _counting_loader  # type: ignore[assignment]
    else:
        # Control group: the exact hermetic null — a warm HF cache must not
        # be able to change this router's behavior.
        def _no_model(*_args: object, **_kwargs: object) -> None:
            return None

        embedding_loader_module.load_sentence_transformer = _no_model  # type: ignore[assignment]

    router = UnifiedRouter(
        project_root=tmp_root,
        config=RoutingConfig(enable_embedding=enable_embedding, enable_ai_triage=False),
    )
    router._scenario_cache = {}
    if enable_embedding:
        # Product bug workaround (see posture note): LazyEmbeddingMatcher
        # does not accept the top_k kwarg the pipeline always passes, so
        # enable_embedding=True crashes route() today. Wrap it in-process —
        # product code stays untouched; the wrapper only forwards.
        from vibesop.core.matching.lazy_matcher import LazyEmbeddingMatcher

        matchers = router._matcher_pipeline._matchers
        router._matcher_pipeline._matchers = [
            (layer, _LazyMatcherAdapter(m) if isinstance(m, LazyEmbeddingMatcher) else m)
            for layer, m in matchers
        ]

    skill_roots = {
        "builtin": resolve_builtin_skills_dir(ROOT),
        "benchmark-pack": ROOT / "tests" / "fixtures" / "benchmark-pack",
    }
    router._candidate_manager.pin_search_paths(list(skill_roots.values()), enable_external=False)
    return router, skill_roots, lambda: loads["n"]


def _preflight_model(model_name: str) -> None:
    """Load the model once, strictly offline, before any passes run.

    HF_HUB_OFFLINE=1 makes even the loader's online-retry path fail fast, so
    a missing/incomplete cache surfaces as ProfileUnavailableError here
    instead of as a silent TFIDF-fallback profile (which would be a fake
    semantic profile) or a mid-run download.
    """
    previous = os.environ.get("HF_HUB_OFFLINE")
    os.environ["HF_HUB_OFFLINE"] = "1"
    try:
        from vibesop.core.embedding_loader import load_sentence_transformer

        load_sentence_transformer(model_name)
    except Exception as exc:
        raise ProfileUnavailableError(
            f"embedding model {model_name!r} unavailable offline "
            f"(HF_HOME={os.environ.get('HF_HOME')!r}): {exc!r}"
        ) from exc
    finally:
        if previous is None:
            os.environ.pop("HF_HUB_OFFLINE", None)
        else:
            os.environ["HF_HUB_OFFLINE"] = previous


def _run_passes(
    router: UnifiedRouter, entries: list[dict], n_passes: int
) -> list[list[tuple[str | None, str | None]]]:
    """N passes over the dataset; one (primary, layer) pair per entry per
    pass. requires_packs annotations are scoring-only and routing-irrelevant,
    so every entry is profiled."""
    passes: list[list[tuple[str | None, str | None]]] = []
    for _ in range(n_passes):
        one_pass: list[tuple[str | None, str | None]] = []
        for entry in entries:
            result = router.route(entry["query"], record_telemetry=False)
            primary = result.primary.skill_id if result.primary else None
            layer = result.primary.layer.value if result.primary else None
            one_pass.append((primary, layer))
        passes.append(one_pass)
    return passes


def _mode_stability(values: list[str | None]) -> tuple[float, str | None]:
    """(mode count / N, mode) — stability of one observation series."""
    if not values:
        return 0.0, None
    mode, count = Counter(values).most_common(1)[0]
    return count / len(values), mode


def _stability_histogram(stabilities: list[float]) -> dict[str, int]:
    counts = Counter(round(s, 4) for s in stabilities)
    return {str(value): count for value, count in sorted(counts.items(), reverse=True)}


def _aggregate_profile(
    passes: list[list[tuple[str | None, str | None]]], entries: list[dict]
) -> dict:
    """Per-query top-1/layer stability (mode count / N) plus dataset-level
    means, histograms and the layer distribution of the final primary."""
    per_query: list[dict] = []
    primary_stabilities: list[float] = []
    layer_stabilities: list[float] = []
    layer_distribution: Counter[str | None] = Counter()
    for idx, entry in enumerate(entries):
        primaries = [one_pass[idx][0] for one_pass in passes]
        layers = [one_pass[idx][1] for one_pass in passes]
        layer_distribution.update(layers)
        primary_stab, primary_mode = _mode_stability(primaries)
        layer_stab, layer_mode = _mode_stability(layers)
        primary_stabilities.append(primary_stab)
        layer_stabilities.append(layer_stab)
        per_query.append(
            {
                "index": idx,
                "query": entry["query"][:80],
                "expect": entry.get("expect", []),
                "primary_mode": primary_mode,
                "primary_stability": round(primary_stab, 4),
                "layer_mode": layer_mode,
                "layer_stability": round(layer_stab, 4),
                "primary_counts": {str(k): v for k, v in Counter(primaries).items()},
                "layer_counts": {str(k): v for k, v in Counter(layers).items()},
            }
        )
    n_queries = len(entries)
    return {
        "n_passes": len(passes),
        "n_queries": n_queries,
        "mean_primary_stability": (
            round(sum(primary_stabilities) / n_queries, 4) if n_queries else 0.0
        ),
        "mean_layer_stability": (
            round(sum(layer_stabilities) / n_queries, 4) if n_queries else 0.0
        ),
        "unstable_primary_count": sum(1 for s in primary_stabilities if s < 1.0),
        "unstable_layer_count": sum(1 for s in layer_stabilities if s < 1.0),
        "primary_stability_histogram": _stability_histogram(primary_stabilities),
        "layer_stability_histogram": _stability_histogram(layer_stabilities),
        "primary_layer_distribution": {str(k): v for k, v in layer_distribution.most_common()},
        "per_query": per_query,
    }


def _control_passes(agg: dict) -> bool:
    """The control contract: with embedding off, stability must be EXACTLY
    1.0 — anything less means the harness itself is noisy and the semantic
    numbers measure nothing (falsification (a))."""
    return agg["unstable_primary_count"] == 0 and agg["unstable_layer_count"] == 0


def _collect_profile_env() -> dict[str, object]:
    env: dict[str, object] = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "hf_home": os.environ.get("HF_HOME"),
        "omp_num_threads_env": os.environ.get("OMP_NUM_THREADS"),
        "hf_hub_offline_env": os.environ.get("HF_HUB_OFFLINE", "<unset>"),
    }
    for module_name in (
        "torch",
        "sentence_transformers",
        "transformers",
        "huggingface_hub",
        "numpy",
    ):
        try:
            env[module_name] = importlib.import_module(module_name).__version__
        except Exception:
            env[module_name] = "not-installed"
    try:
        import torch

        env["torch_get_num_threads"] = torch.get_num_threads()
    except Exception:
        env["torch_get_num_threads"] = None
    return env


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        return out.stdout.strip()
    except Exception:
        return "unknown"


def _write_profile_md(md_path: Path, payload: dict) -> None:
    control = payload["control"]
    semantic = payload["semantic"]
    lines = [
        "# Semantic Layer Reliability Profile",
        "",
        f"- generated (UTC): {payload['created_utc']}",
        f"- git commit: `{payload['git_commit']}`",
        f"- dataset: `{payload['dataset']['path']}` ({payload['dataset']['entries']} entries)",
        f"- model: `{payload['model']}` (EmbeddingMatcher default)",
        f"- N passes per group: {payload['n_passes']}",
        f"- fingerprint: `{payload['fingerprint_sha'][:16]}`",
        f"- verdict: **{payload['verdict']}**",
        "",
        "## Environment pins",
        "",
    ]
    lines += [f"- {key}: {value}" for key, value in sorted(payload["env"].items())]
    lines += [
        "",
        "## Control group (embedding off — harness self-check)",
        "",
        f"- mean primary stability: {control['mean_primary_stability']}",
        f"- mean layer stability: {control['mean_layer_stability']}",
        f"- exactly 1.0: **{control['control_pass']}**",
        "",
        "## Semantic group (embedding on)",
        "",
        f"- mean primary stability: {semantic['mean_primary_stability']}",
        f"- mean layer stability: {semantic['mean_layer_stability']}",
        f"- unstable queries (primary): {semantic['unstable_primary_count']}"
        f"/{semantic['n_queries']}",
        f"- primary stability histogram: {semantic['primary_stability_histogram']}",
        f"- primary layer distribution: {semantic['primary_layer_distribution']}",
        f"- embedding loader calls: {semantic['embedding_loader_calls']}",
        "",
        "## Unstable queries (worst first, capped at 20)",
        "",
    ]
    unstable = [q for q in semantic["per_query"] if q["primary_stability"] < 1.0]
    unstable.sort(key=lambda q: q["primary_stability"])
    if unstable:
        lines += ["| stability | primary mode / counts | query |", "|---|---|---|"]
        lines += [
            f"| {q['primary_stability']} | {q['primary_mode']} {q['primary_counts']} "
            f"| {q['query'][:60]} |"
            for q in unstable[:20]
        ]
    else:
        lines.append("(none — every query produced the same primary across all passes)")
    lines += [
        "",
        "## Interpretation",
        "",
        "- control stability != 1.0 -> falsified (a): the harness measures its own",
        "  noise; fix the harness, ignore the semantic numbers.",
        "- semantic stability ~= 1.0 -> falsified (b): the blind spot is small;",
        "  downgrade lane A to a low-frequency spot check.",
        "- otherwise -> first quantified profile of the semantic layer.",
        "",
        "Report-only by construction: the profile never gates anything (script",
        "exit code is always 0 when the run happened).",
        "",
        f"Machine-readable record: `{md_path.with_suffix('.json').name}`",
        "",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")


def _run_profile(entries: list[dict], eval_file: Path, n_passes: int, profile_out: Path) -> int:
    """Run control (embedding off) + semantic (embedding on) N passes each,
    aggregate, and write the md+json artifacts. Always returns 0 when the
    run happened — CONTROL_BLOCKED is a reported finding, not an exit code."""
    import vibesop.core.embedding_loader as embedding_loader_module

    original_loader = embedding_loader_module.load_sentence_transformer

    # Control group first and entirely within its own pinned cwd: build, run
    # N passes. The loader is nulled exactly like the hermetic posture.
    control_router, _skill_roots, _control_probe = _build_profile_router(enable_embedding=False)
    control_passes = _run_passes(control_router, entries, n_passes)
    # Un-null the loader so the semantic group loads the real model.
    embedding_loader_module.load_sentence_transformer = original_loader  # type: ignore[assignment]

    model_name = _embedding_model_name()
    _preflight_model(model_name)

    semantic_router, skill_roots, loader_probe = _build_profile_router(enable_embedding=True)
    semantic_passes = _run_passes(semantic_router, entries, n_passes)
    loader_calls = loader_probe()

    control_agg = _aggregate_profile(control_passes, entries)
    semantic_agg = _aggregate_profile(semantic_passes, entries)
    control_ok = _control_passes(control_agg)

    if not control_ok:
        verdict = "CONTROL_BLOCKED_HARNESS_NOISE"
    elif loader_calls == 0:
        verdict = "PROFILE_INVALID_NO_EMBEDDING_LOAD"
    else:
        verdict = "PROFILE"

    fingerprint = compute_fingerprint(
        registry_file=ROOT / "core" / "registry.yaml",
        skill_roots=skill_roots,
        dataset_file=eval_file,
        posture=SEMANTIC_PROFILE_POSTURE,
    )
    payload = {
        "schema": "vibesop/semantic-profile/1",
        "created_utc": datetime.now(UTC).isoformat(),
        "git_commit": _git_commit(),
        "dataset": {"path": str(eval_file), "entries": len(entries)},
        "model": model_name,
        "n_passes": n_passes,
        "fingerprint_sha": fingerprint["sha"],
        "posture": SEMANTIC_PROFILE_POSTURE,
        "env": _collect_profile_env(),
        "control": {**control_agg, "control_pass": control_ok},
        "semantic": {**semantic_agg, "embedding_loader_calls": loader_calls},
        "verdict": verdict,
    }

    profile_out.mkdir(parents=True, exist_ok=True)
    stem = f"semantic_profile_{fingerprint['sha'][:16]}"
    json_path = profile_out / f"{stem}.json"
    md_path = profile_out / f"{stem}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_profile_md(md_path, payload)

    print(f"\n=== Semantic Profile (N={n_passes}, {len(entries)} queries) ===")
    print(f"model: {model_name} | fingerprint: {fingerprint['sha'][:16]}")
    print(
        f"control  (embedding off): mean primary {control_agg['mean_primary_stability']} | "
        f"mean layer {control_agg['mean_layer_stability']} | exactly 1.0: {control_ok}"
    )
    print(
        f"semantic (embedding on):  mean primary {semantic_agg['mean_primary_stability']} | "
        f"mean layer {semantic_agg['mean_layer_stability']} | "
        f"unstable {semantic_agg['unstable_primary_count']}/{semantic_agg['n_queries']} | "
        f"histogram {semantic_agg['primary_stability_histogram']}"
    )
    if not control_ok:
        print(
            "CONTROL BLOCKED (falsified (a)): the null-embedding control group is not\n"
            "100% stable — the numbers above measure harness noise, not semantic-layer\n"
            "variance. Fix the harness before reading anything into them."
        )
    if loader_calls == 0:
        print(
            "WARNING: the embedding layer never loaded a model — the semantic numbers\n"
            "are the deterministic path in disguise (verdict PROFILE_INVALID_NO_EMBEDDING_LOAD)."
        )
    print(f"verdict: {verdict}")
    print(f"artifacts -> {json_path} / {md_path}")
    return 0


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
    parser.add_argument(
        "--profile-semantic",
        action="store_true",
        help="semantic-layer reliability profile (lane A, report-only): hermetic "
        "1/2/6 pinning with the EMBEDDING layer released (real offline-first "
        "model, AI triage still off); runs a null-embedding control group N "
        "times first (must be exactly 100% stable). Exit 0 whenever the run "
        "happened — never a gate. Mutually exclusive with --hermetic",
    )
    parser.add_argument(
        "--profile-runs",
        type=int,
        default=10,
        help="N passes per group in --profile-semantic (default 10)",
    )
    parser.add_argument(
        "--profile-out",
        type=Path,
        default=ROOT / "docs" / "benchmark" / "semantic_profile",
        help="artifact directory for the --profile-semantic md+json "
        "(default: docs/benchmark/semantic_profile)",
    )
    args = parser.parse_args()

    if (args.check or args.update_baseline) and not args.hermetic:
        parser.error("--check/--update-baseline require --hermetic")
    if args.check and args.update_baseline:
        parser.error("--check and --update-baseline are mutually exclusive")
    if args.hermetic and args.record:
        parser.error("--record is incompatible with --hermetic (no repo-side writes)")
    if args.profile_semantic and args.hermetic:
        parser.error("--profile-semantic and --hermetic are mutually exclusive postures")
    if args.profile_semantic and (args.check or args.update_baseline):
        parser.error("--check/--update-baseline apply to --hermetic, not --profile-semantic")
    if args.profile_semantic and args.record:
        parser.error("--record is incompatible with --profile-semantic (no repo-side writes)")
    if args.profile_runs < 2:
        parser.error("--profile-runs requires >= 2 (a single pass cannot observe instability)")

    # Normalize every output path BEFORE a possible chdir into the hermetic
    # tmp — relative paths would otherwise land inside the scratch dir.
    json_out = args.json_out.resolve() if args.json_out else None
    baseline_path = args.baseline.resolve()
    profile_out = args.profile_out.resolve()

    eval_file = args.file if args.file.is_absolute() else ROOT / args.file
    entries = yaml.safe_load(eval_file.read_text(encoding="utf-8"))

    if args.profile_semantic:
        try:
            return _run_profile(
                entries=entries,
                eval_file=eval_file,
                n_passes=args.profile_runs,
                profile_out=profile_out,
            )
        except ProfileUnavailableError as exc:
            print(f"PROFILE NOT RUN (do not fake a profile): {exc}", file=sys.stderr)
            return 2

    skill_roots: dict[str, Path] | None = None
    if args.hermetic:
        router, skill_roots, pinned_ids = _build_hermetic_router()
        builtin_ids = external_ids = pinned_ids
    else:
        router = UnifiedRouter(project_root=ROOT)
        builtin_ids, external_ids = _load_resolvable_ids()

    skipped_env_count = 0
    hits1 = hits3 = 0
    n_pos = n_neg = 0
    over_reject = over_inject = 0
    n_near_miss = near_miss_over_inject = 0
    no_match_count = 0
    no_match_by_layer: dict[str, int] = {}
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

        category = e.get("category")
        if category == "must_not_inject":
            # No real skill. FALLBACK_LLM is the router's no-match sentinel
            # (has_match is False); a real skill id is a fail.
            ok1 = not result.has_match
        else:
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
        # Two-sided error counts (report-only). skipped_env entries never
        # reach this point, so they pollute neither side of the confusion.
        if expect:
            n_pos += 1
            if not result.has_match:
                over_reject += 1
        if category == "must_not_inject" or (not expect and not reject):
            n_neg += 1
        if category in ("must_not_inject", "near_miss") and result.has_match:
            over_inject += 1
        if e.get("subclass") == "near_miss" or category == "near_miss":
            n_near_miss += 1
            if result.has_match:
                near_miss_over_inject += 1
        if result.has_match:
            no_match_by_layer[layer] = no_match_by_layer.get(layer, 0) + 1
        else:
            no_match_count += 1
        baseline_records.append(
            {
                "query": query,
                "expect": expect,
                "reject": reject,
                "primary": primary,
                "layer": layer,
                "ok1": bool(ok1),
                "category": category,
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
    no_match_by_layer["no_match"] = no_match_count
    no_match_rate = round(no_match_count / total, 4) if total else 0.0
    metrics = {
        "total": total,
        "skipped_env": skipped_env_count,
        "top1_accuracy": round(hits1 / total, 4) if total else 0.0,
        "recall_at_3": round(hits3 / total, 4) if total else 0.0,
        "errors": errors,
        "confusion_pairs": confusion,
        "n_pos": n_pos,
        "n_neg": n_neg,
        "over_reject": over_reject,
        "over_inject": over_inject,
        "no_match_by_layer": no_match_by_layer,
        "no_match_rate": no_match_rate,
        "n_near_miss": n_near_miss,
        "near_miss_over_inject": near_miss_over_inject,
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
        print(
            f"two-sided: pos {n_pos} (over-reject {over_reject}) | neg {n_neg} "
            f"(over-inject {over_inject}) | near-miss {n_near_miss} "
            f"(over-inject {near_miss_over_inject})"
        )
        print(
            f"no-match by layer: {json.dumps(no_match_by_layer)} | "
            f"no-match rate: {no_match_rate:.1%}"
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
        must_not_inject_fails = [
            r
            for r in baseline_records
            if r.get("category") == "must_not_inject" and not r.get("ok1")
        ]
        if must_not_inject_fails:
            print(
                "\nREFUSED: must_not_inject entries must pass (ok1 true); "
                "--force cannot absorb these:",
                file=sys.stderr,
            )
            for rec in must_not_inject_fails:
                print(
                    f"  {rec['query'][:60]!r}: {rec.get('primary')} ({rec.get('layer')})",
                    file=sys.stderr,
                )
            return 1
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
