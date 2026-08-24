"""Tests for the UnifiedRouter prompt_builder-missing warning.

Without a prompt_builder, AI triage falls back to a one-line prompt
("Query: ... Select best skill.") that LLMs tend to answer as chat, so
skill selection fails silently. The constructor now logs a warning; the
behavior itself is unchanged.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from vibesop.core.routing import UnifiedRouter

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

_LOGGER = "vibesop.core.routing.unified"


class TestPromptBuilderWarning:
    def test_missing_prompt_builder_logs_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING, logger=_LOGGER):
            UnifiedRouter(project_root=tmp_path)

        assert any(
            r.levelno == logging.WARNING and "prompt_builder" in r.message for r in caplog.records
        )

    def test_provided_prompt_builder_no_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING, logger=_LOGGER):
            UnifiedRouter(
                project_root=tmp_path,
                prompt_builder=lambda query, summary, version: "prompt",
            )

        assert not [r for r in caplog.records if "prompt_builder" in r.message]
