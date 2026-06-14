"""Tests for ContainerValidator — runtime detection + report dataclasses.

These tests avoid actually creating containers (slow + needs Docker).
We test the data flow, runtime detection (with mocks), and report
serialization only.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from vibesop.core.prompt_chain import ContainerValidator, ValidationReport


class TestRuntimeDetection:
    """Runtime auto-detection (orbstack → docker → lima → local)."""

    def test_detect_returns_local_when_nothing_available(self) -> None:
        """When every subprocess.run fails, fallback to 'local'."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            tool = ContainerValidator._detect_runtime()
        assert tool == "local"

    def test_detect_prefers_orbstack(self) -> None:
        """If orbctl returns 0, pick orbstack."""

        def fake_run(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
            if cmd[0] == "orbctl":
                return subprocess.CompletedProcess(cmd, 0, "ok", "")
            return subprocess.CompletedProcess(cmd, 1, "", "nope")

        with patch("subprocess.run", side_effect=fake_run):
            tool = ContainerValidator._detect_runtime()
        assert tool == "orbstack"

    def test_detect_falls_back_to_docker(self) -> None:
        """If orbctl missing but docker works, pick docker."""

        def fake_run(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
            if cmd[0] == "orbctl":
                raise FileNotFoundError()
            if cmd[0] == "docker":
                return subprocess.CompletedProcess(cmd, 0, "ok", "")
            return subprocess.CompletedProcess(cmd, 1, "", "")

        with patch("subprocess.run", side_effect=fake_run):
            tool = ContainerValidator._detect_runtime()
        assert tool == "docker"

    def test_explicit_tool_overrides_detection(self) -> None:
        """Passing container_tool= skips detection."""
        v = ContainerValidator(container_tool="docker")
        assert v.container_tool == "docker"


class TestValidationReportDataclass:
    """Report serialization."""

    def test_to_dict_round_trip(self) -> None:
        report = ValidationReport(
            environment={"container_tool": "docker", "python": "3.12"},
            results={"imports": {"vibesop.core": True}},
            p0_issues=[],
            p1_issues=[],
            conclusion="✅ pass",
            duration_s=12.5,
        )
        d = report.to_dict()
        assert d["environment"]["container_tool"] == "docker"
        assert d["results"]["imports"]["vibesop.core"] is True
        assert d["conclusion"] == "✅ pass"
        assert d["duration_s"] == 12.5

    def test_to_json_is_valid_json(self) -> None:
        report = ValidationReport(conclusion="✅ ok", duration_s=1.0)
        data = json.loads(report.to_json())
        assert data["conclusion"] == "✅ ok"
        assert data["duration_s"] == 1.0

    def test_to_json_handles_unicode(self) -> None:
        report = ValidationReport(conclusion="✅ 验证通过 — 中文")
        data = json.loads(report.to_json())
        assert "中文" in data["conclusion"]


class TestCollectIssues:
    """Issue aggregation from results dict."""

    def test_collects_false_booleans(self) -> None:
        results = {
            "imports": {"mod.a": True, "mod.b": False},
            "build": {"claude-code": True, "kimi-cli": False},
        }
        issues = ContainerValidator._collect_issues(results)
        # 2 failures recorded
        assert len(issues) == 2
        checks = {i["check"] for i in issues}
        assert "imports.mod.b" in checks
        assert "build.kimi-cli" in checks

    def test_records_passed_only_for_passed_key(self) -> None:
        """For dict values like {passed: bool}, only False triggers."""
        results = {
            "unit_tests": {"passed": True, "output_tail": "..."},
            "hook_path": {"passed": False, "detail": "..."},
        }
        issues = ContainerValidator._collect_issues(results)
        # only unit_tests.passed would not trigger (True),
        # but hook_path.passed=False does
        assert any(i["check"] == "hook_path.passed" for i in issues)


class TestLocalModeValidate:
    """``validate(skip_container=True)`` runs locally without container setup."""

    def test_validate_local_runs_checks(self, tmp_path: Path) -> None:
        """In local mode, validator runs checks via local Python."""
        v = ContainerValidator(project_root=tmp_path, container_tool="local")
        report = v.validate(skip_container=True)
        # All check categories should be present
        assert "imports" in report.results
        assert "unit_tests" in report.results
        assert "cli_modes" in report.results
        assert "hook_path" in report.results
        assert "build" in report.results
        assert report.environment["container_tool"] == "local"
        # Python version always populated
        assert "python" in report.environment
        assert report.duration_s >= 0
