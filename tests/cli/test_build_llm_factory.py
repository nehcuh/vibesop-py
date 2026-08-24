"""Tests for ``_build_llm_factory`` config-visibility warnings.

When the VibeSOP config has an ``[llm]`` section without ``api_key``, the
configured provider/api_base are dropped and the factory falls back to pure
environment-variable detection. The fallback behavior stays unchanged; it
must now be surfaced via a warning log instead of failing silently.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from unittest.mock import patch

from vibesop.cli.main import _build_llm_factory
from vibesop.core.llm_config import LLMConfig, LLMSource

if TYPE_CHECKING:
    import pytest

_GET_CONFIG = "vibesop.core.llm_config.VibeSOPConfigManager.get_llm_config"
_CREATE_PROVIDER = "vibesop.llm.factory.create_provider"
_LOGGER = "vibesop.cli.main"


def _config_without_api_key() -> LLMConfig:
    return LLMConfig(
        provider="deepseek",
        model="deepseek-v4-flash",
        api_key=None,
        api_base="https://proxy.example.com/v1",
        source=LLMSource.VIBESOP_CONFIG,
    )


class TestBuildLlmFactory:
    def test_empty_api_key_logs_warning_and_falls_back(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        factory = _build_llm_factory()

        with (
            patch(_GET_CONFIG, return_value=_config_without_api_key()),
            patch(_CREATE_PROVIDER) as create_provider,
            caplog.at_level(logging.WARNING, logger=_LOGGER),
        ):
            factory()

        # Behavior unchanged: env-var detection path (no args)
        create_provider.assert_called_once_with()
        assert any(
            r.levelno == logging.WARNING
            and "api_key is empty" in r.message
            and "deepseek" in r.message
            for r in caplog.records
        )

    def test_config_with_api_key_uses_config_without_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        factory = _build_llm_factory()
        config = _config_without_api_key()
        config.api_key = "sk-test"

        with (
            patch(_GET_CONFIG, return_value=config),
            patch(_CREATE_PROVIDER) as create_provider,
            caplog.at_level(logging.WARNING, logger=_LOGGER),
        ):
            factory()

        create_provider.assert_called_once_with(
            provider="deepseek",
            api_key="sk-test",
            base_url="https://proxy.example.com/v1",
        )
        assert not caplog.records

    def test_no_config_falls_back_without_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        factory = _build_llm_factory()

        with (
            patch(_GET_CONFIG, return_value=None),
            patch(_CREATE_PROVIDER) as create_provider,
            caplog.at_level(logging.WARNING, logger=_LOGGER),
        ):
            factory()

        create_provider.assert_called_once_with()
        assert not caplog.records
