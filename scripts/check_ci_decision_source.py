#!/usr/bin/env python3
"""Guard: every CI job must declare where its verdict comes from (Lane B / B1).

Why this exists
---------------
`docs/ROADMAP.md` forbids treating LLM review as a merge gate, but that ban is
prose. Nothing in the repo noticed when a job's verdict started depending on
model output. This guard turns the ban into a mechanism: the registry
`ci/decision-source.yaml` declares a `decision_source` per CI job, and this
script cross-checks that registry against `.github/workflows/ci.yml`.

Contract (exactly these four rules fail; everything else is advisory)
--------------------------------------------------------------------
1. **Coverage** — every job in the workflow must be registered. A new job
   added to ci.yml without a registry entry is a red build, which is the
   point: the registry cannot silently go stale.
2. **Anti-drift** — every registry entry must name a job that still exists in
   the workflow. A leftover entry (renamed/removed job) is red too, so the
   registry cannot silently over-claim.
3. **Domain** — `decision_source` must be present and one of
   `deterministic | human`.
4. **No model gates** — any other value (e.g. `model`) is red *unless* the
   corresponding workflow job is disabled outright with `if: false`, i.e. it
   cannot gate anything. A job that still runs and is read by humans is not
   exempt: `continue-on-error: true` is NOT an escape hatch here.

Advisories (printed, never fatal)
---------------------------------
- registry annotations the script does not know about (free-form; only
  `decision_source` is enforced);
- a recorded `name` that no longer matches the workflow's job name (job ids
  are the identity contract; names are a review aid);
- a non-standard `decision_source` accepted via the `if: false` exemption.

Honest limit
------------
This is a declaration check, not a proof. It cannot see a human pasting a
model's conclusion into a PR comment, and it does not inspect imports — B2
(static import ban for `deterministic` gate scripts) is not implemented yet.
The mechanism shrinks the surface; it does not zero it.

Usage:
    uv run python scripts/check_ci_decision_source.py
    uv run python scripts/check_ci_decision_source.py --root . \
        --workflow .github/workflows/ci.yml --registry ci/decision-source.yaml
    uv run python scripts/check_ci_decision_source.py --quiet

Exit codes:
    0 - all four rules hold (advisories may still be printed)
    1 - at least one rule violated
    2 - could not read/parse the workflow or the registry (fail-closed)
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_WORKFLOW = Path(".github/workflows/ci.yml")
DEFAULT_REGISTRY = Path("ci/decision-source.yaml")

#: The only values that may gate a required job.
ALLOWED_DECISION_SOURCES: tuple[str, ...] = ("deterministic", "human")

#: Keys enforced on a registry entry.
REQUIRED_ENTRY_KEYS: tuple[str, ...] = ("decision_source",)

#: Keys the guard understands but does not enforce (annotations for reviewers).
KNOWN_ENTRY_KEYS: tuple[str, ...] = (
    "decision_source",
    "name",
    "rationale",
    "notes",
    "evidence",
    "confirmed_by",
    "confirmed_at",
)

#: `if:` values that mean the job never runs, so it can never gate anything.
_DISABLED_IF_VALUES = frozenset({"false", "${{ false }}"})


class GuardError(Exception):
    """The inputs could not be read — the guard cannot reach a verdict."""


@dataclass(frozen=True)
class Problem:
    """One contract violation (rule 1-4)."""

    code: str
    message: str

    def render(self) -> str:
        return f"ERROR [{self.code}] {self.message}"


@dataclass
class Report:
    """Outcome of one workflow-vs-registry comparison."""

    workflow_jobs: list[str] = field(default_factory=list)
    registered_jobs: list[str] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)
    advisories: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def load_yaml(path: Path, what: str) -> dict[str, Any]:
    """Load a YAML mapping, raising :class:`GuardError` on any failure."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise GuardError(f"cannot read {what} at {path}: {exc}") from exc
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise GuardError(f"cannot parse {what} at {path}: {exc}") from exc
    if not isinstance(doc, dict):
        raise GuardError(f"{what} at {path} is not a YAML mapping")
    return doc


def workflow_job_specs(doc: Mapping[str, Any], path: Path) -> dict[str, Mapping[str, Any]]:
    """Return ``{job_id: job_body}`` in file order, or raise if there is none."""
    jobs = doc.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        raise GuardError(f"workflow at {path} declares no `jobs:` mapping")
    specs: dict[str, Mapping[str, Any]] = {}
    for job_id, body in jobs.items():
        specs[str(job_id)] = body if isinstance(body, dict) else {}
    return specs


def registry_entries(doc: Mapping[str, Any], path: Path) -> dict[str, Any]:
    """Return the ``jobs:`` mapping of the registry, or raise if it is absent."""
    jobs = doc.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        raise GuardError(f"registry at {path} declares no `jobs:` mapping")
    return {str(job_id): body for job_id, body in jobs.items()}


def job_is_disabled(job: Mapping[str, Any]) -> bool:
    """True when the job can never run (``if: false``).

    Only an outright skip counts. `continue-on-error: true` does not: the job
    still runs, still produces a verdict, and humans still read it.
    """
    condition = job.get("if")
    if condition is False:
        return True
    if isinstance(condition, str):
        return condition.strip().lower() in _DISABLED_IF_VALUES
    return False


def normalize_decision_source(value: Any) -> str:
    """Lower-cased, stripped string form of a `decision_source` value."""
    return str(value).strip().lower() if value is not None else ""


def compare(
    workflow_jobs: Mapping[str, Mapping[str, Any]],
    entries: Mapping[str, Any],
    *,
    workflow_path: Path,
    registry_path: Path,
) -> Report:
    """Apply the four contract rules and collect advisories."""
    report = Report(
        workflow_jobs=list(workflow_jobs),
        registered_jobs=list(entries),
    )

    # Rule 2 — anti-drift: a registry entry with no job behind it.
    for job_id in entries:
        if job_id not in workflow_jobs:
            report.problems.append(
                Problem(
                    "unmatched_registry_entry",
                    f"registry entry '{job_id}' has no job in {workflow_path} — "
                    f"remove it from {registry_path} or restore the job "
                    "(a stale entry lets the registry over-claim)",
                )
            )

    for job_id, job in workflow_jobs.items():
        entry = entries.get(job_id)

        # Rule 1 — coverage.
        if entry is None:
            report.problems.append(
                Problem(
                    "unregistered_job",
                    f"job '{job_id}' is not registered in {registry_path} — every CI job "
                    "needs a decision_source (deterministic | human)",
                )
            )
            continue

        if not isinstance(entry, dict):
            report.problems.append(
                Problem(
                    "invalid_registry_entry",
                    f"registry entry '{job_id}' is not a mapping — expected "
                    f"`decision_source: deterministic|human`",
                )
            )
            continue

        for key in entry:
            if key not in KNOWN_ENTRY_KEYS:
                report.advisories.append(
                    f"registry entry '{job_id}' has unknown key '{key}' "
                    "(annotations are free-form; only decision_source is enforced)"
                )

        recorded_name = entry.get("name")
        actual_name = job.get("name")
        if (
            isinstance(recorded_name, str)
            and isinstance(actual_name, str)
            and recorded_name != actual_name
        ):
            report.advisories.append(
                f"registry entry '{job_id}' records name '{recorded_name}' but "
                f"{workflow_path} says '{actual_name}' — update the review aid"
            )

        # Rule 3 — the entry must declare a source at all.
        if all(key not in entry for key in REQUIRED_ENTRY_KEYS):
            report.problems.append(
                Problem(
                    "missing_decision_source",
                    f"registry entry '{job_id}' has no decision_source — the field is "
                    "mandatory; there is no implicit default",
                )
            )
            continue

        source = normalize_decision_source(entry.get("decision_source"))
        if not source:
            report.problems.append(
                Problem(
                    "empty_decision_source",
                    f"registry entry '{job_id}' has an empty decision_source — "
                    "use deterministic or human",
                )
            )
            continue

        if source in ALLOWED_DECISION_SOURCES:
            continue

        # Rule 4 — a non-deterministic source may only sit on a job that never runs.
        if job_is_disabled(job):
            report.advisories.append(
                f"job '{job_id}' declares decision_source '{source}' but is disabled "
                "with `if: false` — accepted: a skipped job gates nothing"
            )
            continue

        report.problems.append(
            Problem(
                "model_decision_source_on_required_job",
                f"job '{job_id}' declares decision_source '{source}' but is a live job in "
                f"{workflow_path} — only {', '.join(ALLOWED_DECISION_SOURCES)} may gate a "
                "required job (ROADMAP: no LLM review as a merge gate); disable it with "
                "`if: false` or make the verdict deterministic",
            )
        )

    return report


def check(workflow_path: Path, registry_path: Path) -> Report:
    """Load both files and compare them. Raises :class:`GuardError` on input errors."""
    workflow_doc = load_yaml(workflow_path, "workflow")
    registry_doc = load_yaml(registry_path, "registry")
    workflow_jobs = workflow_job_specs(workflow_doc, workflow_path)
    entries = registry_entries(registry_doc, registry_path)
    return compare(
        workflow_jobs,
        entries,
        workflow_path=workflow_path,
        registry_path=registry_path,
    )


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check that every CI job declares a decision_source in the registry "
            "and that no model-sourced value gates a live job."
        ),
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=PROJECT_ROOT,
        help="Repository root the default paths are resolved against.",
    )
    parser.add_argument(
        "--workflow",
        type=Path,
        default=None,
        help=f"Workflow file, relative to --root (default: {DEFAULT_WORKFLOW}).",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=None,
        help=f"Registry file, relative to --root (default: {DEFAULT_REGISTRY}).",
    )
    parser.add_argument("--quiet", action="store_true", help="Only print problems.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    root: Path = args.root.resolve()
    workflow_path = (root / (args.workflow or DEFAULT_WORKFLOW)).resolve()
    registry_path = (root / (args.registry or DEFAULT_REGISTRY)).resolve()

    try:
        report = check(workflow_path, registry_path)
    except GuardError as exc:
        print(f"check_ci_decision_source: {exc}", file=sys.stderr)
        return 2

    for problem in report.problems:
        print(problem.render())

    if not args.quiet:
        for advisory in report.advisories:
            print(f"note     {advisory}")
        summary = (
            f"check_ci_decision_source: {len(report.workflow_jobs)} workflow job(s), "
            f"{len(report.registered_jobs)} registry entr(y/ies) — "
        )
        if report.ok:
            print(
                summary
                + "all registered, all decision sources "
                + " | ".join(ALLOWED_DECISION_SOURCES)
                + "."
            )
        else:
            print(summary + f"{len(report.problems)} problem(s).")

    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
