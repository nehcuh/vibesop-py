"""Tests for external skill loader."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from vibesop.core.skills.external_loader import ExternalSkillLoader, ExternalSkillMetadata, SkillSource
from vibesop.security.exceptions import SecurityError


class TestSkillSource:
    """Test SkillSource enum."""

    def test_values(self):
        assert SkillSource.BUILTIN.value == "builtin"
        assert SkillSource.PROJECT.value == "project"
        assert SkillSource.EXTERNAL.value == "external"
        assert SkillSource.PACK.value == "pack"


class TestExternalSkillMetadata:
    """Test ExternalSkillMetadata dataclass."""

    def _make_meta(self, skill_id: str = "test/skill"):
        mock = MagicMock()
        mock.id = skill_id
        mock.name = "Test"
        mock.description = "Desc"
        return mock

    def test_creation(self):
        meta = ExternalSkillMetadata(
            base_metadata=self._make_meta(),
            source=SkillSource.EXTERNAL,
        )
        assert meta.source == SkillSource.EXTERNAL
        assert meta.is_trusted is False
        assert meta.audit_result is None

    def test_is_safe_with_passing_audit(self):
        mock_audit = MagicMock()
        mock_audit.is_safe = True
        meta = ExternalSkillMetadata(
            base_metadata=self._make_meta(),
            source=SkillSource.EXTERNAL,
            audit_result=mock_audit,
        )
        assert meta.is_safe is True

    def test_is_safe_without_audit(self):
        meta = ExternalSkillMetadata(
            base_metadata=self._make_meta(),
            source=SkillSource.EXTERNAL,
        )
        assert meta.is_safe is False

    def test_is_safe_with_failing_audit(self):
        mock_audit = MagicMock()
        mock_audit.is_safe = False
        meta = ExternalSkillMetadata(
            base_metadata=self._make_meta(),
            source=SkillSource.EXTERNAL,
            audit_result=mock_audit,
        )
        assert meta.is_safe is False

    def test_to_dict(self):
        meta = ExternalSkillMetadata(
            base_metadata=self._make_meta("my/skill"),
            source=SkillSource.PACK,
            pack_name="superpowers",
            pack_version="1.0.0",
            install_path=Path("/tmp/skill"),
            is_trusted=True,
        )
        d = meta.to_dict()
        assert d["id"] == "my/skill"
        assert d["source"] == "pack"
        assert d["pack_name"] == "superpowers"
        assert d["is_trusted"] is True

    def test_to_dict_no_path(self):
        meta = ExternalSkillMetadata(
            base_metadata=self._make_meta(),
            source=SkillSource.BUILTIN,
        )
        d = meta.to_dict()
        assert d["install_path"] is None


class TestExternalSkillLoaderInit:
    """Test ExternalSkillLoader initialization."""

    def test_default_init(self):
        loader = ExternalSkillLoader()
        assert loader._require_audit is True
        assert loader._strict_mode is True

    def test_custom_paths(self, tmp_path: Path):
        paths = [tmp_path / "skills"]
        loader = ExternalSkillLoader(external_paths=paths)
        assert loader.external_paths == paths
