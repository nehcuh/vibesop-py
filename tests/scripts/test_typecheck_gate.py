"""Type-gate regression tests: the CI basedpyright step must pass only on real success.

Background (docs/specs/2026-09-09-verification-contract.md §F): with the pinned
basedpyright 1.39.9, plain-text exit codes are

- 0 = success (warnings allowed)
- 1 = type errors
- 3 = configuration error (unrecognized setting, missing stubPath dir, ...)

The old gate ``uv run basedpyright || [ $? -eq 3 ]`` treated exit 3 as "warnings
only" and green-lit runs that also reported type errors. These tests therefore
run the real pinned basedpyright binary in throwaway projects (no fake return
codes, no network) and pin the CI command's full shape so the old acceptance
cannot be reintroduced unnoticed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PYPROJECT = REPO_ROOT / "pyproject.toml"


def _find_basedpyright() -> Path | None:
    """The real basedpyright next to the running interpreter, else on PATH."""
    candidate = Path(sys.executable).with_name(
        "basedpyright.exe" if os.name == "nt" else "basedpyright"
    )
    if candidate.is_file():
        return candidate
    found = shutil.which("basedpyright")
    return Path(found) if found else None


BP_BIN = _find_basedpyright()

pytestmark = pytest.mark.skipif(
    BP_BIN is None, reason="basedpyright not installed — run `uv sync --extra dev`"
)


def _make_project(tmp_path: Path, *, extra_config: str = "", body: str) -> Path:
    """A throwaway project with a [tool.pyright] config and one source file."""
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pyright]\ninclude = ["src"]\n' + extra_config,
        encoding="utf-8",
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "sample.py").write_text(body, encoding="utf-8")
    return tmp_path


def _run_gate(project: Path, *extra_args: str) -> subprocess.CompletedProcess[str]:
    """Run the CI-shaped plain-text command (no --outputjson)."""
    args = [str(BP_BIN)]
    args.extend(extra_args)
    args.append("--level")
    args.append("error")
    return subprocess.run(
        args,
        cwd=project,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_clean_project_passes() -> None:
    """Exit 0 on clean code: the only state the gate may accept."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        project = _make_project(
            Path(td),
            body="def double(x: int) -> int:\n    return x * 2\n",
        )
        result = _run_gate(project)
    assert result.returncode == 0, result.stdout + result.stderr


def test_type_error_is_rejected() -> None:
    """A type error exits 1 and must fail the gate."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        project = _make_project(
            Path(td),
            body='def f(x: int) -> int:\n    return "bad"\n',
        )
        result = _run_gate(project)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "error:" in result.stdout


def test_invalid_config_is_rejected_as_config_error() -> None:
    """Exit 3 = configuration error in plain-text mode, never accepted.

    This is exactly the failure the old ``|| [ $? -eq 3 ]`` gate swallowed.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        project = _make_project(
            Path(td),
            extra_config='reportMissingReturnType = "error"\n',
            body="def f(x: int) -> int:\n    return x\n",
        )
        result = _run_gate(project)
        assert result.returncode == 3, result.stdout + result.stderr
        assert "unrecognized setting" in result.stderr


def test_warnings_only_is_allowed_under_level_error() -> None:
    """Rules configured as warning stay advisory: non-blocking with --level error.

    Plain-text basedpyright exits 1 when warnings are reported at the default
    level, so the CI command must use ``--level error`` to keep explicitly
    warning-severity rules non-blocking while errors still fail.
    """
    import tempfile

    body = (
        "class Box:\n"
        "    def __init__(self) -> None:\n"
        "        self._secret = 1\n"
        "\n"
        "def use(b: Box) -> None:\n"
        "    print(b._secret)\n"
    )
    with tempfile.TemporaryDirectory() as td:
        project = _make_project(
            Path(td),
            extra_config='reportPrivateUsage = "warning"\n',
            body=body,
        )
        plain = subprocess.run(
            [str(BP_BIN), "."],
            cwd=project,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        gated = _run_gate(project)

    assert "warning" in plain.stdout.lower()
    assert plain.returncode == 1  # default level makes warnings block
    assert gated.returncode == 0  # --level error keeps warnings non-blocking


def test_ci_command_shape_is_pinned() -> None:
    """The real CI step must run the plain-text gate with --level error and must
    no longer accept exit 3 as success."""
    import re

    ci = CI_YML.read_text(encoding="utf-8")
    runs = re.findall(r"^[ \t]*run: (uv run basedpyright.*)$", ci, re.M)
    assert runs, "ci.yml has no basedpyright run step"
    for run_line in runs:
        assert run_line == "uv run basedpyright --level error", run_line

    # pyproject [tool.pyright]: the invalid settings and the nonexistent
    # stubPath are gone (valid rules are untouched).
    pyproject_text = PYPROJECT.read_text(encoding="utf-8")
    section = pyproject_text.split("[tool.pyright]", 1)[1].split("\n[", 1)[0]
    assert "reportMissingReturnType =" not in section
    assert "reportUntypedClassDef =" not in section
    assert "stubPath =" not in section
    # Effective rules that must survive untouched.
    assert 'reportMissingParameterType = "error"' in section
    assert 'reportUntypedBaseClass = "error"' in section
    assert 'reportUntypedFunctionDecorator = "error"' in section
