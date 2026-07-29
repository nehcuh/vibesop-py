"""Tests for dev/test environment auto-detection.

Note: pytest re-injects ``PYTEST_CURRENT_TEST`` at the start of the call
phase (after fixture setup), so env cleanup must happen INSIDE each test
body rather than in a fixture.
"""

from __future__ import annotations

import sys

import pytest

from vibesop.core.observability.dev_detect import ENV_OVERRIDE, is_dev_environment


def _strip_signals(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove every signal is_dev_environment inspects.

    Must be called inside the test body — pytest sets PYTEST_CURRENT_TEST
    between fixture setup and test call.
    """
    monkeypatch.delenv(ENV_OVERRIDE, raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)


class TestEnvOverride:
    def test_explicit_dev(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _strip_signals(monkeypatch)
        monkeypatch.setenv(ENV_OVERRIDE, "dev")
        assert is_dev_environment() is True

    def test_explicit_prod(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _strip_signals(monkeypatch)
        monkeypatch.setenv(ENV_OVERRIDE, "prod")
        assert is_dev_environment() is False

    def test_override_beats_pytest_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # PYTEST_CURRENT_TEST is set during real pytest runs (this very test).
        # Override must win even when pytest signals are present.
        monkeypatch.setenv(ENV_OVERRIDE, "prod")
        assert is_dev_environment() is False

    def test_override_case_insensitive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _strip_signals(monkeypatch)
        monkeypatch.setenv(ENV_OVERRIDE, "  PROD  ")
        assert is_dev_environment() is False

    @pytest.mark.parametrize("token", ["dev", "test", "1", "true"])
    def test_dev_tokens(self, monkeypatch: pytest.MonkeyPatch, token: str) -> None:
        _strip_signals(monkeypatch)
        monkeypatch.setenv(ENV_OVERRIDE, token)
        assert is_dev_environment() is True

    @pytest.mark.parametrize("token", ["prod", "production", "0", "false"])
    def test_prod_tokens(self, monkeypatch: pytest.MonkeyPatch, token: str) -> None:
        _strip_signals(monkeypatch)
        monkeypatch.setenv(ENV_OVERRIDE, token)
        assert is_dev_environment() is False


class TestPytestDetection:
    def test_pytest_current_test_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Already set by pytest during this test — just verify detection fires
        _strip_signals(monkeypatch)
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_x.py::test_y (call)")
        assert is_dev_environment() is True

    def test_argv0_pytest(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _strip_signals(monkeypatch)
        monkeypatch.setattr(sys, "argv", ["/usr/local/bin/pytest", "tests/"])
        assert is_dev_environment() is True

    def test_argv0_pytest_exe(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _strip_signals(monkeypatch)
        monkeypatch.setattr(sys, "argv", ["C:\\venv\\Scripts\\pytest.exe"])
        assert is_dev_environment() is True

    def test_dash_m_pytest(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _strip_signals(monkeypatch)
        # python -m pytest tests/
        monkeypatch.setattr(sys, "argv", ["python", "-m", "pytest", "tests/"])
        assert is_dev_environment() is True


class TestProdFallback:
    def test_empty_argv_not_dev(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _strip_signals(monkeypatch)
        monkeypatch.setattr(sys, "argv", [])
        assert is_dev_environment() is False

    def test_vibe_cli_argv_not_dev(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _strip_signals(monkeypatch)
        monkeypatch.setattr(sys, "argv", ["/usr/local/bin/vibe", "route", "hello"])
        assert is_dev_environment() is False

    def test_python_script_not_dev(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _strip_signals(monkeypatch)
        monkeypatch.setattr(sys, "argv", ["python", "scripts/bootstrap.py"])
        assert is_dev_environment() is False

    def test_empty_env_not_dev(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _strip_signals(monkeypatch)
        monkeypatch.setattr(sys, "argv", ["python"])
        assert is_dev_environment() is False
