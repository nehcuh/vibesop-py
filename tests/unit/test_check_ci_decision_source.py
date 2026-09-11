"""Tests for scripts/check_ci_decision_source.py (Lane B / B1 registry guard).

The guard's verdict is defined against two files, so every test here builds a
throwaway pair (a fixture workflow + a fixture registry) under ``tmp_path`` and
runs the CLI through ``main([...])``. The real ``.github/workflows/ci.yml`` is
only ever read — no test writes to it.

The fixture cases matter more than the happy path: the whole point of B1 is
that a job declaring a model-sourced verdict is red, so that case is asserted
against the process exit code (the contract CI consumes) and against the
problem code the guard emits.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_ci_decision_source.py"
spec = importlib.util.spec_from_file_location("check_ci_decision_source", SCRIPT)
assert spec and spec.loader
ccds = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ccds  # dataclasses need the module registered
spec.loader.exec_module(ccds)

REAL_REGISTRY = ROOT / "ci" / "decision-source.yaml"


def _job(
    job_id: str,
    *,
    name: str | None = None,
    condition: str | None = None,
    extra: str | None = None,
) -> str:
    """One workflow job block. `extra` adds raw job-level keys."""
    lines = [f"  {job_id}:", f"    name: {name or job_id}", "    runs-on: ubuntu-latest"]
    if condition is not None:
        lines.append(f"    if: {condition}")
    if extra is not None:
        lines.append(f"    {extra}")
    lines += ["    steps:", "      - run: uv run pytest -q"]
    return "\n".join(lines) + "\n"


def _workflow(*jobs: str) -> str:
    return "name: CI\non:\n  workflow_call:\njobs:\n" + "".join(jobs)


def _registry(jobs: dict[str, object]) -> str:
    return yaml.safe_dump({"schema_version": 1, "jobs": jobs}, sort_keys=False)


def _tree(tmp_path: Path, workflow: str, registry: str) -> Path:
    """Lay out a repo-shaped tree so the guard's default paths are exercised."""
    root = tmp_path / "repo"
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / "ci").mkdir(parents=True)
    (root / ".github" / "workflows" / "ci.yml").write_text(workflow, encoding="utf-8")
    (root / "ci" / "decision-source.yaml").write_text(registry, encoding="utf-8")
    return root


def _run(root: Path, *extra: str) -> int:
    return ccds.main(["--root", str(root), *extra])


def _codes(report: ccds.Report) -> list[str]:
    return [problem.code for problem in report.problems]


# --------------------------------------------------------------------------
# Real repository: the registry shipped with Lane B must cover the real ci.yml.
# --------------------------------------------------------------------------


def test_real_repo_registry_covers_real_ci_workflow(capsys: pytest.CaptureFixture[str]) -> None:
    """Default paths: 8/8 jobs registered, every source in the allowed domain."""
    assert ccds.main([]) == 0
    out = capsys.readouterr().out
    assert "8 workflow job(s), 8 registry entr(y/ies)" in out


def test_real_repo_guard_is_red_when_a_job_is_missing(tmp_path: Path) -> None:
    """The real workflow minus one registration is red — coverage is load-bearing."""
    workflow_doc = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    registry_doc = yaml.safe_load(REAL_REGISTRY.read_text(encoding="utf-8"))
    dropped = "routing-benchmark"
    del registry_doc["jobs"][dropped]

    root = _tree(
        tmp_path,
        yaml.safe_dump(workflow_doc, sort_keys=False),
        yaml.safe_dump(registry_doc, sort_keys=False),
    )
    assert _run(root) == 1
    report = ccds.check(root / ".github/workflows/ci.yml", root / "ci/decision-source.yaml")
    assert _codes(report) == ["unregistered_job"]


def test_real_workflow_with_a_model_job_injected_is_red(tmp_path: Path) -> None:
    """Cross-check against the real workflow content: a model gate is red.

    ci.yml is read, never written — the injected job lives in a throwaway copy.
    """
    workflow_doc = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    registry_doc = yaml.safe_load(REAL_REGISTRY.read_text(encoding="utf-8"))
    workflow_doc["jobs"]["llm-review"] = {
        "name": "LLM Review",
        "runs-on": "ubuntu-latest",
        "steps": [{"run": "uv run python scripts/llm_review.py"}],
    }
    registry_doc["jobs"]["llm-review"] = {
        "name": "LLM Review",
        "decision_source": "model",
    }

    root = _tree(
        tmp_path,
        yaml.safe_dump(workflow_doc, sort_keys=False),
        yaml.safe_dump(registry_doc, sort_keys=False),
    )
    assert _run(root) == 1
    report = ccds.check(root / ".github/workflows/ci.yml", root / "ci/decision-source.yaml")
    assert _codes(report) == ["model_decision_source_on_required_job"]


def test_real_registry_is_marked_as_a_draft() -> None:
    """Lane B ships a proposal, not a ratified ruling — the file must say so."""
    doc = yaml.safe_load(REAL_REGISTRY.read_text(encoding="utf-8"))
    assert doc["proposed_by"] == "grok"
    assert doc["pending_human_confirm"] is True
    assert doc["workflow"] == ".github/workflows/ci.yml"
    for job_id, entry in doc["jobs"].items():
        assert entry["decision_source"] in ccds.ALLOWED_DECISION_SOURCES, job_id


# --------------------------------------------------------------------------
# Rule 1 / 2 — coverage and anti-drift.
# --------------------------------------------------------------------------


def test_full_coverage_is_green(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        _workflow(_job("lint", name="Lint"), _job("test", name="Test")),
        _registry(
            {
                "lint": {"name": "Lint", "decision_source": "deterministic"},
                "test": {"name": "Test", "decision_source": "deterministic"},
            }
        ),
    )
    assert _run(root) == 0


def test_unregistered_job_is_red(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        _workflow(_job("lint"), _job("brand-new-gate")),
        _registry({"lint": {"decision_source": "deterministic"}}),
    )
    assert _run(root) == 1
    report = ccds.check(root / ".github/workflows/ci.yml", root / "ci/decision-source.yaml")
    assert _codes(report) == ["unregistered_job"]
    assert "brand-new-gate" in report.problems[0].message


def test_registry_entry_without_a_job_is_red(tmp_path: Path) -> None:
    """Anti-drift: a renamed/removed job must not leave a stale registration."""
    root = _tree(
        tmp_path,
        _workflow(_job("lint")),
        _registry(
            {
                "lint": {"decision_source": "deterministic"},
                "retired-job": {"decision_source": "deterministic"},
            }
        ),
    )
    assert _run(root) == 1
    report = ccds.check(root / ".github/workflows/ci.yml", root / "ci/decision-source.yaml")
    assert _codes(report) == ["unmatched_registry_entry"]


# --------------------------------------------------------------------------
# Rules 3 / 4 — the decision_source domain and the model-gate ban.
# --------------------------------------------------------------------------


def test_model_decision_source_on_required_job_is_red(tmp_path: Path) -> None:
    """The core B1 assertion: a live job cannot decide on model output."""
    root = _tree(
        tmp_path,
        _workflow(_job("lint"), _job("llm-review", name="LLM Review")),
        _registry(
            {
                "lint": {"decision_source": "deterministic"},
                "llm-review": {"name": "LLM Review", "decision_source": "model"},
            }
        ),
    )
    assert _run(root) == 1
    report = ccds.check(root / ".github/workflows/ci.yml", root / "ci/decision-source.yaml")
    assert _codes(report) == ["model_decision_source_on_required_job"]
    assert "llm-review" in report.problems[0].message


def test_model_decision_source_on_disabled_job_is_green(tmp_path: Path) -> None:
    """`if: false` means the job cannot gate anything, so it is exempt (advisory)."""
    root = _tree(
        tmp_path,
        _workflow(_job("lint"), _job("llm-review", condition="false")),
        _registry(
            {
                "lint": {"decision_source": "deterministic"},
                "llm-review": {"decision_source": "model"},
            }
        ),
    )
    assert _run(root) == 0
    report = ccds.check(root / ".github/workflows/ci.yml", root / "ci/decision-source.yaml")
    assert report.ok
    assert any("if: false" in note for note in report.advisories)


def test_continue_on_error_is_not_an_exemption(tmp_path: Path) -> None:
    """A report-only job still runs and is still read — no model-sourced verdict."""
    root = _tree(
        tmp_path,
        _workflow(_job("routing-eval", condition="true", extra="continue-on-error: true")),
        _registry({"routing-eval": {"decision_source": "model"}}),
    )
    assert _run(root) == 1
    report = ccds.check(root / ".github/workflows/ci.yml", root / "ci/decision-source.yaml")
    assert _codes(report) == ["model_decision_source_on_required_job"]


@pytest.mark.parametrize("condition", ["${{ false }}", "1", "${{ github.event_name == 'x' }}"])
def test_only_literal_false_disables_a_job(tmp_path: Path, condition: str) -> None:
    """Only a real skip exempts a model-sourced value; anything else is live."""
    root = _tree(
        tmp_path,
        _workflow(_job("llm-review", condition=condition)),
        _registry({"llm-review": {"decision_source": "model"}}),
    )
    expected = 0 if condition == "${{ false }}" else 1
    assert _run(root) == expected


def test_job_body_without_a_mapping_still_counts_as_unregistered(tmp_path: Path) -> None:
    """`lint:` with an empty body is still a job in ci.yml, so it needs an entry."""
    root = _tree(
        tmp_path,
        _workflow(_job("lint"), "  empty-body:\n"),
        _registry({"lint": {"decision_source": "deterministic"}}),
    )
    assert _run(root) == 1
    report = ccds.check(root / ".github/workflows/ci.yml", root / "ci/decision-source.yaml")
    assert _codes(report) == ["unregistered_job"]


@pytest.mark.parametrize("source", ["deterministic", "human", " Human ", "DETERMINISTIC"])
def test_allowed_decision_sources_accepted(tmp_path: Path, source: str) -> None:
    root = _tree(
        tmp_path,
        _workflow(_job("lint")),
        _registry({"lint": {"decision_source": source}}),
    )
    assert _run(root) == 0


def test_missing_decision_source_key_is_red(tmp_path: Path) -> None:
    """No implicit default: an entry without the field is not 'deterministic'."""
    root = _tree(
        tmp_path,
        _workflow(_job("lint")),
        _registry({"lint": {"name": "Lint", "rationale": "forgot the field"}}),
    )
    assert _run(root) == 1
    report = ccds.check(root / ".github/workflows/ci.yml", root / "ci/decision-source.yaml")
    assert _codes(report) == ["missing_decision_source"]


@pytest.mark.parametrize("value", ["", "   ", None])
def test_empty_decision_source_is_red(tmp_path: Path, value: str | None) -> None:
    root = _tree(
        tmp_path,
        _workflow(_job("lint")),
        _registry({"lint": {"decision_source": value}}),
    )
    assert _run(root) == 1
    report = ccds.check(root / ".github/workflows/ci.yml", root / "ci/decision-source.yaml")
    assert _codes(report) == ["empty_decision_source"]


def test_model_review_source_on_required_job_is_red(tmp_path: Path) -> None:
    """Any name for a model-sourced verdict is rejected, not just the literal `model`."""
    root = _tree(
        tmp_path,
        _workflow(_job("gate")),
        _registry({"gate": {"decision_source": "claude-review"}}),
    )
    assert _run(root) == 1
    report = ccds.check(root / ".github/workflows/ci.yml", root / "ci/decision-source.yaml")
    assert _codes(report) == ["model_decision_source_on_required_job"]


def test_non_mapping_registry_entry_is_red(tmp_path: Path) -> None:
    root = _tree(tmp_path, _workflow(_job("lint")), _registry({"lint": "deterministic"}))
    assert _run(root) == 1
    report = ccds.check(root / ".github/workflows/ci.yml", root / "ci/decision-source.yaml")
    assert _codes(report) == ["invalid_registry_entry"]


# --------------------------------------------------------------------------
# Advisories never move the exit code; input failures fail closed (exit 2).
# --------------------------------------------------------------------------


def test_name_drift_is_advisory_only(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _tree(
        tmp_path,
        _workflow(_job("lint", name="Lint (ruff)")),
        _registry({"lint": {"name": "Lint", "decision_source": "deterministic"}}),
    )
    assert _run(root) == 0
    assert "records name 'Lint' but" in capsys.readouterr().out


def test_unknown_registry_key_is_advisory_only(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        _workflow(_job("lint")),
        _registry({"lint": {"decision_source": "deterministic", "decision_soruce": "typo"}}),
    )
    assert _run(root) == 0
    report = ccds.check(root / ".github/workflows/ci.yml", root / "ci/decision-source.yaml")
    assert any("unknown key 'decision_soruce'" in note for note in report.advisories)


def test_quiet_prints_only_problems(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _tree(
        tmp_path,
        _workflow(_job("lint")),
        _registry({"lint": {"decision_source": "model"}}),
    )
    assert _run(root, "--quiet") == 1
    out = capsys.readouterr().out
    assert out.startswith("ERROR [model_decision_source_on_required_job]")
    assert "note " not in out
    assert "check_ci_decision_source:" not in out


def test_missing_workflow_fails_closed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _tree(tmp_path, _workflow(_job("lint")), _registry({"lint": {}}))
    (root / ".github/workflows/ci.yml").unlink()
    assert _run(root) == 2
    assert "cannot read workflow" in capsys.readouterr().err


def test_missing_registry_fails_closed(tmp_path: Path) -> None:
    root = _tree(tmp_path, _workflow(_job("lint")), _registry({"lint": {}}))
    (root / "ci/decision-source.yaml").unlink()
    assert _run(root) == 2


def test_malformed_yaml_fails_closed(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        _workflow(_job("lint")),
        "jobs:\n  lint: {decision_source: deterministic\n",
    )
    assert _run(root) == 2


def test_workflow_without_jobs_fails_closed(tmp_path: Path) -> None:
    root = _tree(tmp_path, "name: CI\non:\n  workflow_call:\n", _registry({"lint": {}}))
    assert _run(root) == 2


def test_non_mapping_document_fails_closed(tmp_path: Path) -> None:
    """A top-level YAML list is not a workflow — fail closed, do not guess."""
    root = _tree(tmp_path, "- lint\n- test\n", _registry({"lint": {}}))
    assert _run(root) == 2


def test_registry_without_jobs_fails_closed(tmp_path: Path) -> None:
    root = _tree(tmp_path, _workflow(_job("lint")), "schema_version: 1\n")
    assert _run(root) == 2


def test_explicit_paths_override_root(tmp_path: Path) -> None:
    """`--workflow` / `--registry` are what let this guard be fixture-tested."""
    root = _tree(
        tmp_path,
        _workflow(_job("lint")),
        _registry({"lint": {"decision_source": "deterministic"}}),
    )
    assert _run(root, "--workflow", ".github/workflows/ci.yml") == 0
    assert _run(root, "--registry", "ci/decision-source.yaml") == 0
