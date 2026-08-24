"""Tests for ``VibeSOPConfigManager.get_llm_config`` fallback visibility.

Two previously silent failure modes are now logged:
- a config file that exists but fails to parse -> warning (path + error)
- no usable project config in cwd, falling back to the ~/.vibe global
  config -> info log naming the actual file used
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from vibesop.core.llm_config import VibeSOPConfigManager

if TYPE_CHECKING:
    import pytest

_LOGGER = "vibesop.core.llm_config"


class TestGetLlmConfigVisibility:
    def test_parse_failure_logs_warning(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        bad = tmp_path / "config.toml"
        bad.write_text("not [valid toml =", encoding="utf-8")
        monkeypatch.setattr(VibeSOPConfigManager, "CONFIG_PATHS", [bad])

        with caplog.at_level(logging.WARNING, logger=_LOGGER):
            result = VibeSOPConfigManager.get_llm_config()

        assert result is None
        assert any(r.levelno == logging.WARNING and str(bad) in r.message for r in caplog.records)

    def test_home_fallback_logs_actual_path(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        # Path.home() is redirected to an isolated tmp dir by the autouse
        # _isolated_home fixture, so this is not the real user home.
        home_config = Path.home() / ".vibe" / "config.toml"
        home_config.parent.mkdir(parents=True, exist_ok=True)
        home_config.write_text(
            '[llm]\nprovider = "deepseek"\nmodel = "deepseek-v4-flash"\n',
            encoding="utf-8",
        )
        missing_project = tmp_path / "proj" / ".vibe" / "config.toml"
        monkeypatch.setattr(
            VibeSOPConfigManager,
            "CONFIG_PATHS",
            [missing_project, home_config],
        )

        with caplog.at_level(logging.INFO, logger=_LOGGER):
            result = VibeSOPConfigManager.get_llm_config()

        assert result is not None
        assert result.provider == "deepseek"
        assert any(
            r.levelno == logging.INFO and str(home_config) in r.message for r in caplog.records
        )

    def test_project_config_used_without_fallback_log(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        project_config = tmp_path / "proj" / ".vibe" / "config.toml"
        project_config.parent.mkdir(parents=True)
        project_config.write_text('[llm]\nprovider = "kimi"\n', encoding="utf-8")
        monkeypatch.setattr(VibeSOPConfigManager, "CONFIG_PATHS", [project_config])

        with caplog.at_level(logging.INFO, logger=_LOGGER):
            result = VibeSOPConfigManager.get_llm_config()

        assert result is not None
        assert result.provider == "kimi"
        assert not [r for r in caplog.records if r.levelno >= logging.INFO]
