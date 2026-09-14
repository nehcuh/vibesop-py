"""Routing hot-path tests must run only in the dedicated benchmark job.

The live ``ci.yml`` marker filters are the contract. Collection is executed
against those production expressions so an unmarked load-sensitive file
cannot re-enter the default suite.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
HOT_PATH = "tests/benchmark/test_routing_hot_path.py"
BENCHMARK_DIR = "tests/benchmark"


def _jobs() -> dict[str, Any]:
    data = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
    jobs = data["jobs"]
    assert isinstance(jobs, dict)
    return jobs


def _marker_from_run(run: str) -> str:
    quoted = re.search(r'-m\s+"([^"]+)"', run)
    if quoted:
        return quoted.group(1)
    bare = re.search(r"-m\s+(\S+)", run)
    assert bare, run
    return bare.group(1)


def _job_pytest_marker(job_id: str, *, needle: str) -> str:
    job = _jobs()[job_id]
    for step in job["steps"]:
        if not isinstance(step, dict):
            continue
        run = str(step.get("run", ""))
        if "pytest" in run and needle in run:
            return _marker_from_run(run)
    raise AssertionError(f"{job_id} has no pytest step containing {needle!r}")


def _collect(marker: str, path: str) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-m",
            marker,
            path,
            "-p",
            "no:cacheprovider",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    return proc


def _nodeids(collected: str, needle: str) -> list[str]:
    return [line for line in collected.splitlines() if needle in line and line.startswith("tests/")]


def test_ci_regression_jobs_exclude_benchmark() -> None:
    for job_id in ("test", "test-windows"):
        marker = _job_pytest_marker(job_id, needle="not benchmark")
        assert marker == "not benchmark and not slow"


def test_ci_benchmark_job_selects_benchmark_marker() -> None:
    marker = _job_pytest_marker("benchmark", needle="-m benchmark")
    assert marker == "benchmark"


def test_hot_path_is_deselected_by_ci_regression_filter() -> None:
    marker = _job_pytest_marker("test", needle="not benchmark")
    proc = _collect(marker, HOT_PATH)
    out = proc.stdout + proc.stderr
    # pytest exits 5 when every collected item is deselected.
    assert proc.returncode in {0, 5}, out
    assert _nodeids(out, "test_routing_hot_path.py") == []
    assert "4 deselected" in out


def test_hot_path_is_selected_by_ci_benchmark_filter() -> None:
    marker = _job_pytest_marker("benchmark", needle="-m benchmark")
    proc = _collect(marker, HOT_PATH)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    nodeids = _nodeids(out, "test_routing_hot_path.py")
    assert len(nodeids) == 4, out


def test_benchmark_directory_is_excluded_from_ci_regression_filter() -> None:
    marker = _job_pytest_marker("test", needle="not benchmark")
    proc = _collect(marker, BENCHMARK_DIR)
    out = proc.stdout + proc.stderr
    assert proc.returncode in {0, 5}, out
    assert _nodeids(out, "tests/benchmark/") == []
    assert "deselected" in out
