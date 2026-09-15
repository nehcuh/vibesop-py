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
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    import pytest

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


_CHECK_FINGERPRINT = {"version": 1, "sha": "0" * 64, "inputs": {}}


def _run_eval_check(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    entries: list[dict],
    *,
    baseline_entries: list[dict],
    responses: dict[str, tuple[str | None, bool]] | None = None,
) -> tuple[int, dict]:
    """Hermetic --check against a temp baseline; fingerprint is canned.

    Production YAML/baseline are never read. Two-sided counters still
    accumulate from ``entries``; the gate uses ``baseline_records`` only.
    """
    tmp_path.mkdir(parents=True, exist_ok=True)
    dataset = tmp_path / "eval.yaml"
    dataset.write_text(yaml.safe_dump(entries, allow_unicode=True), encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(
            {
                "version": 1,
                "fingerprint": _CHECK_FINGERPRINT,
                "entries": baseline_entries,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    out = tmp_path / "out.json"
    monkeypatch.setattr(evr, "UnifiedRouter", _fake_router(responses or {}))
    monkeypatch.setattr(
        evr,
        "_build_hermetic_router",
        lambda: (_fake_router(responses or {})(None), {"builtin": tmp_path}, set()),
    )
    monkeypatch.setattr(evr, "compute_fingerprint", lambda **_kw: _CHECK_FINGERPRINT)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "eval_routing.py",
            "--hermetic",
            "--check",
            "--file",
            str(dataset),
            "--baseline",
            str(baseline),
            "--json-out",
            str(out),
        ],
    )
    rc = evr.main()
    return rc, json.loads(out.read_text(encoding="utf-8"))


def _run_eval_update(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    entries: list[dict],
    *,
    responses: dict[str, tuple[str | None, bool]] | None = None,
) -> tuple[int, Path]:
    """Hermetic --update-baseline against a missing temp baseline.

    Isolates the must_not_inject hard-refuse: no prior baseline means
    check_update_absorption returns None, and --force is unused.
    """
    tmp_path.mkdir(parents=True, exist_ok=True)
    dataset = tmp_path / "eval.yaml"
    dataset.write_text(yaml.safe_dump(entries, allow_unicode=True), encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    monkeypatch.setattr(evr, "UnifiedRouter", _fake_router(responses or {}))
    monkeypatch.setattr(
        evr,
        "_build_hermetic_router",
        lambda: (_fake_router(responses or {})(None), {"builtin": tmp_path}, set()),
    )
    monkeypatch.setattr(evr, "compute_fingerprint", lambda **_kw: _CHECK_FINGERPRINT)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "eval_routing.py",
            "--hermetic",
            "--update-baseline",
            "--file",
            str(dataset),
            "--baseline",
            str(baseline),
        ],
    )
    rc = evr.main()
    return rc, baseline


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
    assert m["routing_outcomes_by_layer"] == {"lexical": 2, "no_match": 2}
    assert "no_match_by_layer" not in m
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


def test_bare_nomatch_over_inject_increments_n_neg_and_over_inject(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Empty expect + no reject is an explicit no-match negative; injecting
    a real skill must close both n_neg and over_inject."""
    entries = [{"query": "bare inject", "expect": []}]
    rc, m = _run_eval(
        monkeypatch,
        tmp_path,
        entries,
        responses={"bare inject": ("builtin/session-end", True)},
    )
    assert rc == 0
    assert m["n_pos"] == 0
    assert m["n_neg"] == 1
    assert m["over_inject"] == 1
    assert m["over_reject"] == 0
    assert m["n_near_miss"] == 0
    assert m["near_miss_over_inject"] == 0


def test_subclass_only_near_miss_over_inject_is_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """subclass: near_miss without category: near_miss still counts as
    negative; over_inject and near_miss_over_inject stay nested."""
    entries = [
        {
            "query": "subclass inject",
            "expect": [],
            "reject": ["builtin/session-end"],
            "subclass": "near_miss",
        }
    ]
    rc, m = _run_eval(
        monkeypatch,
        tmp_path,
        entries,
        responses={"subclass inject": ("builtin/session-end", True)},
    )
    assert rc == 0
    assert m["n_pos"] == 0
    assert m["n_neg"] == 1
    assert m["over_inject"] == 1
    assert m["n_near_miss"] == 1
    assert m["near_miss_over_inject"] == 1
    assert m["near_miss_over_inject"] <= m["over_inject"]


def test_negative_label_precedes_nonempty_expect(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A must_not_inject row with a leftover expect is classified once as
    negative, not as both n_pos and n_neg."""
    entries = [
        {
            "query": "conflict",
            "expect": ["builtin/session-end"],
            "category": "must_not_inject",
        }
    ]
    rc, m = _run_eval(
        monkeypatch,
        tmp_path,
        entries,
        resolvable=({"builtin/session-end"}, set()),
        responses={"conflict": ("builtin/session-end", True)},
    )
    assert rc == 0
    assert m["n_pos"] == 0
    assert m["n_neg"] == 1
    assert m["over_inject"] == 1
    assert m["over_reject"] == 0
    assert m["n_pos"] + m["n_neg"] == 1


def test_report_only_counters_do_not_change_check_exit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Nonzero two-sided counters are invisible to --check. Matching
    baseline_records → exit 0; an ok1 true→false flip → exit 1. Temp
    YAML + baseline only; production files are not read."""
    entries = [
        {"query": "pos hit", "expect": ["builtin/session-end"]},
        {"query": "neg inject", "expect": [], "category": "must_not_inject"},
        {"query": "pos miss", "expect": ["builtin/session-end"]},
    ]
    responses = {
        "pos hit": ("builtin/session-end", True),
        "neg inject": ("builtin/session-end", True),
        "pos miss": (None, False),
    }
    matching_baseline = [
        {
            "query": "pos hit",
            "expect": ["builtin/session-end"],
            "reject": [],
            "primary": "builtin/session-end",
            "layer": "lexical",
            "ok1": True,
            "category": None,
        },
        {
            "query": "neg inject",
            "expect": [],
            "reject": [],
            "primary": "builtin/session-end",
            "layer": "lexical",
            "ok1": False,
            "category": "must_not_inject",
        },
        {
            "query": "pos miss",
            "expect": ["builtin/session-end"],
            "reject": [],
            "primary": None,
            "layer": None,
            "ok1": False,
            "category": None,
        },
    ]
    rc0, m0 = _run_eval_check(
        monkeypatch,
        tmp_path / "ok",
        entries,
        baseline_entries=matching_baseline,
        responses=responses,
    )
    assert rc0 == 0
    assert m0["over_inject"] == 1
    assert m0["over_reject"] == 1
    assert m0["n_pos"] == 2
    assert m0["n_neg"] == 1

    flipped = [dict(row) for row in matching_baseline]
    flipped[2] = {**flipped[2], "ok1": True, "primary": "builtin/session-end", "layer": "lexical"}
    rc1, m1 = _run_eval_check(
        monkeypatch,
        tmp_path / "fail",
        entries,
        baseline_entries=flipped,
        responses=responses,
    )
    assert rc1 == 1
    assert m1["over_inject"] == m0["over_inject"]
    assert m1["over_reject"] == m0["over_reject"]
    assert m1["n_pos"] == m0["n_pos"]
    assert m1["n_neg"] == m0["n_neg"]


def test_reject_only_outside_binary_denom_stays_in_total_and_no_match_rate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Reject-only rows stay outside n_pos/n_neg but remain in total, so
    no_match_rate is no_match/total — not no_match/(n_pos+n_neg)."""
    entries = [
        {"query": "pos hit", "expect": ["builtin/session-end"]},
        {
            "query": "reject only",
            "expect": [],
            "reject": ["builtin/session-end"],
        },
    ]
    rc, m = _run_eval(
        monkeypatch,
        tmp_path,
        entries,
        resolvable=({"builtin/session-end"}, set()),
        responses={
            "pos hit": ("builtin/session-end", True),
            "reject only": (None, False),
        },
    )
    assert rc == 0
    assert m["n_pos"] == 1
    assert m["n_neg"] == 0
    assert m["total"] == 2
    assert m["n_pos"] + m["n_neg"] == 1
    # 1 no-match / 2 scored; dividing by n_pos+n_neg would yield 1.0.
    assert m["no_match_rate"] == 0.5
    assert m["routing_outcomes_by_layer"] == {"lexical": 1, "no_match": 1}
    assert "no_match_by_layer" not in m


def test_near_miss_outside_must_not_inject_hard_refuse(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """category: near_miss with ok1 false is not absorbed into the
    must_not_inject hard-refuse list; a must_not_inject fail still refuses."""
    near_miss_entries = [
        {"query": "nm injected", "expect": [], "category": "near_miss"},
    ]
    rc_nm, baseline_nm = _run_eval_update(
        monkeypatch,
        tmp_path / "near-miss",
        near_miss_entries,
        responses={"nm injected": ("builtin/session-end", True)},
    )
    assert rc_nm == 0
    assert baseline_nm.exists()
    written = json.loads(baseline_nm.read_text(encoding="utf-8"))
    assert written["entries"][0]["category"] == "near_miss"
    assert written["entries"][0]["ok1"] is False

    hard_refuse_entries = [
        {"query": "neg inject", "expect": [], "category": "must_not_inject"},
    ]
    rc_hard, baseline_hard = _run_eval_update(
        monkeypatch,
        tmp_path / "hard-refuse",
        hard_refuse_entries,
        responses={"neg inject": ("builtin/session-end", True)},
    )
    assert rc_hard == 1
    assert not baseline_hard.exists()


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


def test_json_out_metrics_carry_provenance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """8.5: dataset/hermetic/generated_at are additive provenance keys so
    consumers can reject a stale or non-hermetic eval payload."""
    from datetime import datetime

    entries = [{"query": "hit", "expect": ["builtin/session-end"]}]
    rc, m = _run_eval(
        monkeypatch,
        tmp_path,
        entries,
        resolvable=({"builtin/session-end"}, set()),
        responses={"hit": ("builtin/session-end", True)},
    )
    assert rc == 0
    assert m["dataset"].endswith("eval.yaml")
    assert m["hermetic"] is False
    assert datetime.fromisoformat(m["generated_at"]).tzinfo is not None


def test_json_stdout_metrics_carry_provenance(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from datetime import datetime

    dataset = tmp_path / "eval.yaml"
    dataset.write_text(
        yaml.safe_dump([{"query": "hit", "expect": ["builtin/session-end"]}]),
        encoding="utf-8",
    )
    monkeypatch.setattr(evr, "UnifiedRouter", _fake_router({"hit": ("builtin/session-end", True)}))
    monkeypatch.setattr(evr, "_load_resolvable_ids", lambda: ({"builtin/session-end"}, set()))
    monkeypatch.setattr(sys, "argv", ["eval_routing.py", "--file", str(dataset), "--json"])
    rc = evr.main()
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dataset"] == str(dataset)
    assert payload["hermetic"] is False
    assert datetime.fromisoformat(payload["generated_at"]).tzinfo is not None


# ---------------------------------------------------------------------------
# Portable eval producer identity (8.5 provenance contract)
# ---------------------------------------------------------------------------


def test_dataset_identity_repo_relative_under_root() -> None:
    """The default dataset yields exactly the canonical portable identity."""
    default = evr.ROOT / "tests" / "benchmark" / "routing_eval.yaml"
    assert evr._dataset_identity(default) == "tests/benchmark/routing_eval.yaml"


def test_dataset_identity_collapses_repo_relative_path() -> None:
    weird = evr.ROOT / "tests" / "benchmark" / ".." / "benchmark" / "routing_eval.yaml"
    assert evr._dataset_identity(weird) == "tests/benchmark/routing_eval.yaml"


def test_dataset_identity_external_is_resolved_absolute(tmp_path: Path) -> None:
    external = tmp_path / "eval.yaml"
    external.write_text("[]", encoding="utf-8")
    identity = evr._dataset_identity(external)
    assert identity == str(external.resolve())
    assert not identity.startswith(str(evr.ROOT))
