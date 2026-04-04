"""Tests for HookInstaller class."""

from __future__ import annotations

from pathlib import Path

from vibesop.hooks.installer import HookInstaller


class TestHookInstaller:
    """Tests for HookInstaller class."""

    def test_create_installer(self) -> None:
        """Test creating a HookInstaller."""
        installer = HookInstaller()
        assert installer is not None

    def test_install_hooks(self, tmp_path: Path) -> None:
        """Test installing hooks for a platform."""
        installer = HookInstaller()

        result = installer.install_hooks(
            platform="claude-code",
            config_dir=tmp_path,
        )
        assert isinstance(result, dict)

    def test_verify_hooks(self, tmp_path: Path) -> None:
        """Test verifying hook installation."""
        installer = HookInstaller()

        result = installer.verify_hooks(
            platform="claude-code",
            config_dir=tmp_path,
        )
        assert isinstance(result, dict)
