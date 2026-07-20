"""Tests for builder/overlay.py."""

from pathlib import Path

import pytest

from vibesop.builder.overlay import OverlayMerger


class TestOverlayMerger:
    """Tests for OverlayMerger."""

    def test_load_overlay_valid(self, tmp_path: Path):
        merger = OverlayMerger()
        overlay_path = tmp_path / "overlay.yaml"
        overlay_path.write_text("metadata:\n  name: test\n")
        data = merger.load_overlay(overlay_path)
        assert isinstance(data, dict)
        assert data["metadata"]["name"] == "test"

    def test_load_overlay_invalid_yaml(self, tmp_path: Path):
        merger = OverlayMerger()
        bad_path = tmp_path / "bad.yaml"
        bad_path.write_text("::: invalid :::")
        with pytest.raises(ValueError):
            merger.load_overlay(bad_path)

