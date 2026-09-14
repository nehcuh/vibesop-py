#!/usr/bin/env python3
"""Guard: every CI job must declare where its verdict comes from.

Why this exists
---------------
`docs/ROADMAP.md` forbids treating LLM review as a merge gate, but that ban is
prose. Nothing in the repo noticed when a job's verdict started depending on
model output. This guard turns the ban into a mechanism: the registry
`ci/decision-source.yaml` declares a `decision_source` per CI job, and this
script cross-checks that registry against `.github/workflows/ci.yml`.

Scope
-----
This first registry covers `.github/workflows/ci.yml` ONLY. Quickstart
(`quickstart-e2e.yml`), release (`release.yml`), and CodeQL workflows are
out of scope and must not be pointed at this checker. The registry must
declare ``workflow: .github/workflows/ci.yml``; any other value is exit 2.

Contract (exactly these rules fail; everything else is advisory)
----------------------------------------------------------------
1. **Coverage** — every job in the workflow must be registered. A new job
   added to ci.yml without a registry entry is a red build, which is the
   point: the registry cannot silently go stale.
2. **Anti-drift** — every registry entry must name a job that still exists in
   the workflow. A leftover entry (renamed/removed job) is red too, so the
   registry cannot silently over-claim.
3. **Domain** — `decision_source` must be present and one of
   `deterministic | human`. `model` or any other value is a contract
   violation even on a job disabled with `if: false`. A skipped job is still
   in the workflow, still registered, and still bound by the domain.
   `continue-on-error: true` is not an escape hatch either: the job still
   runs and is still read.

Advisories (printed, never fatal)
---------------------------------
- registry annotations the script does not know about (free-form; only
  `decision_source` is enforced);
- a recorded `name` that no longer matches the workflow's job name (job ids
  are the identity contract; names are a review aid).

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
    0 - all contract rules hold (advisories may still be printed)
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

#: The only values that may appear as `decision_source`.
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
)

#: Load-bearing registry schema. Wrong or missing values are exit 2.
REQUIRED_REGISTRY_SCHEMA_VERSION = 1
REQUIRED_REGISTRY_WORKFLOW = ".github/workflows/ci.yml"


class GuardError(Exception):
    """The inputs could not be read — the guard cannot reach a verdict."""


class UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate or unhashable mapping keys (fail closed)."""


def _construct_unique_mapping(
    loader: yaml.SafeLoader, node: yaml.nodes.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    """Build a mapping and raise if any key is duplicated or unhashable."""
    if not isinstance(node, yaml.nodes.MappingNode):
        raise yaml.constructor.ConstructorError(
            None,
            None,
            f"expected a mapping node, but found {node.id}",
            node.start_mark,
        )
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            hash(key)
        except TypeError as exc:
            raise yaml.constructor.ConstructorError(
                None,
                None,
                f"unhashable mapping key {type(key).__name__}",
                key_node.start_mark,
            ) from exc
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                None,
                None,
                f"duplicate mapping key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


@dataclass(frozen=True)
class Problem:
    """One contract violation (coverage / anti-drift / domain)."""

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
    """Load a YAML mapping, raising :class:`GuardError` on any failure.

    Invalid UTF-8, duplicate mapping keys, and unhashable mapping keys are
    input failures (exit 2), not silent last-key-wins collapses or an
    uncaught ``TypeError``.
    """
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise GuardError(f"cannot read {what} at {path}: {exc}") from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise GuardError(f"cannot decode {what} at {path} as UTF-8: {exc}") from exc
    try:
        doc = yaml.load(text, Loader=UniqueKeyLoader)
    except (yaml.YAMLError, TypeError) as exc:
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
    """Return the ``jobs:`` mapping of the registry, or raise if the schema fails.

    ``schema_version`` must be the exact integer ``1`` (not ``True``,
    ``1.0``, or ``"1"``). ``workflow: .github/workflows/ci.yml`` and a
    non-empty ``jobs`` mapping are also load-bearing. Wrong or missing
    values are input failures (exit 2), not advisories.
    """
    version = doc.get("schema_version")
    # `True == 1` and `1.0 == 1` in Python; require the exact integer type.
    if type(version) is not int or version != REQUIRED_REGISTRY_SCHEMA_VERSION:
        raise GuardError(
            f"registry at {path} must declare schema_version: "
            f"{REQUIRED_REGISTRY_SCHEMA_VERSION} (got {version!r})"
        )
    workflow = doc.get("workflow")
    if workflow != REQUIRED_REGISTRY_WORKFLOW:
        raise GuardError(
            f"registry at {path} must declare workflow: {REQUIRED_REGISTRY_WORKFLOW} "
            f"(got {workflow!r}); this guard covers ci.yml only"
        )
    jobs = doc.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        raise GuardError(f"registry at {path} declares no `jobs:` mapping")
    return {str(job_id): body for job_id, body in jobs.items()}


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
    """Apply the contract rules and collect advisories."""
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

        report.problems.append(
            Problem(
                "invalid_decision_source",
                f"job '{job_id}' declares decision_source '{source}' — "
                f"only {' | '.join(ALLOWED_DECISION_SOURCES)} are valid; "
                "any other value is a contract violation even if the job is disabled",
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
            "Check that every job in .github/workflows/ci.yml declares a "
            "decision_source in the registry and that every value is "
            "deterministic or human. Scope is ci.yml ONLY — quickstart-e2e.yml, "
            "release.yml, and CodeQL workflows are out of scope."
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
        help=(
            f"Workflow file, relative to --root (default: {DEFAULT_WORKFLOW}). "
            "This first registry covers ci.yml only; do not point at "
            "quickstart-e2e.yml, release.yml, or CodeQL workflows."
        ),
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
