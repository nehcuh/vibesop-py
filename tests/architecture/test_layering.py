"""Architecture layering enforcement — core/ must not depend on outer layers.

Enforces the dependency direction in docs/architecture/three-layers.md: ``core/``
is the innermost layer and must not import from ``cli/``, ``agent/``,
``adapters/``, or ``builder/``. Pre-fix this rule was an *unenforced assertion*
— the ``tests/architecture/test_dependencies.py`` / ``test_boundaries.py`` files
referenced in three-layers.md:517-527 did not exist, so two real violations
landed silently:

  - ``core/loop/executor.py`` imported ``vibesop.agent.runtime.agent_runtime``
    (Core -> Agent). Fixed via a ``LoopRunner`` Protocol + runtime injection
    from the CLI caller.
  - ``core/skills/slash_commands.py`` imported ``vibesop.cli.routing_report``
    for ``/vibe-route --explain`` (Core -> CLI). Fixed via an injected optional
    ``routing_report_renderer`` (text fallback when none is provided).

This test AST-scans every ``.py`` file under ``src/vibesop/core/`` (top-level
*and* lazy imports) so the rule can't regress without a failing build.

Limitation: this is a *static* AST scan — it catches ``import`` / ``from ...
import`` but not dynamic ``__import__("vibesop.cli...")`` /
``importlib.import_module(...)``. Defeating the guard that way would be a
deliberate, unusual act (and itself a smell); a regex-based secondary scan can
be added if it ever becomes a concern.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CORE_DIR = _REPO_ROOT / "src" / "vibesop" / "core"
# Layers core/ must NOT import (the outer layers).
_FORBIDDEN_PREFIXES = ("vibesop.cli", "vibesop.agent", "vibesop.adapters", "vibesop.builder")


def _imported_modules(source: str) -> list[str]:
    """All module names imported in a source file (top-level + lazy/nested)."""
    tree = ast.parse(source)
    mods: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.append(node.module)
    return mods


def _core_python_files() -> list[Path]:
    return [p for p in _CORE_DIR.rglob("*.py") if "__pycache__" not in p.parts]


def _is_forbidden(module: str) -> bool:
    return any(module == p or module.startswith(p + ".") for p in _FORBIDDEN_PREFIXES)


@pytest.mark.parametrize(
    "path",
    _core_python_files(),
    ids=lambda p: str(p.relative_to(_CORE_DIR)),
)
def test_core_imports_no_outer_layer(path: Path) -> None:
    """No module under src/vibesop/core/ may import cli/agent/adapters/builder."""
    source = path.read_text(encoding="utf-8")
    violations = [m for m in _imported_modules(source) if _is_forbidden(m)]
    assert not violations, (
        f"{path.relative_to(_CORE_DIR)} imports outer-layer module(s) {violations}. "
        f"core/ must depend only on itself + stdlib/third-party, never on "
        f"cli/agent/adapters/builder (see docs/architecture/three-layers.md)."
    )


def test_layering_test_actually_covers_core() -> None:
    """Guard: if _core_python_files() ever returns nothing, the parametrized
    test above would vacuously pass. Assert we're scanning real files."""
    files = _core_python_files()
    assert len(files) > 50, f"expected to scan many core/ files, got {len(files)}"
