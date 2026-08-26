"""Platform registries must not drift (docs/dev/platform-invariants.md).

A `len >= 2` assertion let grok-build vanish from quickstart while still
appearing in SUPPORTED_PLATFORMS. Guard membership, not cardinality.
"""

from __future__ import annotations

from vibesop.builder.renderer import ConfigRenderer
from vibesop.cli.commands.verify import (
    PLATFORM_CONFIGS,
    collect_settings_hook_commands,
    unsafe_windows_hook_command_reason,
)
from vibesop.constants import SUPPORTED_PLATFORMS
from vibesop.installer.installer import VibeSOPInstaller
from vibesop.installer.quickstart_runner import QuickstartRunner


def test_installer_platforms_are_supported() -> None:
    names = {p["name"] for p in VibeSOPInstaller().list_platforms()}
    assert names <= set(SUPPORTED_PLATFORMS)
    assert "grok-build" in names


def test_quickstart_matches_installer() -> None:
    installer = {p["name"] for p in VibeSOPInstaller().list_platforms()}
    quickstart = set(QuickstartRunner()._supported_platforms)
    assert quickstart == installer


def test_renderer_adapters_are_supported() -> None:
    assert set(ConfigRenderer._adapters) <= set(SUPPORTED_PLATFORMS)
    assert "grok-build" in ConfigRenderer._adapters


def test_verify_covers_installer_platforms() -> None:
    installer = {p["name"] for p in VibeSOPInstaller().list_platforms()}
    assert installer <= set(PLATFORM_CONFIGS)
    assert "grok-build" in PLATFORM_CONFIGS


def test_grok_verify_checks_vibe_on_path() -> None:
    assert "vibe_on_path" in PLATFORM_CONFIGS["grok-build"]["checks"]


def test_claude_verify_checks_hook_command_safety() -> None:
    assert "route_hook_command" in PLATFORM_CONFIGS["claude-code"]["checks"]


def test_unsafe_hook_command_detects_backslash_and_git_bash_wrapper() -> None:
    assert unsafe_windows_hook_command_reason(r"bash C:\Users\x\.claude\hooks\x.sh")
    assert unsafe_windows_hook_command_reason(
        '"C:/Program Files/Git/bin/bash.exe" "C:/Users/x/.claude/hooks/x.sh"'
    )
    assert unsafe_windows_hook_command_reason('"C:/Users/x/.claude/hooks/x.sh"') is None


def test_collect_settings_hook_commands_walks_nested_hooks() -> None:
    settings = {
        "hooks": {
            "UserPromptSubmit": [
                {"hooks": [{"type": "command", "command": '"C:/Users/x/.claude/hooks/a.sh"'}]}
            ]
        }
    }
    assert collect_settings_hook_commands(settings) == ['"C:/Users/x/.claude/hooks/a.sh"']
