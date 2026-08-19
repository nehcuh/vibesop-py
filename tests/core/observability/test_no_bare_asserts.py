"""F2 regression pin: no bare ``assert`` statements in ``core/observability/``.

Runtime guards in this package run in cron-scheduled batch/scan paths.
Under ``python -O`` asserts are stripped, silently disabling the guard —
which is exactly how the F2 bug (``assert cluster.task_keys``) let a
zero-step shell candidate get promoted. All runtime guards here must be
explicit ``if`` checks (see ``skill_promote.scan_candidates``).

Uses ``ast`` so comments and docstrings mentioning "assert" don't trip it.
"""

from __future__ import annotations

import ast
from pathlib import Path

import vibesop.core.observability as observability_pkg


def test_no_bare_assert_statements_in_observability_package() -> None:
    pkg_dir = Path(observability_pkg.__file__).parent
    offenders: list[str] = []
    for path in sorted(pkg_dir.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assert):
                offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, (
        "bare assert statements found in core/observability (stripped under "
        f"python -O — use explicit if-checks): {offenders}"
    )
