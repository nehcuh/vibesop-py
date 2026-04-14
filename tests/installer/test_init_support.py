"""Tests for InitSupport class."""

from __future__ import annotations

from typing import TYPE_CHECKING

from vibesop.installer.init_support import InitSupport

if TYPE_CHECKING:
    from pathlib import Path


class TestInitSupport:
    """Tests for project initialization support."""

    def test_init_project(self, tmp_path: Path) -> None:
        """Test initializing a project with VibeSOP."""
        init = InitSupport()
        result = init.init_project(project_path=tmp_path)

        assert result["success"] is True
        assert (tmp_path / ".vibe").exists()

    def test_init_project_creates_config(self, tmp_path: Path) -> None:
        """Test that init_project creates config.yaml."""
        init = InitSupport()
        init.init_project(project_path=tmp_path)

        config_file = tmp_path / ".vibe" / "config.yaml"
        assert config_file.exists()
