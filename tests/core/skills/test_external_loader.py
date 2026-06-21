"""Tests for external skill loader."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from vibesop.core.skills.external_loader import (
    ExternalSkillLoader,
    ExternalSkillMetadata,
    SkillSource,
    discover_external_skills,
    is_skill_safe,
)
from vibesop.spec.models import SkillSpec


def _make_meta(skill_id="test/skill"):
    return SkillSpec(
        id=skill_id,
        name="Test",
        description="Desc",
        intent="Do things",
    )


class TestSkillSource:
    """Test SkillSource enum."""

    def test_values(self):
        assert SkillSource.BUILTIN.value == "builtin"
        assert SkillSource.PROJECT.value == "project"
        assert SkillSource.EXTERNAL.value == "external"
        assert SkillSource.PACK.value == "pack"


class TestExternalSkillMetadata:
    """Test ExternalSkillMetadata dataclass."""

    def test_creation(self):
        meta = ExternalSkillMetadata(
            base_metadata=_make_meta(),
            source=SkillSource.EXTERNAL,
        )
        assert meta.source == SkillSource.EXTERNAL
        assert meta.is_trusted is False
        assert meta.audit_result is None

    def test_is_safe_with_passing_audit(self):
        mock_audit = MagicMock()
        mock_audit.is_safe = True
        meta = ExternalSkillMetadata(
            base_metadata=_make_meta(),
            source=SkillSource.EXTERNAL,
            audit_result=mock_audit,
        )
        assert meta.is_safe is True

    def test_is_safe_without_audit(self):
        meta = ExternalSkillMetadata(
            base_metadata=_make_meta(),
            source=SkillSource.EXTERNAL,
        )
        assert meta.is_safe is False

    def test_is_safe_with_failing_audit(self):
        mock_audit = MagicMock()
        mock_audit.is_safe = False
        meta = ExternalSkillMetadata(
            base_metadata=_make_meta(),
            source=SkillSource.EXTERNAL,
            audit_result=mock_audit,
        )
        assert meta.is_safe is False

    def test_to_dict(self):
        meta = ExternalSkillMetadata(
            base_metadata=_make_meta("my/skill"),
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
            base_metadata=_make_meta(),
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

    def test_with_auditor(self, tmp_path: Path):
        mock_auditor = MagicMock()
        paths = [tmp_path / "skills"]
        paths[0].mkdir()
        loader = ExternalSkillLoader(external_paths=paths, auditor=mock_auditor)
        assert loader._auditor is mock_auditor
        mock_auditor.add_allowed_path.assert_called()

    def test_set_default_auditor_factory(self):
        factory = MagicMock()
        ExternalSkillLoader.set_default_auditor_factory(factory)
        assert ExternalSkillLoader._default_auditor_factory is factory
        # Reset after test
        ExternalSkillLoader._default_auditor_factory = None


class TestExternalSkillLoaderDiscover:
    """Test discover_all and discover_from_pack."""

    def test_discover_returns_cache(self, tmp_path: Path):
        loader = ExternalSkillLoader(
            external_paths=[tmp_path / "nonexistent"],
            require_audit=False,
        )
        # Pre-populate cache
        fake = ExternalSkillMetadata(
            base_metadata=_make_meta("cached/skill"),
            source=SkillSource.EXTERNAL,
        )
        loader._cache["cached/skill"] = fake
        result = loader.discover_all()
        assert "cached/skill" in result

    def test_discover_force_reload(self, tmp_path: Path):
        loader = ExternalSkillLoader(
            external_paths=[tmp_path / "nonexistent"],
            require_audit=False,
        )
        fake = ExternalSkillMetadata(
            base_metadata=_make_meta("cached/skill"),
            source=SkillSource.EXTERNAL,
        )
        loader._cache["cached/skill"] = fake
        result = loader.discover_all(force_reload=True)
        # Cache cleared and reloaded
        assert result is not None

    def test_discover_skips_missing_paths(self, tmp_path: Path):
        loader = ExternalSkillLoader(
            external_paths=[tmp_path / "nonexistent"],
            require_audit=False,
        )
        result = loader.discover_all()
        assert result == {}

    def test_discover_from_pack_missing_pack(self, tmp_path: Path):
        loader = ExternalSkillLoader(require_audit=False)
        result = loader.discover_from_pack("nonexistent", tmp_path / "missing")
        assert result == {}

    def test_discover_from_pack(self, tmp_path: Path):
        pack_dir = tmp_path / "test-pack"
        skill_dir = pack_dir / "skills" / "my-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("""---
id: test-skill
name: Test Skill
description: A skill from a pack
---
# Content
""")
        loader = ExternalSkillLoader(require_audit=False)
        result = loader.discover_from_pack("test-pack", pack_dir)
        assert len(result) >= 1

    def test_discover_from_pack_with_version(self, tmp_path: Path):
        pack_dir = tmp_path / "versioned-pack"
        pack_dir.mkdir()
        (pack_dir / "pack.json").write_text('{"version": "2.0.0"}')
        skill_dir = pack_dir / "skills" / "my-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("""---
id: v-skill
name: Versioned
description: Versioned skill
---
# Content
""")
        loader = ExternalSkillLoader(require_audit=False)
        result = loader.discover_from_pack("versioned-pack", pack_dir)
        assert len(result) >= 1
        skill = list(result.values())[0]
        assert skill.pack_version == "2.0.0"


class TestExternalSkillLoaderLoad:
    """Test load_skill and related methods."""

    def test_load_skill_from_cache(self, tmp_path: Path):
        loader = ExternalSkillLoader(
            external_paths=[tmp_path / "nonexistent"],
            require_audit=False,
        )
        fake = ExternalSkillMetadata(
            base_metadata=_make_meta("cached/skill"),
            source=SkillSource.EXTERNAL,
        )
        loader._cache["cached/skill"] = fake
        result = loader.load_skill("cached/skill")
        assert result is not None

    def test_load_skill_missing_no_fallback(self, tmp_path: Path):
        loader = ExternalSkillLoader(
            external_paths=[tmp_path / "nonexistent"],
            require_audit=False,
        )
        result = loader.load_skill("nonexistent", fallback_to_builtin=False)
        assert result is None

    def test_load_skill_unsafe_blocked(self, tmp_path: Path):
        loader = ExternalSkillLoader(
            external_paths=[tmp_path / "nonexistent"],
            require_audit=True,
        )
        unsafe = ExternalSkillMetadata(
            base_metadata=_make_meta("unsafe/skill"),
            source=SkillSource.EXTERNAL,
        )
        loader._cache["unsafe/skill"] = unsafe
        result = loader.load_skill("unsafe/skill")
        assert result is None

    def test_is_safe_to_load_true(self, tmp_path: Path):
        loader = ExternalSkillLoader(
            external_paths=[tmp_path / "nonexistent"],
            require_audit=False,
        )
        mock_audit = MagicMock()
        mock_audit.is_safe = True
        safe = ExternalSkillMetadata(
            base_metadata=_make_meta("safe/skill"),
            source=SkillSource.EXTERNAL,
            audit_result=mock_audit,
        )
        loader._cache["safe/skill"] = safe
        assert loader.is_safe_to_load("safe/skill") is True

    def test_is_safe_to_load_missing(self, tmp_path: Path):
        loader = ExternalSkillLoader(
            external_paths=[tmp_path / "nonexistent"],
            require_audit=False,
        )
        assert loader.is_safe_to_load("nonexistent") is False

    def test_get_unsafe_skills(self, tmp_path: Path):
        loader = ExternalSkillLoader(
            external_paths=[tmp_path / "nonexistent"],
            require_audit=False,
        )
        mock_audit = MagicMock()
        mock_audit.is_safe = False
        unsafe = ExternalSkillMetadata(
            base_metadata=_make_meta("unsafe/skill"),
            source=SkillSource.EXTERNAL,
            audit_result=mock_audit,
        )
        loader._cache["unsafe/skill"] = unsafe
        result = loader.get_unsafe_skills()
        assert len(result) == 1


class TestExternalSkillLoaderSupportedPacks:
    """Test get_supported_packs."""

    def test_returns_packs_info(self):
        loader = ExternalSkillLoader(require_audit=False)
        packs = loader.get_supported_packs()
        assert isinstance(packs, dict)
        # Verify known packs are listed
        for pack_name in ["gstack", "superpowers", "omx"]:
            if pack_name in loader.TRUSTED_PACKS:
                assert pack_name in packs
                assert "url" in packs[pack_name]
                assert "installed" in packs[pack_name]


class TestExternalSkillLoaderPackVersion:
    """Test _get_pack_version."""

    def test_pack_json(self, tmp_path: Path):
        (tmp_path / "pack.json").write_text('{"version": "1.2.3"}')
        loader = ExternalSkillLoader(require_audit=False)
        version = loader._get_pack_version(tmp_path, "test")
        assert version == "1.2.3"

    def test_package_json(self, tmp_path: Path):
        (tmp_path / "package.json").write_text('{"version": "4.5.6"}')
        loader = ExternalSkillLoader(require_audit=False)
        version = loader._get_pack_version(tmp_path, "test")
        assert version == "4.5.6"

    def test_pack_json_priority(self, tmp_path: Path):
        (tmp_path / "pack.json").write_text('{"version": "1.0.0"}')
        (tmp_path / "package.json").write_text('{"version": "2.0.0"}')
        loader = ExternalSkillLoader(require_audit=False)
        version = loader._get_pack_version(tmp_path, "test")
        assert version == "1.0.0"  # pack.json takes priority

    def test_no_version_file(self, tmp_path: Path):
        loader = ExternalSkillLoader(require_audit=False)
        version = loader._get_pack_version(tmp_path, "test")
        assert version is None

    def test_invalid_json(self, tmp_path: Path):
        (tmp_path / "pack.json").write_text("not json")
        loader = ExternalSkillLoader(require_audit=False)
        version = loader._get_pack_version(tmp_path, "test")
        assert version is None


class TestExternalSkillLoaderParseAndAudit:
    """Test _parse_and_audit."""

    def test_rejects_high_threat_untrusted_skill(self, tmp_path: Path):
        mock_auditor = MagicMock()
        threat = MagicMock()
        threat.level.value = "high"
        threat.name = "RoleHijacking"

        mock_result = MagicMock()
        mock_result.is_safe = False
        mock_result.threats = [threat]

        mock_auditor.audit_skill_file.return_value = mock_result

        loader = ExternalSkillLoader(require_audit=True, auditor=mock_auditor)
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("# Test")

        result = loader._parse_and_audit(
            skill_dir=tmp_path,
            skill_file=skill_file,
            pack_name="untrusted-pack",
            is_trusted=False,
        )
        assert result is None

    def test_allows_trusted_pack_with_high_threat(self, tmp_path: Path):
        mock_auditor = MagicMock()
        threat = MagicMock()
        threat.level.value = "high"
        threat.name = "RoleHijacking"

        mock_result = MagicMock()
        mock_result.is_safe = False
        mock_result.threats = [threat]

        mock_auditor.audit_skill_file.return_value = mock_result

        loader = ExternalSkillLoader(require_audit=True, auditor=mock_auditor)
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("""---
id: trusted-skill
name: Trusted
description: A trusted skill
---
# Content
""")
        from vibesop.constants import TRUSTED_PACKS

        pack_name = list(TRUSTED_PACKS.keys())[0] if TRUSTED_PACKS else "gstack"

        result = loader._parse_and_audit(
            skill_dir=tmp_path,
            skill_file=skill_file,
            pack_name=pack_name,
            is_trusted=True,
        )
        assert result is not None

    def test_parse_and_audit_no_auditor(self, tmp_path: Path):
        loader = ExternalSkillLoader(require_audit=False)
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("""---
id: test-skill
name: Test
description: A test skill
---
# Content
""")
        result = loader._parse_and_audit(
            skill_dir=tmp_path,
            skill_file=skill_file,
        )
        assert result is not None
        assert result.base_metadata.id == "test-skill"
        assert result.source == SkillSource.EXTERNAL

    def test_parse_and_audit_with_pack_name(self, tmp_path: Path):
        loader = ExternalSkillLoader(require_audit=False)
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("""---
id: pack-skill
name: Pack Skill
description: From a pack
---
# Content
""")
        result = loader._parse_and_audit(
            skill_dir=tmp_path,
            skill_file=skill_file,
            pack_name="superpowers",
            pack_version="1.0.0",
            is_trusted=True,
        )
        assert result is not None
        assert result.source == SkillSource.PACK
        assert result.pack_name == "superpowers"
        assert result.is_trusted is True

    def test_parse_and_audit_returns_none_for_invalid_skill_md(self, tmp_path: Path):
        loader = ExternalSkillLoader(require_audit=False)
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("Just some text without frontmatter")
        result = loader._parse_and_audit(
            skill_dir=tmp_path,
            skill_file=skill_file,
        )
        assert result is None


class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    def test_discover_external_skills(self, tmp_path: Path):
        with patch(
            "vibesop.core.skills.external_loader.ExternalSkillLoader.EXTERNAL_PATHS",
            [tmp_path / "nonexistent"],
        ):
            result = discover_external_skills(require_audit=False)
            assert result == {}

    def test_is_skill_safe(self, tmp_path: Path):
        with patch(
            "vibesop.core.skills.external_loader.ExternalSkillLoader.EXTERNAL_PATHS",
            [tmp_path / "nonexistent"],
        ):
            result = is_skill_safe("nonexistent")
            assert result is False
