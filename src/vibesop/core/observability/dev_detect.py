"""Dev/test environment detection — automatic, no env var required.

Used by ``SpanWriter`` to route spans to a separate dev file
(``.vibe/observability/spans.dev.jsonl``) so test scaffolding never
pollutes the real production span stream that ``vibe recall`` reads from.

Detection order (first match wins):
1. Explicit override via ``VIBESOP_OBSERVABILITY_MODE`` env var
2. ``PYTEST_CURRENT_TEST`` env var (pytest sets this during active test)
3. ``sys.argv[0]`` is the pytest executable
4. Invoked via ``python -m pytest`` (adjacency-checked)

Returns ``False`` for all other contexts (production CLI runs, hooks
firing during real agent use, etc.). Fails open to "prod" rather than
"dev" because the cost asymmetry demands it:

- **False positive dev** (real traffic misrouted to spans.dev.jsonl):
  ``vibe recall`` never sees it — silent loss of production memory.
  **HIGH cost** — invisible breakage.
- **False negative dev** (test traffic leaks to spans.jsonl):
  prod file contaminated with synthetic spans. **MEDIUM cost** —
  annoying but recoverable; many tests already pass explicit paths.

Default-to-prod trades "slightly dirty prod file" for "no silent data
loss." The trade is correct because recall depends on prod-file
completeness; pollution can be filtered, missing data cannot be recovered.
"""

from __future__ import annotations

import os
import sys

__all__ = ["ENV_OVERRIDE", "is_dev_environment"]

ENV_OVERRIDE = "VIBESOP_OBSERVABILITY_MODE"

_DEV_TOKENS = {"dev", "test", "1", "true"}
_PROD_TOKENS = {"prod", "production", "0", "false"}


def is_dev_environment() -> bool:
    """Return True if currently running inside a dev/test context.

    See module docstring for detection order and fail-safe rationale.
    """
    override = os.environ.get(ENV_OVERRIDE, "").strip().lower()
    if override in _DEV_TOKENS:
        return True
    if override in _PROD_TOKENS:
        return False

    # Primary: pytest sets PYTEST_CURRENT_TEST during active test execution
    if "PYTEST_CURRENT_TEST" in os.environ:
        return True

    # Secondary: invoked directly as `pytest`/`python -m pytest`.
    # Use endswith to handle cross-platform path separators (POSIX uses /,
    # Windows uses \; Path.name on POSIX won't split on backslash).
    argv0 = sys.argv[0].lower() if sys.argv else ""
    if argv0.endswith(("pytest", "pytest.exe")):
        return True

    # Adjacency check: `python -m pytest` has argv[i]=="-m" followed by
    # argv[i+1]=="pytest". Loose `"pytest" in argv` would match unrelated
    # args like `python script.py --name pytest_runner`.
    for i, arg in enumerate(sys.argv[:-1]):
        if arg == "-m" and sys.argv[i + 1] == "pytest":
            return True

    return False
