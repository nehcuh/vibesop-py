"""Platform registries must not drift (docs/dev/platform-invariants.md).

A `len >= 2` assertion let grok-build vanish from quickstart while still
appearing in SUPPORTED_PLATFORMS. Guard membership, not cardinality.
"""

from __future__ import annotations

from vibesop.builder.renderer import ConfigRenderer
from vibesop.cli.commands.verify import PLATFORM_CONFIGS
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
