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
