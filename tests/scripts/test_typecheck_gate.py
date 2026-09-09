"""Type-gate regression tests: the CI basedpyright step must pass only on real success.

Background (docs/specs/2026-09-09-verification-contract.md §F): with the pinned
basedpyright 1.39.9, plain-text exit codes are

- 0 = success (warnings allowed)
- 1 = type errors
- 3 = configuration error (unrecognized setting, missing stubPath dir, ...)

The old gate ``uv run basedpyright || [ $? -eq 3 ]`` treated exit 3 as "warnings
only" and green-lit runs that also reported type errors. Additionally,
``GITHUB_ACTIONS=true`` switches basedpyright 1.39.9 to GitHub Actions output,
where a warnings-only run exits 1 even under ``--level error``. Every real gate
entry point therefore sets ``PYRIGHT_DISABLE_GITHUB_ACTIONS_OUTPUT=1`` (plain-text
mode); these tests inherit that production setting by parsing the CI step env
rather than redefining it, and run each scenario both on a normal machine and
with a real ``GITHUB_ACTIONS=true`` child environment.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PYPROJECT = REPO_ROOT / "pyproject.toml"

_PLAIN_OPTIONS = ("--level", "error")


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


def _ci_typecheck_env() -> dict[str, str]:
    """The real env of the CI ``Run basedpyright`` step (production setting).

    Tests inherit this instead of redefining the environment config, so a change
    in ci.yml is picked up here automatically.
    """
    data = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
    steps = data["jobs"]["type-check"]["steps"]
    for step in steps:
        if "basedpyright" in str(step.get("run", "")):
            return {str(k): str(v) for k, v in (step.get("env") or {}).items()}
    raise AssertionError("ci.yml has no Run basedpyright step env")


PROD_ENV = _ci_typecheck_env()


def _child_env(*, github: bool) -> dict[str, str]:
    env = os.environ.copy()
    env.update(PROD_ENV)
    # ``github=False`` must mean a normal machine: never let an outer
    # GITHUB_ACTIONS=true leak in; ``github=True`` sets it explicitly.
    if github:
        env["GITHUB_ACTIONS"] = "true"
    else:
        env.pop("GITHUB_ACTIONS", None)
    return env


def _make_project(tmp_path: Path, *, extra_config: str = "", body: str) -> Path:
    """A throwaway project with a [tool.pyright] config and one source file."""
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pyright]\ninclude = ["src"]\n' + extra_config,
        encoding="utf-8",
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "sample.py").write_text(body, encoding="utf-8")
    return tmp_path


def _run_basedpyright(
    project: Path, args: list[str], *, github: bool
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(BP_BIN), *args],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env=_child_env(github=github),
    )


def _run_gate(project: Path, *, github: bool) -> subprocess.CompletedProcess[str]:
    """Run the CI-shaped plain-text command (no --outputjson)."""
    return _run_basedpyright(project, list(_PLAIN_OPTIONS), github=github)


GITHUB_CASES = pytest.mark.parametrize("github", [False, True])


@GITHUB_CASES
def test_clean_project_passes(github: bool) -> None:
    """Exit 0 on clean code: the only state the gate may accept."""
    with tempfile.TemporaryDirectory() as td:
        project = _make_project(
            Path(td),
            body="def double(x: int) -> int:\n    return x * 2\n",
        )
        result = _run_gate(project, github=github)
    assert result.returncode == 0, result.stdout + result.stderr


@GITHUB_CASES
def test_type_error_is_rejected(github: bool) -> None:
    """A type error exits 1 and must fail the gate."""
    with tempfile.TemporaryDirectory() as td:
        project = _make_project(
            Path(td),
            body='def f(x: int) -> int:\n    return "bad"\n',
        )
        result = _run_gate(project, github=github)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "error:" in result.stdout


@GITHUB_CASES
def test_invalid_config_is_rejected_as_config_error(github: bool) -> None:
    """Exit 3 = configuration error in plain-text mode, never accepted.

    This is exactly the failure the old ``|| [ $? -eq 3 ]`` gate swallowed.
    """
    with tempfile.TemporaryDirectory() as td:
        project = _make_project(
            Path(td),
            extra_config='reportMissingReturnType = "error"\n',
            body="def f(x: int) -> int:\n    return x\n",
        )
        result = _run_gate(project, github=github)
    assert result.returncode == 3, result.stdout + result.stderr
    assert "unrecognized setting" in result.stderr


_WARNING_BODY = (
    "class Box:\n"
    "    def __init__(self) -> None:\n"
    "        self._secret = 1\n"
    "\n"
    "def use(b: Box) -> None:\n"
    "    print(b._secret)\n"
)


@GITHUB_CASES
def test_warnings_only_is_allowed_under_level_error(github: bool) -> None:
    """Rules configured as warning stay advisory: non-blocking with --level error.

    First prove the fixture really produces the configured ``reportPrivateUsage``
    warning: the same project, production env, WITHOUT ``--level error``, must
    report the warning with exit 1 and zero errors. Then the gated command
    (``--level error`` + production plain-text env) must exit 0.
    """
    with tempfile.TemporaryDirectory() as td:
        project = _make_project(
            Path(td),
            extra_config='reportPrivateUsage = "warning"\n',
            body=_WARNING_BODY,
        )
        # Control: no --level error → the warning is reported and blocks.
        ungated = _run_basedpyright(project, [], github=github)
        assert ungated.returncode == 1, ungated.stdout + ungated.stderr
        assert "0 errors" in ungated.stdout, ungated.stdout
        assert "reportPrivateUsage" in ungated.stdout, ungated.stdout
        assert "warning" in ungated.stdout, ungated.stdout

        # Gated (CI shape): warnings stay advisory → exit 0.
        result = _run_gate(project, github=github)
    assert result.returncode == 0, result.stdout + result.stderr


def test_production_env_is_plain_text() -> None:
    """The CI step env must force plain-text output (single source of truth)."""
    assert PROD_ENV.get("PYRIGHT_DISABLE_GITHUB_ACTIONS_OUTPUT") == "1"


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
