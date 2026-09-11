"""Tests for scripts/eval_routing.py skipped_env handling (gate38).

The skipped_env predicate keeps pack-dependent entries (annotated with
``requires_packs``) out of the scored denominator and the errors list when
the pack is not installed in the eval environment — without ever hiding a
real regression for unannotated entries.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "eval_routing.py"
spec = importlib.util.spec_from_file_location("eval_routing", SCRIPT)
evr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evr)

EXTENDED_YAML = ROOT / "tests" / "benchmark" / "routing_eval_extended.yaml"
REGISTRY_YAML = ROOT / "core" / "registry.yaml"


def _fake_router(responses: dict[str, tuple[str | None, bool]]):
    """UnifiedRouter stand-in: query -> (primary skill_id, has_match)."""

    class FakeRouter:
        def __init__(self, project_root):
            pass

        def route(self, query, record_telemetry=False):
            primary_id, has_match = responses.get(query, (None, False))
            primary = (
                SimpleNamespace(
                    skill_id=primary_id,
                    layer=SimpleNamespace(value="lexical"),
                    confidence=0.9,
                )
                if primary_id
                else None
            )
            return SimpleNamespace(primary=primary, alternatives=[], has_match=has_match)

    return FakeRouter


def _run_eval(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    entries: list[dict],
    *,
    resolvable: tuple[set[str] | None, set[str] | None] = (set(), set()),
    responses: dict[str, tuple[str | None, bool]] | None = None,
) -> tuple[int, dict]:
    dataset = tmp_path / "eval.yaml"
    dataset.write_text(yaml.safe_dump(entries, allow_unicode=True), encoding="utf-8")
    out = tmp_path / "out.json"
    monkeypatch.setattr(evr, "UnifiedRouter", _fake_router(responses or {}))
    monkeypatch.setattr(evr, "_load_resolvable_ids", lambda: resolvable)
    monkeypatch.setattr(
        sys,
        "argv",
        ["eval_routing.py", "--file", str(dataset), "--json-out", str(out)],
    )
    rc = evr.main()
    return rc, json.loads(out.read_text(encoding="utf-8"))


def test_skipped_env_excluded_from_denominator_and_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    entries = [
        {"query": "hit", "expect": ["builtin/session-end"]},
        {
            "query": "pack miss",
            "expect": ["omx/git-master"],
            "requires_packs": ["omx"],
        },
    ]
    rc, m = _run_eval(
        monkeypatch,
        tmp_path,
        entries,
        resolvable=({"builtin/session-end"}, set()),  # omx pack absent
        responses={"hit": ("builtin/session-end", True), "pack miss": ("other/thing", True)},
    )
    assert rc == 0
    assert m["total"] == 1
    assert m["skipped_env"] == 1
    assert m["top1_accuracy"] == 1.0
    assert m["recall_at_3"] == 1.0
    # The skipped row would have been a misroute; it must NOT enter errors.
    assert m["errors"] == []

    skipped_rows = [r for r in m["per_query"] if r["query"] == "pack miss"]
    assert len(skipped_rows) == 1
    assert skipped_rows[0]["ok1"] is None
    assert skipped_rows[0]["skipped_env"] is True
    scored_rows = [r for r in m["per_query"] if r["query"] == "hit"]
    assert scored_rows[0]["ok1"] is True
    assert scored_rows[0]["skipped_env"] is False


def test_unannotated_misroute_still_counts_as_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """must-NOT: a pack-dependent entry WITHOUT requires_packs is scored
    normally — skipping is opt-in via the annotation only."""
    entries = [{"query": "pack miss", "expect": ["omx/git-master"]}]
    rc, m = _run_eval(
        monkeypatch,
        tmp_path,
        entries,
        resolvable=(set(), set()),
        responses={"pack miss": ("other/thing", True)},
    )
    assert rc == 0
    assert m["total"] == 1
    assert m["skipped_env"] == 0
    assert m["top1_accuracy"] == 0.0
    assert len(m["errors"]) == 1


def test_presence_check_failure_counts_as_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """If the resolvability probe itself raises (None sources), every id
    counts as resolvable — annotated entries are scored (possibly as false
    errors), never silently skipped."""
    entries = [
        {
            "query": "pack miss",
            "expect": ["omx/git-master"],
            "requires_packs": ["omx"],
        }
    ]
    rc, m = _run_eval(
        monkeypatch,
        tmp_path,
        entries,
        resolvable=(None, None),
        responses={"pack miss": ("other/thing", True)},
    )
    assert rc == 0
    assert m["skipped_env"] == 0
    assert m["total"] == 1
    assert len(m["errors"]) == 1


def test_empty_expect_with_requires_packs_is_not_skipped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """all([]) is True — an annotated no-match/reject assertion (expect: [])
    must never be treated as skipped_env."""
    entries = [
        {
            "query": "neg",
            "expect": [],
            "reject": ["omx/git-master"],
            "requires_packs": ["omx"],
        }
    ]
    rc, m = _run_eval(
        monkeypatch,
        tmp_path,
        entries,
        resolvable=(set(), set()),
        responses={"neg": (None, False)},
    )
    assert rc == 0
    assert m["skipped_env"] == 0
    assert m["total"] == 1
    assert m["top1_accuracy"] == 1.0


def test_all_skipped_aggregates_without_zero_division(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    entries = [
        {"query": "a", "expect": ["omx/git-master"], "requires_packs": ["omx"]},
        {
            "query": "b",
            "expect": ["superpowers/using-git-worktrees"],
            "requires_packs": ["superpowers"],
        },
    ]
    rc, m = _run_eval(monkeypatch, tmp_path, entries, resolvable=(set(), set()))
    assert rc == 0
    assert m["total"] == 0
    assert m["skipped_env"] == 2
    assert m["top1_accuracy"] == 0.0
    assert m["recall_at_3"] == 0.0
    assert m["errors"] == []


def test_exit_code_always_zero_with_errors(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Report-only contract: misroutes never change the exit code."""
    entries = [{"query": "miss", "expect": ["builtin/session-end"]}]
    rc, m = _run_eval(
        monkeypatch,
        tmp_path,
        entries,
        resolvable=(set(), set()),
        responses={"miss": ("other/thing", True)},
    )
    assert rc == 0
    assert len(m["errors"]) == 1


def test_partially_resolvable_expect_is_scored(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Skip requires ALL expect ids unresolvable; one resolvable id keeps
    the entry scored."""
    entries = [
        {
            "query": "multi",
            "expect": ["omx/git-master", "builtin/session-end"],
            "requires_packs": ["omx"],
        }
    ]
    rc, m = _run_eval(
        monkeypatch,
        tmp_path,
        entries,
        resolvable=({"builtin/session-end"}, set()),
        responses={"multi": ("builtin/session-end", True)},
    )
    assert rc == 0
    assert m["skipped_env"] == 0
    assert m["top1_accuracy"] == 1.0


def test_two_sided_error_counts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Direction D report-only counts: 1 pos hit + 1 pos over-reject +
    1 must_not_inject over-inject + 1 must_not_inject correctly rejected
    pin all four confusion counters (and the exit code stays 0)."""
    entries = [
        {"query": "pos hit", "expect": ["builtin/session-end"]},
        {"query": "pos over-reject", "expect": ["builtin/session-end"]},
        {"query": "neg over-inject", "expect": [], "category": "must_not_inject"},
        {"query": "neg ok", "expect": [], "category": "must_not_inject"},
    ]
    rc, m = _run_eval(
        monkeypatch,
        tmp_path,
        entries,
        resolvable=({"builtin/session-end"}, set()),
        responses={
            "pos hit": ("builtin/session-end", True),
            "pos over-reject": (None, False),
            "neg over-inject": ("builtin/session-end", True),
            "neg ok": (None, False),
        },
    )
    assert rc == 0
    assert m["n_pos"] == 2
    assert m["over_reject"] == 1
    assert m["n_neg"] == 2
    assert m["over_inject"] == 1
    # FakeRouter reports layer "lexical" whenever primary exists.
    assert m["no_match_by_layer"] == {"lexical": 2, "no_match": 2}
    assert m["no_match_rate"] == 0.5
    assert m["n_near_miss"] == 0
    assert m["near_miss_over_inject"] == 0


def test_skipped_env_excluded_from_two_sided_counts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """skipped_env entries stay out of the denominator AND out of n_pos
    (and cannot leak into n_neg either — they are never routed)."""
    entries = [
        {"query": "scored", "expect": ["builtin/session-end"]},
        {
            "query": "pack miss",
            "expect": ["omx/git-master"],
            "requires_packs": ["omx"],
        },
    ]
    rc, m = _run_eval(
        monkeypatch,
        tmp_path,
        entries,
        resolvable=({"builtin/session-end"}, set()),  # omx pack absent
        responses={"scored": ("builtin/session-end", True)},
    )
    assert rc == 0
    assert m["total"] == 1
    assert m["skipped_env"] == 1
    assert m["n_pos"] == 1
    assert m["over_reject"] == 0
    assert m["n_neg"] == 0


def test_near_miss_sublayer_counts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """near_miss is negative-for-injection in both spellings —
    `category: near_miss` and `subclass: near_miss` under must_not_inject —
    and always lands in n_neg via the empty-expect no-match clause."""
    entries = [
        {"query": "nm injected", "expect": [], "category": "near_miss"},
        {
            "query": "nm rejected",
            "expect": [],
            "category": "must_not_inject",
            "subclass": "near_miss",
        },
    ]
    rc, m = _run_eval(
        monkeypatch,
        tmp_path,
        entries,
        responses={
            "nm injected": ("builtin/session-end", True),
            "nm rejected": (None, False),
        },
    )
    assert rc == 0
    assert m["n_near_miss"] == 2
    assert m["near_miss_over_inject"] == 1
    assert m["over_inject"] == 1
    assert m["n_neg"] == 2


def test_extended_yaml_requires_packs_namespaces_valid() -> None:
    """Hand-edited annotations must reference namespaces declared in
    core/registry.yaml — pins against typos drifting the field away from
    the router's id space."""
    registry = yaml.safe_load(REGISTRY_YAML.read_text(encoding="utf-8"))
    namespaces = set(registry.get("namespaces", {}))
    entries = yaml.safe_load(EXTENDED_YAML.read_text(encoding="utf-8"))

    annotated = [e for e in entries if e.get("requires_packs")]
    assert annotated, "extended set lost its requires_packs annotations"
    for e in annotated:
        for ns in e["requires_packs"]:
            assert ns in namespaces, f"{e['query']!r}: unknown pack {ns!r}"
        # The annotation must match the namespace the expect ids actually
        # live in (a wrong-but-valid namespace would silently mis-skip).
        for sid in e.get("expect", []):
            prefix = sid.split("/", 1)[0]
            assert prefix in namespaces, f"{e['query']!r}: unknown expect namespace {prefix!r}"
            assert prefix in e["requires_packs"], (
                f"{e['query']!r}: expect {sid!r} not covered by requires_packs"
            )


# ---------------------------------------------------------------------------
# --profile-semantic (lane A): aggregation + control-group contract. These
# tests NEVER load a real embedding model — the routers are fakes and the
# real builder/preflight are monkeypatched out.
# ---------------------------------------------------------------------------


class _CyclingRouter:
    """Router stand-in whose response per query cycles through a fixed list
    across successive route() calls — one "flaky" observation per pass."""

    def __init__(self, cycles: dict[str, list[tuple[str | None, bool]]]) -> None:
        self._cycles = cycles
        self._calls: dict[str, int] = {}

    def route(self, query: str, record_telemetry: bool = False):
        i = self._calls.get(query, 0)
        self._calls[query] = i + 1
        primary_id, has_match = self._cycles[query][i % len(self._cycles[query])]
        primary = (
            SimpleNamespace(
                skill_id=primary_id,
                layer=SimpleNamespace(value="embedding"),
                confidence=0.9,
            )
            if primary_id
            else None
        )
        return SimpleNamespace(primary=primary, alternatives=[], has_match=has_match)


def test_mode_stability_identical_series() -> None:
    assert evr._mode_stability(["a"] * 10) == (1.0, "a")
    assert evr._mode_stability([None] * 4) == (1.0, None)
    assert evr._mode_stability([]) == (0.0, None)


def test_mode_stability_mixed_series() -> None:
    stab, mode = evr._mode_stability(["x"] * 7 + ["y"] * 3)
    assert stab == 0.7
    assert mode == "x"
    tie_stab, _ = evr._mode_stability(["x", "y"])
    assert tie_stab == 0.5


def test_aggregate_profile_means_histogram_and_unstable_counts() -> None:
    entries = [{"query": "stable"}, {"query": "flippy"}]
    passes = [
        [("a", "lexical"), ("b", "lexical")],
        [("a", "lexical"), ("c", "lexical")],
        [("a", "lexical"), ("b", "lexical")],
    ]
    agg = evr._aggregate_profile(passes, entries)
    assert agg["n_passes"] == 3
    assert agg["n_queries"] == 2
    assert agg["mean_primary_stability"] == round((1.0 + 2 / 3) / 2, 4)
    assert agg["unstable_primary_count"] == 1
    assert agg["unstable_layer_count"] == 0
    assert agg["primary_stability_histogram"] == {"1.0": 1, "0.6667": 1}
    unstable = [q for q in agg["per_query"] if q["primary_stability"] < 1.0]
    assert len(unstable) == 1
    assert unstable[0]["primary_mode"] == "b"
    assert unstable[0]["primary_counts"] == {"b": 2, "c": 1}


def test_control_group_must_be_exactly_stable() -> None:
    """The control contract: anything below exactly 1.0 blocks the profile —
    the harness would be measuring its own noise (falsification (a))."""
    entries = [{"query": "q"}]
    stable = evr._aggregate_profile([[("a", "lexical")]] * 3, entries)
    flaky = evr._aggregate_profile(
        [[("a", "lexical")], [("b", "lexical")], [("a", "lexical")]], entries
    )
    layer_flaky = evr._aggregate_profile(
        [[("a", "lexical")], [("a", "embedding")], [("a", "lexical")]], entries
    )
    assert evr._control_passes(stable)
    assert not evr._control_passes(flaky)
    # Layer instability alone also blocks — layer stability is a reported
    # metric, so the control must pin it too.
    assert not evr._control_passes(layer_flaky)


def _run_profile_with_fakes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    entries: list[dict],
    control: _CyclingRouter,
    semantic: _CyclingRouter,
    *,
    runs: int = 3,
    loader_calls: int = 1,
) -> dict:
    """Drive evr.main() in --profile-semantic mode with fake routers; returns
    the JSON artifact payload (asserts rc==0 and exactly one artifact pair)."""
    dataset = tmp_path / "profile_eval.yaml"
    dataset.write_text(yaml.safe_dump(entries, allow_unicode=True), encoding="utf-8")
    out_dir = tmp_path / "profile-out"
    roots = {"builtin": tmp_path / "builtin", "benchmark-pack": tmp_path / "pack"}
    for root in roots.values():
        root.mkdir()
        (root / "skill.md").write_text(f"# {root.name}\n", encoding="utf-8")

    def fake_builder(*, enable_embedding: bool):
        router = semantic if enable_embedding else control
        return router, roots, (lambda: loader_calls if enable_embedding else 0)

    monkeypatch.setattr(evr, "_build_profile_router", fake_builder)
    monkeypatch.setattr(evr, "_preflight_model", lambda model_name: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "eval_routing.py",
            "--profile-semantic",
            "--file",
            str(dataset),
            "--profile-runs",
            str(runs),
            "--profile-out",
            str(out_dir),
        ],
    )
    rc = evr.main()
    assert rc == 0, "profile mode is report-only: a successful run always exits 0"
    json_artifacts = sorted(out_dir.glob("semantic_profile_*.json"))
    assert len(json_artifacts) == 1
    md_artifacts = sorted(out_dir.glob("semantic_profile_*.md"))
    assert len(md_artifacts) == 1
    payload = json.loads(json_artifacts[0].read_text(encoding="utf-8"))
    assert payload["n_passes"] == runs
    assert json_artifacts[0].stem == md_artifacts[0].stem
    return payload


def test_profile_end_to_end_with_fake_routers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Full profile path (fakes): control deterministic -> control_pass;
    one flaky semantic query -> mean (1.0 + 2/3)/2; verdict PROFILE."""
    entries = [
        {"query": "q1", "expect": ["builtin/session-end"]},
        {"query": "q2", "expect": ["builtin/deep-diagnosis-optimization"]},
    ]
    control = _CyclingRouter({e["query"]: [("ctl", True)] for e in entries})
    semantic = _CyclingRouter(
        {
            "q1": [("builtin/session-end", True)],
            "q2": [
                ("builtin/other", True),
                ("builtin/session-end", True),
                ("builtin/other", True),
            ],
        }
    )
    payload = _run_profile_with_fakes(monkeypatch, tmp_path, entries, control, semantic)
    assert payload["control"]["control_pass"] is True
    assert payload["control"]["mean_primary_stability"] == 1.0
    assert payload["semantic"]["mean_primary_stability"] == round((1.0 + 2 / 3) / 2, 4)
    assert payload["semantic"]["unstable_primary_count"] == 1
    assert payload["semantic"]["embedding_loader_calls"] == 1
    assert payload["verdict"] == "PROFILE"
    # JSON contract from the lane spec: N, env pins, versions, threads.
    # (Field presence — with fake builders the pinning side effects never
    # run, so the recorded values here are honestly None.)
    assert payload["n_passes"] == 3
    for field in ("omp_num_threads_env", "hf_home", "torch", "sentence_transformers"):
        assert field in payload["env"]
    assert payload["posture"]["enable_embedding"] is True
    assert payload["posture"]["enable_ai_triage"] is False
    assert payload["model"]
    assert len(payload["fingerprint_sha"]) == 64


def test_profile_control_blocked_is_a_finding_not_a_gate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Control instability must surface as CONTROL_BLOCKED_HARNESS_NOISE with
    exit 0 — the report-only contract forbids turning it into a gate."""
    entries = [{"query": "q1", "expect": []}]
    control = _CyclingRouter({"q1": [("a", True), ("b", True), ("a", True)]})
    semantic = _CyclingRouter({"q1": [("s", True)]})
    payload = _run_profile_with_fakes(monkeypatch, tmp_path, entries, control, semantic)
    assert payload["control"]["control_pass"] is False
    assert payload["control"]["mean_primary_stability"] == round(2 / 3, 4)
    assert payload["verdict"] == "CONTROL_BLOCKED_HARNESS_NOISE"


def test_profile_invalid_when_embedding_never_loaded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Zero loader calls mean the "semantic" numbers are the deterministic
    path in disguise — flagged, never silently reported as a profile."""
    entries = [{"query": "q1", "expect": []}]
    stable = _CyclingRouter({"q1": [("s", True)]})
    payload = _run_profile_with_fakes(
        monkeypatch, tmp_path, entries, stable, stable, loader_calls=0
    )
    assert payload["semantic"]["embedding_loader_calls"] == 0
    assert payload["verdict"] == "PROFILE_INVALID_NO_EMBEDDING_LOAD"


def test_profile_semantic_mutually_exclusive_with_hermetic() -> None:
    sys.argv = ["eval_routing.py", "--profile-semantic", "--hermetic"]
    with pytest.raises(SystemExit) as exc:
        evr.main()
    assert exc.value.code == 2


def test_profile_preflight_offline_failure_raises_unavailable() -> None:
    """A model that cannot load offline raises ProfileUnavailableError (the
    profile must not run on the deterministic fallback path in disguise).
    Works both with sentence-transformers installed (offline cache miss) and
    without it (ImportError from the offline attempt)."""
    with pytest.raises(evr.ProfileUnavailableError):
        evr._preflight_model("definitely-not-cached-model")


def test_lazy_matcher_adapter_forwards_top_k() -> None:
    """The harness adapter forwards the pipeline's top_k kwarg 1:1 to the
    real matcher — the exact call the product pipeline makes and the exact
    TypeError the unadapted LazyEmbeddingMatcher raises today."""
    from vibesop.core.matching.lazy_matcher import LazyEmbeddingMatcher

    calls: dict[str, object] = {}

    class _Real:
        def match(self, query, candidates, context=None, top_k=10):
            calls["top_k"] = top_k
            return []

    lazy = LazyEmbeddingMatcher(config=None)
    lazy._real = _Real()  # type: ignore[assignment]
    adapter = evr._LazyMatcherAdapter(lazy)
    # The unadapted proxy would raise TypeError here.
    adapter.match("q", [], None, top_k=5)
    assert calls["top_k"] == 5
