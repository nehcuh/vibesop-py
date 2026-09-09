"""Release/Makefile gate regression using the real production stages.

Background (docs/specs/2026-09-09-verification-contract.md §G):

- Makefile ``type-check`` and ``scripts/verify-release.sh`` used to treat
  basedpyright exit 3 as success. In 1.39.9 plain-text mode, 3 is a
  configuration error.
- The release script grepped pytest output for ``passed`` without pipefail,
  so a real summary like ``1 failed, 1 passed`` was accepted.

Stages are sliced out of ``scripts/verify-release.sh`` at the ``# Run tests``
and ``# Check type hints`` markers and executed as-is. The Makefile
``type-check`` recipe is extracted (and ``make -f`` is used when available).
No second acceptance ``if`` is written here. Temp projects reuse the already
installed env (``UV_PROJECT_ENVIRONMENT`` / ``UV_NO_SYNC`` / ``UV_OFFLINE``).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = REPO_ROOT / "Makefile"
RELEASE_SH = REPO_ROOT / "scripts" / "verify-release.sh"

# These tests execute POSIX release-script stages via bash/grep; skip only when
# the executables are actually absent (e.g. native Windows), never wholesale.
pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("grep") is None,
    reason="requires bash and grep on PATH",
)

# Prefix only: shell options + the color vars the extracted fragments expand.
# Must not include an acceptance if — that lives in the production stage.
_STAGE_PREFIX = """\
set -euo pipefail
GREEN='\\033[0;32m'
RED='\\033[0;31m'
YELLOW='\\033[1;33m'
NC='\\033[0m'
"""

_MIN_PYPROJECT = """\
[project]
name = "release-gate-probe"
version = "0.0.1"
requires-python = ">=3.12"
"""


def _uv_env() -> dict[str, str]:
    env = os.environ.copy()
    env["UV_PROJECT_ENVIRONMENT"] = str(Path(sys.prefix).resolve())
    env["UV_NO_SYNC"] = "1"
    env["UV_OFFLINE"] = "1"
    env.pop("FORCE_COLOR", None)
    env["NO_COLOR"] = "1"
    return env


def _plain(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _extract_stage(source: str, start_marker: str, end_marker: str) -> str:
    start = source.index(start_marker)
    end = source.index(end_marker, start + len(start_marker))
    stage = source[start:end].strip()
    assert stage, f"empty stage between {start_marker!r} and {end_marker!r}"
    return stage


def _release_source() -> str:
    return RELEASE_SH.read_text(encoding="utf-8")


def _test_stage() -> str:
    return _extract_stage(_release_source(), "# Run tests", "# Check type hints")


def _type_stage() -> str:
    return _extract_stage(_release_source(), "# Check type hints", "# Check linting")


def _makefile_type_check_recipe() -> str:
    text = MAKEFILE.read_text(encoding="utf-8")
    match = re.search(r"^type-check:.*\n((?:\t.*\n?)+)", text, re.M)
    assert match, "Makefile is missing a type-check recipe"
    lines: list[str] = []
    for line in match.group(1).splitlines():
        assert line.startswith("\t"), line
        lines.append(line[1:])
    recipe = "\n".join(lines).strip()
    assert recipe, "empty type-check recipe"
    return recipe


def _run_bash(project: Path, body: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", body],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env=_uv_env(),
    )


def _run_extracted_stage(project: Path, stage: str) -> subprocess.CompletedProcess[str]:
    return _run_bash(project, _STAGE_PREFIX + stage + "\n")


def _run_makefile_recipe(project: Path) -> subprocess.CompletedProcess[str]:
    return _run_bash(project, "set -euo pipefail\n" + _makefile_type_check_recipe() + "\n")


def _write_pytest_project(root: Path, *, failing: bool) -> Path:
    (root / "pyproject.toml").write_text(_MIN_PYPROJECT, encoding="utf-8")
    tests = root / "tests"
    tests.mkdir()
    (tests / "test_ok.py").write_text(
        "def test_ok() -> None:\n    assert 1 + 1 == 2\n", encoding="utf-8"
    )
    if failing:
        (tests / "test_bad.py").write_text(
            "def test_bad() -> None:\n    assert 1 + 1 == 3\n",
            encoding="utf-8",
        )
    return root


def _write_type_project(root: Path, *, extra_config: str = "", body: str) -> Path:
    (root / "pyproject.toml").write_text(
        _MIN_PYPROJECT + '[tool.pyright]\ninclude = ["src"]\n' + extra_config,
        encoding="utf-8",
    )
    (root / "src").mkdir()
    (root / "src" / "sample.py").write_text(body, encoding="utf-8")
    return root


def test_mixed_pass_fail_is_rejected_unlike_grep_passed() -> None:
    """Real pytest '1 failed, 1 passed' must fail the extracted release test stage."""
    stage = _test_stage()
    assert "grep" not in stage
    assert "uv run pytest" in stage

    with tempfile.TemporaryDirectory() as td:
        project = _write_pytest_project(Path(td), failing=True)
        result = _run_extracted_stage(project, stage)

    out = _plain(result.stdout + result.stderr)
    assert result.returncode != 0, out
    assert "failed" in out
    assert "passed" in out
    grep = subprocess.run(
        ["grep", "-q", "passed"],
        input=out,
        text=True,
        check=False,
    )
    assert grep.returncode == 0, "old grep gate would have accepted this mix"
    assert "Tests failing" in out


def test_all_passing_pytest_is_allowed() -> None:
    stage = _test_stage()
    with tempfile.TemporaryDirectory() as td:
        project = _write_pytest_project(Path(td), failing=False)
        result = _run_extracted_stage(project, stage)

    out = _plain(result.stdout + result.stderr)
    assert result.returncode == 0, out
    assert "Tests passing" in out
    assert "failed" not in out


def test_type_error_is_rejected() -> None:
    recipe = _makefile_type_check_recipe()
    type_stage = _type_stage()
    assert "--level error" in recipe
    assert "uv run basedpyright --level error" in type_stage
    assert "-eq 3" not in type_stage

    with tempfile.TemporaryDirectory() as td:
        project = _write_type_project(
            Path(td),
            body='def f(x: int) -> int:\n    return "bad"\n',
        )
        from_make = _run_makefile_recipe(project)
        from_release = _run_extracted_stage(project, type_stage)

    assert from_make.returncode == 1, from_make.stdout + from_make.stderr
    assert "error:" in _plain(from_make.stdout)
    assert from_release.returncode != 0, from_release.stdout + from_release.stderr


def test_invalid_config_is_rejected_as_config_error() -> None:
    """Plain-text basedpyright exit 3 must fail both local gates."""
    with tempfile.TemporaryDirectory() as td:
        project = _write_type_project(
            Path(td),
            extra_config='reportMissingReturnType = "error"\n',
            body="def f(x: int) -> int:\n    return x\n",
        )
        from_make = _run_makefile_recipe(project)
        from_release = _run_extracted_stage(project, _type_stage())

    combined = _plain(from_make.stdout + from_make.stderr)
    assert from_make.returncode == 3, combined
    assert "unrecognized setting" in combined
    assert from_release.returncode != 0, from_release.stdout + from_release.stderr


def test_warnings_only_is_allowed_under_level_error() -> None:
    recipe = _makefile_type_check_recipe()
    ungated = recipe.replace(" --level error", "")
    assert ungated != recipe, "type-check recipe must pass --level error"

    body = (
        "class Box:\n"
        "    def __init__(self) -> None:\n"
        "        self._secret = 1\n"
        "\n"
        "def use(b: Box) -> None:\n"
        "    print(b._secret)\n"
    )
    with tempfile.TemporaryDirectory() as td:
        project = _write_type_project(
            Path(td),
            extra_config='reportPrivateUsage = "warning"\n',
            body=body,
        )
        plain = _run_bash(project, "set -euo pipefail\n" + ungated + "\n")
        gated = _run_makefile_recipe(project)
        from_release = _run_extracted_stage(project, _type_stage())

    assert "warning" in _plain(plain.stdout).lower()
    assert plain.returncode == 1
    assert gated.returncode == 0, gated.stdout + gated.stderr
    assert from_release.returncode == 0, from_release.stdout + from_release.stderr


@pytest.mark.skipif(shutil.which("make") is None, reason="make not on PATH")
def test_make_f_type_check_rejects_type_error() -> None:
    """The real Makefile target, not a recopied command, must fail on type errors."""
    with tempfile.TemporaryDirectory() as td:
        project = _write_type_project(
            Path(td),
            body='def f(x: int) -> int:\n    return "bad"\n',
        )
        result = subprocess.run(
            ["make", "-f", str(MAKEFILE), "type-check"],
            cwd=project,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            env=_uv_env(),
        )
    assert result.returncode != 0, result.stdout + result.stderr
    assert "error:" in _plain(result.stdout + result.stderr)
