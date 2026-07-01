"""Tests for PlatformAdapter availability detection (Phase 3).

Locks in the new ``is_available()`` / ``detect()`` / ``cli_binary`` API on
PlatformAdapter — these back the ``vibe doctor`` Platform Availability section
and let users see which AI Agent executor is wired up.
"""

from unittest.mock import patch

import pytest

from vibesop.adapters import (
    ClaudeCodeAdapter,
    CursorAdapter,
    KimiCliAdapter,
    OpenCodeAdapter,
    PiCodingAgentAdapter,
)

_CONCRETE = [
    ClaudeCodeAdapter,
    OpenCodeAdapter,
    KimiCliAdapter,
    CursorAdapter,
    PiCodingAgentAdapter,
]


@pytest.mark.parametrize(
    ("cls", "binary"),
    [
        (ClaudeCodeAdapter, "claude"),
        (OpenCodeAdapter, "opencode"),
        (KimiCliAdapter, "kimi"),
        (CursorAdapter, "cursor"),
        (PiCodingAgentAdapter, "pi"),
    ],
)
def test_cli_binary_declared(cls: type, binary: str) -> None:
    """Each concrete adapter declares the CLI binary it detects."""
    assert cls.cli_binary == binary


def test_base_default_cli_binary_is_empty() -> None:
    """The base default is empty (no PATH-based detection)."""
    from vibesop.adapters.base import PlatformAdapter

    assert PlatformAdapter.cli_binary == ""


@pytest.mark.parametrize("cls", _CONCRETE)
def test_is_available_and_detect_use_shutil_which(cls: type) -> None:
    """is_available/detect resolve via shutil.which(cli_binary)."""
    adapter = cls()

    with patch("shutil.which", return_value="/usr/local/bin/fake"):
        assert adapter.is_available() is True
        assert adapter.detect() == "/usr/local/bin/fake"

    with patch("shutil.which", return_value=None):
        assert adapter.is_available() is False
        assert adapter.detect() is None
