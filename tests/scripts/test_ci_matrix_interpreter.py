"""CI matrix jobs must run the requested interpreter, not ``.python-version``.

The live ``.github/workflows/ci.yml`` payload is the contract: job-level
``UV_PYTHON`` overrides the repo pin, and a post-sync assert step fails closed
when observed major.minor != ``${{ matrix.python-version }}``. The snippet is
executed here rather than re-declared.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
MATRIX_JOBS = ("test", "test-windows")
ASSERT_STEP = "Assert interpreter matches matrix"


def _jobs() -> dict[str, Any]:
    data = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
    jobs = data["jobs"]
    assert isinstance(jobs, dict)
    return jobs


def _assert_step(job: dict[str, Any]) -> dict[str, Any]:
    for step in job["steps"]:
        if isinstance(step, dict) and step.get("name") == ASSERT_STEP:
            return step
    raise AssertionError(f"missing step {ASSERT_STEP!r}")


def _python_c_payload(run: str) -> str:
    marker = 'python -c "'
    start = run.find(marker)
    assert start != -1, run
    start += len(marker)
    end = run.rfind('"')
    assert end > start, run
    return run[start:end]


@pytest.mark.parametrize("job_id", MATRIX_JOBS)
def test_matrix_job_pins_uv_python_at_job_level(job_id: str) -> None:
    job = _jobs()[job_id]
    assert job["strategy"]["matrix"]["python-version"] == ["3.12", "3.13"]
    assert job.get("env", {}).get("UV_PYTHON") == "${{ matrix.python-version }}"


@pytest.mark.parametrize("job_id", MATRIX_JOBS)
def test_matrix_job_installs_the_matrix_interpreter(job_id: str) -> None:
    job = _jobs()[job_id]
    install = [
        step
        for step in job["steps"]
        if isinstance(step, dict) and "uv python install" in str(step.get("run", ""))
    ]
    assert install, job_id
    assert install[0]["run"] == "uv python install ${{ matrix.python-version }}"


@pytest.mark.parametrize("job_id", MATRIX_JOBS)
def test_matrix_job_asserts_interpreter_after_sync(job_id: str) -> None:
    job = _jobs()[job_id]
    names = [step.get("name", "") for step in job["steps"] if isinstance(step, dict)]
    assert names.index("Install dependencies") < names.index(ASSERT_STEP)
    step = _assert_step(job)
    assert step.get("env", {}).get("EXPECTED_PYTHON") == "${{ matrix.python-version }}"
    run = str(step["run"])
    assert "${{" not in run
    assert "$" not in run
    assert "{" not in run
    assert "sys.version_info" in run
    assert "EXPECTED_PYTHON" in run
    assert "SystemExit" in run


def test_production_assert_snippet_fails_closed_on_mismatch() -> None:
    """Execute the live YAML ``python -c`` payload against this interpreter."""
    payload = _python_c_payload(str(_assert_step(_jobs()["test"])["run"]))
    current = ".".join(map(str, sys.version_info[:2]))
    env = os.environ.copy()
    env["EXPECTED_PYTHON"] = current
    matched = subprocess.run(
        [sys.executable, "-c", payload],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert matched.returncode == 0, matched.stdout + matched.stderr

    env["EXPECTED_PYTHON"] = "0.0"
    mismatched = subprocess.run(
        [sys.executable, "-c", payload],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert mismatched.returncode != 0
    assert "interpreter" in mismatched.stdout
    assert "expected" in mismatched.stdout
