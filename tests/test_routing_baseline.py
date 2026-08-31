"""Hermetic routing baseline gate logic (gate45 P1).

Unit tests for the pure functions in vibesop.core.routing.benchmark —
fingerprint content-sensitivity and baseline compare/exit-code semantics.
The full harness determinism (HOME/HF/cwd A/B) is verified manually in
docs/dev/routing-benchmark.md, not here.
"""

from __future__ import annotations

import json
from pathlib import Path

from vibesop.core.routing.benchmark import (
    HERMETIC_POSTURE,
    check_update_absorption,
    compare_entries,
    compute_fingerprint,
    evaluate_against_baseline,
    write_baseline,
)


def _entry(query: str, ok1: bool, primary: str, layer: str = "keyword") -> dict:
    return {
        "query": query,
        "expect": [primary],
        "reject": [],
        "primary": primary,
        "layer": layer,
        "ok1": ok1,
    }


def _make_files(root: Path) -> tuple[Path, Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    registry = root / "registry.yaml"
    registry.write_text("skills: []\n", encoding="utf-8")
    dataset = root / "dataset.yaml"
    dataset.write_text("- query: q\n", encoding="utf-8")
    skills = root / "skills"
    (skills / "alpha").mkdir(parents=True, exist_ok=True)
    (skills / "alpha" / "SKILL.md").write_text("---\nid: alpha\n---\nbody\n", encoding="utf-8")
    return registry, dataset, skills


def _fingerprint(registry: Path, dataset: Path, skills: Path) -> dict:
    return compute_fingerprint(
        registry_file=registry,
        skill_roots={"builtin": skills},
        dataset_file=dataset,
        posture=HERMETIC_POSTURE,
    )


class TestComputeFingerprint:
    def test_touch_is_invisible_content_edit_is_visible(self, tmp_path: Path) -> None:
        registry, dataset, skills = _make_files(tmp_path)
        before = _fingerprint(registry, dataset, skills)

        (skills / "alpha" / "SKILL.md").touch()
        registry.touch()
        assert _fingerprint(registry, dataset, skills) == before  # mtime-insensitive

        (skills / "alpha" / "SKILL.md").write_text(
            "---\nid: alpha\n---\nchanged\n", encoding="utf-8"
        )
        after = _fingerprint(registry, dataset, skills)
        assert after != before
        assert (
            after["inputs"]["skills:builtin"]["alpha/SKILL.md"]
            != before["inputs"]["skills:builtin"]["alpha/SKILL.md"]
        )

    def test_absolute_location_is_invisible(self, tmp_path: Path) -> None:
        """CI checkout vs local clone must fingerprint identically."""
        import shutil

        registry, dataset, skills = _make_files(tmp_path / "src")
        a = tmp_path / "a" / "skills"
        b = tmp_path / "nested" / "deeper" / "b" / "skills"
        shutil.copytree(skills, a)
        shutil.copytree(skills, b)
        assert (
            _fingerprint(registry, dataset, a)["sha"] == _fingerprint(registry, dataset, b)["sha"]
        )

    def test_posture_change_invalidates(self, tmp_path: Path) -> None:
        registry, dataset, skills = _make_files(tmp_path)
        fp = compute_fingerprint(
            registry_file=registry,
            skill_roots={"builtin": skills},
            dataset_file=dataset,
            posture={**HERMETIC_POSTURE, "enable_embedding": True},
        )
        assert fp["sha"] != _fingerprint(registry, dataset, skills)["sha"]

    def test_crlf_checkout_fingerprints_identically(self, tmp_path: Path) -> None:
        """Windows autocrlf checkout: same content with CRLF bytes must hash
        identically to the LF checkout."""
        registry, dataset, skills = _make_files(tmp_path / "env-lf")
        # Force true LF bytes (write_text translates \n to os.linesep, so on
        # Windows the tree is already CRLF and the test would be vacuous).
        for path in (registry, dataset, skills / "alpha" / "SKILL.md"):
            path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
        lf_fp = _fingerprint(registry, dataset, skills)

        registry, dataset, skills = _make_files(tmp_path / "env-crlf")
        for path in (registry, dataset, skills / "alpha" / "SKILL.md"):
            # Normalize to LF first (write_text may already have emitted
            # CRLF on Windows), then rewrite every line ending as CRLF.
            content = path.read_bytes().replace(b"\r\n", b"\n")
            path.write_bytes(content.replace(b"\n", b"\r\n"))
        crlf_fp = _fingerprint(registry, dataset, skills)

        assert crlf_fp == lf_fp


class TestCompareEntries:
    def test_new_fail_exits_1(self) -> None:
        baseline = [_entry("q1", ok1=True, primary="s1")]
        current = [_entry("q1", ok1=False, primary="fallback-llm", layer="fallback_llm")]
        outcome = compare_entries(baseline, current)
        assert outcome.exit_code == 1
        assert len(outcome.new_fails) == 1
        assert outcome.new_fails[0]["baseline"] == "s1 (keyword)"
        assert outcome.new_fails[0]["current"] == "fallback-llm (fallback_llm)"

    def test_new_pass_exits_0(self) -> None:
        baseline = [_entry("q1", ok1=False, primary="fallback-llm", layer="fallback_llm")]
        current = [_entry("q1", ok1=True, primary="s1")]
        outcome = compare_entries(baseline, current)
        assert outcome.exit_code == 0
        assert len(outcome.new_passes) == 1

    def test_pass_with_primary_drift_warns_but_exits_0(self) -> None:
        baseline = [_entry("q1", ok1=True, primary="s1", layer="keyword")]
        current = [_entry("q1", ok1=True, primary="s1", layer="tfidf")]
        outcome = compare_entries(baseline, current)
        assert outcome.exit_code == 0
        assert not outcome.new_fails
        assert len(outcome.drift_warnings) == 1

    def test_known_fail_stays_silent(self) -> None:
        baseline = [_entry("q1", ok1=False, primary="fallback-llm", layer="fallback_llm")]
        current = [_entry("q1", ok1=False, primary="fallback-llm", layer="fallback_llm")]
        outcome = compare_entries(baseline, current)
        assert outcome.exit_code == 0
        assert not outcome.new_fails and not outcome.new_passes and not outcome.drift_warnings
        assert outcome.known_fails == 1


class TestEvaluateAgainstBaseline:
    def _write(self, tmp_path: Path, tag: str, entries: list[dict]) -> tuple[Path, dict]:
        registry, dataset, skills = _make_files(tmp_path / f"env-{tag}")
        fp = _fingerprint(registry, dataset, skills)
        path = tmp_path / f"baseline-{tag}.json"
        write_baseline(path, fp, entries)
        return path, fp

    def test_matching_fingerprint_passes(self, tmp_path: Path) -> None:
        path, fp = self._write(tmp_path, "a", [_entry("q1", ok1=True, primary="s1")])
        outcome = evaluate_against_baseline(path, fp, [_entry("q1", ok1=True, primary="s1")])
        assert outcome.exit_code == 0

    def test_missing_baseline_exits_3(self, tmp_path: Path) -> None:
        _, fp = self._write(tmp_path, "a", [])
        outcome = evaluate_against_baseline(tmp_path / "nope.json", fp, [])
        assert outcome.exit_code == 3 and outcome.stale

    def test_fingerprint_mismatch_exits_3_before_entry_compare(self, tmp_path: Path) -> None:
        # Baseline recorded a pass; current run has a new FAIL — but the
        # dataset content also changed, so the gate must report "stale"
        # (refresh), never compare across universes.
        path, fp = self._write(tmp_path, "a", [_entry("q1", ok1=True, primary="s1")])
        tampered = {**fp, "sha": "0" * 64}
        outcome = evaluate_against_baseline(path, tampered, [_entry("q1", ok1=False, primary="x")])
        assert outcome.exit_code == 3 and outcome.stale
        assert not outcome.new_fails

    def test_schema_version_mismatch_exits_3(self, tmp_path: Path) -> None:
        path, fp = self._write(tmp_path, "a", [_entry("q1", ok1=True, primary="s1")])
        data = json.loads(path.read_text(encoding="utf-8"))
        data["version"] = 999
        path.write_text(json.dumps(data), encoding="utf-8")
        outcome = evaluate_against_baseline(path, fp, [])
        assert outcome.exit_code == 3

    def test_unreadable_baseline_exits_3(self, tmp_path: Path) -> None:
        _, fp = self._write(tmp_path, "a", [])
        path = tmp_path / "corrupt.json"
        path.write_text("not json at all", encoding="utf-8")
        outcome = evaluate_against_baseline(path, fp, [])
        assert outcome.exit_code == 3

    def test_non_dict_fingerprint_exits_3_not_traceback(self, tmp_path: Path) -> None:
        """Valid JSON with a wrong-typed fingerprint is unreadable, not a crash."""
        path, fp = self._write(tmp_path, "a", [_entry("q1", ok1=True, primary="s1")])
        data = json.loads(path.read_text(encoding="utf-8"))
        data["fingerprint"] = "not-a-dict"
        path.write_text(json.dumps(data), encoding="utf-8")
        outcome = evaluate_against_baseline(path, fp, [])
        assert outcome.exit_code == 3 and outcome.stale

    def test_malformed_entries_exit_3_not_traceback(self, tmp_path: Path) -> None:
        """Entries that are not a list of dicts with 'query' are unreadable."""
        path, fp = self._write(tmp_path, "a", [_entry("q1", ok1=True, primary="s1")])
        data = json.loads(path.read_text(encoding="utf-8"))
        data["entries"] = [{"no_query": True}]
        path.write_text(json.dumps(data), encoding="utf-8")
        outcome = evaluate_against_baseline(path, fp, [_entry("q1", ok1=True, primary="s1")])
        assert outcome.exit_code == 3 and outcome.stale

        data["entries"] = "not-a-list"
        path.write_text(json.dumps(data), encoding="utf-8")
        outcome = evaluate_against_baseline(path, fp, [])
        assert outcome.exit_code == 3 and outcome.stale

    def test_non_string_query_exits_3_not_traceback(self, tmp_path: Path) -> None:
        """A list/dict ``query`` is unhashable — the dict comprehension in
        compare_entries would raise TypeError, so it counts as malformed."""
        path, fp = self._write(tmp_path, "a", [_entry("q1", ok1=True, primary="s1")])
        data = json.loads(path.read_text(encoding="utf-8"))
        for bad_query in (["a"], {"x": 1}):
            data["entries"] = [{"query": bad_query, "ok1": True, "primary": "s1"}]
            path.write_text(json.dumps(data), encoding="utf-8")
            outcome = evaluate_against_baseline(path, fp, [_entry("q1", ok1=True, primary="s1")])
            assert outcome.exit_code == 3 and outcome.stale, bad_query

    def test_malformed_reason_names_the_malformed_side(self, tmp_path: Path) -> None:
        """Malformed BASELINE entries coach --update-baseline; malformed
        CURRENT entries come from the benchmark's own run — a baseline
        refresh cannot heal them, so the message must not suggest one."""
        path, fp = self._write(tmp_path, "a", [_entry("q1", ok1=True, primary="s1")])

        current_bad = evaluate_against_baseline(path, fp, [{"no_query": True}])
        assert current_bad.exit_code == 3 and current_bad.stale
        assert "current" in current_bad.reason
        assert "--update-baseline" not in current_bad.reason

        data = json.loads(path.read_text(encoding="utf-8"))
        data["entries"] = [{"no_query": True}]
        path.write_text(json.dumps(data), encoding="utf-8")
        baseline_bad = evaluate_against_baseline(path, fp, [_entry("q1", ok1=True, primary="s1")])
        assert baseline_bad.exit_code == 3 and baseline_bad.stale
        assert "baseline" in baseline_bad.reason
        assert "--update-baseline" in baseline_bad.reason


class TestCheckUpdateAbsorption:
    """Pre-refresh guard (review F-1): refresh must not launder regressions."""

    def test_absorbing_a_regression_is_flagged(self, tmp_path: Path) -> None:
        path, _fp = self._write(tmp_path, [_entry("q1", ok1=True, primary="s1")])
        # Fingerprint deliberately NOT checked: absorption matters exactly
        # when the fingerprint changed alongside the regression.
        guard = check_update_absorption(path, [_entry("q1", ok1=False, primary="x")])
        assert guard is not None and guard.exit_code == 1
        assert len(guard.new_fails) == 1

    def test_clean_refresh_is_allowed(self, tmp_path: Path) -> None:
        path, _ = self._write(tmp_path, [_entry("q1", ok1=True, primary="s1")])
        guard = check_update_absorption(path, [_entry("q1", ok1=True, primary="s1")])
        assert guard is not None and guard.exit_code == 0

    def test_newly_passing_flip_is_not_a_refusal(self, tmp_path: Path) -> None:
        path, _ = self._write(tmp_path, [_entry("q1", ok1=False, primary="x")])
        guard = check_update_absorption(path, [_entry("q1", ok1=True, primary="s1")])
        assert guard is not None and guard.exit_code == 0
        assert len(guard.new_passes) == 1

    def test_first_refresh_has_nothing_to_compare(self, tmp_path: Path) -> None:
        guard = check_update_absorption(tmp_path / "nope.json", [])
        assert guard is None

    def test_incompatible_old_baseline_is_ignored(self, tmp_path: Path) -> None:
        path, _ = self._write(tmp_path, [_entry("q1", ok1=True, primary="s1")])
        data = json.loads(path.read_text(encoding="utf-8"))
        data["version"] = 999
        path.write_text(json.dumps(data), encoding="utf-8")
        assert check_update_absorption(path, []) is None

    @staticmethod
    def _write(tmp_path: Path, entries: list[dict]) -> tuple[Path, dict]:
        registry, dataset, skills = _make_files(tmp_path / "env-guard")
        fp = _fingerprint(registry, dataset, skills)
        path = tmp_path / "baseline-guard.json"
        write_baseline(path, fp, entries)
        return path, fp


class TestWriteBaseline:
    def test_round_trip_is_deterministic(self, tmp_path: Path) -> None:
        registry, dataset, skills = _make_files(tmp_path)
        fp = _fingerprint(registry, dataset, skills)
        entries = [_entry("q1", ok1=True, primary="s1")]
        p1, p2 = tmp_path / "b1.json", tmp_path / "b2.json"
        write_baseline(p1, fp, entries)
        write_baseline(p2, fp, entries)
        assert p1.read_bytes() == p2.read_bytes()
        loaded = json.loads(p1.read_text(encoding="utf-8"))
        assert loaded["fingerprint"]["sha"] == fp["sha"]
        assert loaded["entries"] == entries
