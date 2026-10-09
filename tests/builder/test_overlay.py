"""Tests for builder/overlay.py."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from vibesop.adapters.models import Manifest, ManifestMetadata, RoutingPolicy
from vibesop.builder.overlay import OverlayMerger, create_overlay, validate_overlay


def _base_manifest() -> Manifest:
    manifest = Manifest(metadata=ManifestMetadata(platform="claude-code"))
    manifest.policies.routing = RoutingPolicy(confidence_threshold=0.6, max_candidates=7)
    return manifest


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

    def test_create_overlay_roundtrip_keeps_threshold(self, tmp_path: Path) -> None:
        """0.9 written by create_overlay must survive merge, not fall back to 0.6."""
        overlay_path = tmp_path / "overlay.yaml"
        create_overlay(
            overlay_path,
            security={"scan_external_content": False, "max_file_size": 2048},
            routing={"confidence_threshold": 0.9, "max_candidates": 1},
        )

        loaded = OverlayMerger().load_overlay(overlay_path)
        assert loaded["policies"]["routing"]["confidence_threshold"] == 0.9
        assert loaded["policies"]["security"]["scan_external_content"] is False

        merged = OverlayMerger().merge(_base_manifest(), overlay_path)
        assert merged.policies.routing.confidence_threshold == 0.9
        assert merged.policies.routing.max_candidates == 1
        assert merged.policies.security.scan_external_content is False
        assert merged.policies.security.max_file_size == 2048
        assert validate_overlay(overlay_path) == []

    def test_partial_overlay_preserves_unspecified_routing_field(self, tmp_path: Path) -> None:
        overlay_path = tmp_path / "overlay.yaml"
        create_overlay(overlay_path, routing={"confidence_threshold": 0.9})

        merged = OverlayMerger().merge(_base_manifest(), overlay_path)
        assert merged.policies.routing.confidence_threshold == 0.9
        assert merged.policies.routing.max_candidates == 7

    def test_legacy_top_level_policy_still_merges(self, tmp_path: Path) -> None:
        """Pre-D09 files kept security/routing at the top level."""
        overlay_path = tmp_path / "legacy.yaml"
        overlay_path.write_text(
            "security:\n  scan_external_content: false\nrouting:\n  confidence_threshold: 0.9\n",
            encoding="utf-8",
        )

        errors = validate_overlay(overlay_path)
        assert errors
        assert any("routing" in err or "security" in err for err in errors)

        merged = OverlayMerger().merge(_base_manifest(), overlay_path)
        assert merged.policies.routing.confidence_threshold == 0.9
        assert merged.policies.security.scan_external_content is False
        assert merged.policies.routing.max_candidates == 7

    def test_canonical_policy_wins_over_legacy_top_level(self, tmp_path: Path) -> None:
        overlay_path = tmp_path / "both.yaml"
        overlay_path.write_text(
            "policies:\n"
            "  routing:\n"
            "    confidence_threshold: 0.9\n"
            "routing:\n"
            "  confidence_threshold: 0.2\n",
            encoding="utf-8",
        )

        assert validate_overlay(overlay_path)
        merged = OverlayMerger().merge(_base_manifest(), overlay_path)
        assert merged.policies.routing.confidence_threshold == 0.9

    def test_validate_rejects_illegal_policy_value(self, tmp_path: Path) -> None:
        overlay_path = tmp_path / "illegal.yaml"
        create_overlay(
            overlay_path,
            routing={"confidence_threshold": 1.5},
            security={"allow_path_traversal": True},
        )

        errors = validate_overlay(overlay_path)
        assert any("confidence_threshold" in err for err in errors)
        assert any("allow_path_traversal" in err for err in errors)
        with pytest.raises(ValidationError):
            OverlayMerger().merge(_base_manifest(), overlay_path)
