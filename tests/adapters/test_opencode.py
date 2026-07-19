"""Tests for OpenCodeAdapter."""

import sys
from pathlib import Path
from typing import ClassVar

import pytest

from vibesop.adapters import OpenCodeAdapter
from vibesop.adapters.models import (
    Manifest,
    ManifestMetadata,
    PolicySet,
    RoutingPolicy,
    SecurityPolicy,
)
from vibesop.spec import SkillSpec


class TestOpenCodeAdapter:
    """Test OpenCodeAdapter functionality."""

    def test_platform_name(self) -> None:
        """Test platform name."""
        adapter = OpenCodeAdapter()
        assert adapter.platform_name == "opencode"

    def test_config_dir(self) -> None:
        """Test config directory."""
        adapter = OpenCodeAdapter()
        assert adapter.config_dir == Path("~/.config/opencode").expanduser()

    def test_get_settings_schema(self) -> None:
        """Test settings schema generation."""
        adapter = OpenCodeAdapter()
        schema = adapter.get_settings_schema()

        assert isinstance(schema, dict)
        assert "$schema" in schema
        assert "properties" in schema
        assert "editor" in schema["properties"]
        assert "security" in schema["properties"]

    def test_render_config_basic(self, tmp_path: Path) -> None:
        """Test basic config rendering."""
        adapter = OpenCodeAdapter()
        metadata = ManifestMetadata(platform="opencode")
        manifest = Manifest(metadata=metadata)

        result = adapter.render_config(manifest, tmp_path)

        assert result.success
        assert (
            result.file_count == 9
        )  # config.yaml + llm-config.json + AGENTS.md + vibesop-env.sh + hooks/vibesop-route.sh + docs/(4 files)
        assert (tmp_path / "config.yaml").exists()
        assert (tmp_path / "llm-config.json").exists()
        assert (tmp_path / "vibesop-env.sh").exists()
        assert (tmp_path / "hooks" / "vibesop-route.sh").exists()
        assert (tmp_path / "docs" / "routing.md").exists()
        assert (tmp_path / "docs" / "session-lifecycle.md").exists()
        assert (tmp_path / "docs" / "skills-catalog.md").exists()
        assert (tmp_path / "docs" / "quick-commands.md").exists()

    def test_render_config_with_skills(self, tmp_path: Path) -> None:
        """Test rendering with skills."""
        adapter = OpenCodeAdapter()
        metadata = ManifestMetadata(platform="opencode")

        skill = SkillSpec(
            id="test-skill",
            name="Test Skill",
            description="A test skill",
            trigger_when="Testing scenario",
        )

        manifest = Manifest(
            metadata=metadata,
            skills=[skill],
        )

        result = adapter.render_config(manifest, tmp_path)

        assert result.success
        assert (
            result.file_count == 11
        )  # config.yaml + README.md + llm-config.json + AGENTS.md + vibesop-env.sh + hooks/vibesop-route.sh + skill + docs/(4 files)
        assert (tmp_path / "config.yaml").exists()
        assert (tmp_path / "README.md").exists()
        assert (tmp_path / "llm-config.json").exists()
        assert (tmp_path / "vibesop-env.sh").exists()
        assert (tmp_path / "skills" / "test-skill" / "SKILL.md").exists()

    def test_config_yaml_content(self, tmp_path: Path) -> None:
        """Test config.yaml content."""
        adapter = OpenCodeAdapter()
        metadata = ManifestMetadata(
            platform="opencode",
            version="1.0.0",
            author="Test Author",
        )
        manifest = Manifest(metadata=metadata)

        result = adapter.render_config(manifest, tmp_path)
        assert result.success

        config_yaml = (tmp_path / "config.yaml").read_text(encoding="utf-8")

        # Check for key sections
        assert "version: 1.0.0" in config_yaml
        assert "platform: opencode" in config_yaml
        assert "author: Test Author" in config_yaml

    def test_readme_content(self, tmp_path: Path) -> None:
        """Test README.md content."""
        adapter = OpenCodeAdapter()
        metadata = ManifestMetadata(platform="opencode")

        skill = SkillSpec(
            id="test-skill",
            name="Test Skill",
            description="A test skill",
            trigger_when="Testing",
        )

        manifest = Manifest(
            metadata=metadata,
            skills=[skill],
        )

        result = adapter.render_config(manifest, tmp_path)
        assert result.success

        readme = (tmp_path / "README.md").read_text(encoding="utf-8")

        assert "# OpenCode Configuration" in readme
        assert "## Skills" in readme
        assert "vibe skills list" in readme

    def test_render_config_with_custom_policies(self, tmp_path: Path) -> None:
        """Test rendering with custom policies."""
        adapter = OpenCodeAdapter()
        metadata = ManifestMetadata(platform="opencode")

        security = SecurityPolicy(
            scan_external_content=False,
            max_file_size=1024 * 1024,
        )
        routing = RoutingPolicy(
            enable_ai_routing=False,
            confidence_threshold=0.8,
        )

        manifest = Manifest(
            metadata=metadata,
            policies=PolicySet(security=security, routing=routing),
        )

        result = adapter.render_config(manifest, tmp_path)
        assert result.success

        config_yaml = (tmp_path / "config.yaml").read_text(encoding="utf-8")

        # Check policies are reflected
        assert "scan_external_content: false" in config_yaml
        assert "enable_ai_routing: false" in config_yaml

    def test_render_config_invalid_platform(self, tmp_path: Path) -> None:
        """Test rendering with wrong platform."""
        adapter = OpenCodeAdapter()
        metadata = ManifestMetadata(platform="wrong-platform")
        manifest = Manifest(metadata=metadata)

        result = adapter.render_config(manifest, tmp_path)

        assert not result.success
        assert len(result.errors) > 0

    def test_render_config_multiple_skills(self, tmp_path: Path) -> None:
        """Test rendering with multiple skills."""
        adapter = OpenCodeAdapter()
        metadata = ManifestMetadata(platform="opencode")

        skills = [
            SkillSpec(
                id="skill-1",
                name="Skill 1",
                description="First skill",
                trigger_when="Scenario 1",
            ),
            SkillSpec(
                id="skill-2",
                name="Skill 2",
                description="Second skill",
                trigger_when="Scenario 2",
            ),
        ]

        manifest = Manifest(
            metadata=metadata,
            skills=skills,
        )

        result = adapter.render_config(manifest, tmp_path)
        assert result.success

        config_yaml = (tmp_path / "config.yaml").read_text(encoding="utf-8")
        assert "- id: skill-1" in config_yaml
        assert "- id: skill-2" in config_yaml

        # Skills should be rendered to skills/ directory
        assert (tmp_path / "skills" / "skill-1" / "SKILL.md").exists()
        assert (tmp_path / "skills" / "skill-2" / "SKILL.md").exists()

    def test_render_config_only(self, tmp_path: Path) -> None:
        """Test render_config_only does not create skills directory."""
        adapter = OpenCodeAdapter()
        metadata = ManifestMetadata(platform="opencode")

        skill = SkillSpec(
            id="test-skill",
            name="Test Skill",
            description="A test skill",
            trigger_when="Testing scenario",
        )

        manifest = Manifest(
            metadata=metadata,
            skills=[skill],
        )

        result = adapter.render_config_only(manifest, tmp_path)

        assert result.success
        assert (
            result.file_count == 10
        )  # config.yaml + README.md + llm-config.json + AGENTS.md + vibesop-env.sh + hooks/vibesop-route.sh + docs/(4 files)
        assert (tmp_path / "config.yaml").exists()
        assert (tmp_path / "README.md").exists()
        assert (tmp_path / "vibesop-env.sh").exists()
        assert not (tmp_path / "skills").exists()

    def test_render_config_only_without_skills(self, tmp_path: Path) -> None:
        """Test render_config_only with no skills."""
        adapter = OpenCodeAdapter()
        metadata = ManifestMetadata(platform="opencode")
        manifest = Manifest(metadata=metadata, skills=[])

        result = adapter.render_config_only(manifest, tmp_path)

        assert result.success
        assert (
            result.file_count == 9
        )  # config.yaml + llm-config.json + AGENTS.md + vibesop-env.sh + hooks/vibesop-route.sh + docs/(4 files)
        assert (tmp_path / "vibesop-env.sh").exists()
        assert not (tmp_path / "README.md").exists()

    def test_agents_md_is_slim(self, tmp_path: Path) -> None:
        """AGENTS.md should be a slim index referencing docs/ files."""
        adapter = OpenCodeAdapter()
        metadata = ManifestMetadata(platform="opencode")

        skill = SkillSpec(
            id="test-skill",
            name="Test Skill",
            description="A test skill",
            trigger_when="Testing",
        )

        manifest = Manifest(
            metadata=metadata,
            skills=[skill],
        )

        result = adapter.render_config(manifest, tmp_path)
        assert result.success

        agents_md = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")

        # Must reference docs/ for details
        assert "docs/routing.md" in agents_md
        assert "docs/session-lifecycle.md" in agents_md
        # Must NOT inline skill listings
        assert "### test-skill" not in agents_md
        # Must reference vibe skills list instead
        assert "vibe skills list" in agents_md

    def test_docs_skills_catalog_lists_skills(self, tmp_path: Path) -> None:
        """docs/skills-catalog.md should list skills from the manifest."""
        adapter = OpenCodeAdapter()
        metadata = ManifestMetadata(platform="opencode")

        skill = SkillSpec(
            id="test-skill",
            name="Test Skill",
            description="A test skill",
            trigger_when="Testing",
        )

        manifest = Manifest(
            metadata=metadata,
            skills=[skill],
        )

        result = adapter.render_config(manifest, tmp_path)
        assert result.success

        catalog = (tmp_path / "docs" / "skills-catalog.md").read_text(encoding="utf-8")
        assert "### test-skill" in catalog
        assert "Test Skill" in catalog
        assert "A test skill" in catalog

    def test_agents_md_without_skills_no_inline(self, tmp_path: Path) -> None:
        """AGENTS.md with no skills should not list any skills inline."""
        adapter = OpenCodeAdapter()
        metadata = ManifestMetadata(platform="opencode")
        manifest = Manifest(metadata=metadata, skills=[])

        result = adapter.render_config(manifest, tmp_path)
        assert result.success

        agents_md = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
        assert (
            "### " not in agents_md.split("## Skills")[1].split("##")[0]
            if "## Skills" in agents_md
            else True
        )

    def test_install_hooks_default(self, tmp_path: Path) -> None:
        """Test default hook installation."""
        adapter = OpenCodeAdapter()

        result = adapter.install_hooks(tmp_path)

        assert result == {}

    def test_env_script_content(self, tmp_path: Path) -> None:
        """Generated vibesop-env.sh contains conversation ID setup."""
        adapter = OpenCodeAdapter()
        metadata = ManifestMetadata(platform="opencode")
        manifest = Manifest(metadata=metadata)

        result = adapter.render_config(manifest, tmp_path)
        assert result.success

        script_path = tmp_path / "vibesop-env.sh"
        assert script_path.exists()
        if sys.platform != "win32":
            # Windows chmod only toggles read-only; hooks run via `bash <script>`.
            assert script_path.stat().st_mode & 0o111  # executable

        content = script_path.read_text(encoding="utf-8")
        assert "CONVERSATION_ID" in content
        assert "python3 -c" in content
        assert "hashlib" in content
        assert "command vibe" in content
        # OpenCode doesn't support hooks


class TestOpenCodeAdapterEdgeCases:
    """Test edge cases and error conditions."""

    def test_render_with_empty_skill_list(self, tmp_path: Path) -> None:
        """Test rendering with no skills."""
        adapter = OpenCodeAdapter()
        metadata = ManifestMetadata(platform="opencode")
        manifest = Manifest(
            metadata=metadata,
            skills=[],
        )

        result = adapter.render_config(manifest, tmp_path)
        assert result.success
        assert (
            result.file_count == 9
        )  # config.yaml + llm-config.json + AGENTS.md + vibesop-env.sh + hooks/vibesop-route.sh + docs/(4 files), no README

    def test_render_with_full_metadata(self, tmp_path: Path) -> None:
        """Test rendering with full metadata."""
        adapter = OpenCodeAdapter()
        from datetime import datetime

        now = datetime.now()
        metadata = ManifestMetadata(
            platform="opencode",
            version="2.0.0",
            author="Test Author",
            description="Test manifest",
            created_at=now,
            updated_at=now,
        )
        manifest = Manifest(metadata=metadata)

        result = adapter.render_config(manifest, tmp_path)
        assert result.success

        config_yaml = (tmp_path / "config.yaml").read_text(encoding="utf-8")
        assert "version: 2.0.0" in config_yaml
        assert "author: Test Author" in config_yaml
        assert "description: Test manifest" in config_yaml

    def test_yaml_is_valid(self, tmp_path: Path) -> None:
        """Test that generated YAML is valid."""
        adapter = OpenCodeAdapter()
        metadata = ManifestMetadata(platform="opencode")
        manifest = Manifest(metadata=metadata)

        result = adapter.render_config(manifest, tmp_path)
        assert result.success

        # Try to parse the YAML
        from ruamel.yaml import YAML

        yaml = YAML()
        with (tmp_path / "config.yaml").open("r", encoding="utf-8") as f:
            config: dict[str, object] = yaml.load(f)  # type: ignore[assignment]

        assert isinstance(config, dict)
        assert "version" in config
        assert "platform" in config

    def test_concurrent_render(self, tmp_path: Path) -> None:
        """Test that multiple renders don't interfere."""
        adapter = OpenCodeAdapter()
        metadata = ManifestMetadata(platform="opencode")
        manifest = Manifest(metadata=metadata)

        result1 = adapter.render_config(manifest, tmp_path / "config1")
        result2 = adapter.render_config(manifest, tmp_path / "config2")

        assert result1.success
        assert result2.success

        assert (tmp_path / "config1" / "config.yaml").exists()
        assert (tmp_path / "config2" / "config.yaml").exists()

    def test_readme_without_skills(self, tmp_path: Path) -> None:
        """Test that README is not created when no skills."""
        adapter = OpenCodeAdapter()
        metadata = ManifestMetadata(platform="opencode")
        manifest = Manifest(
            metadata=metadata,
            skills=[],
        )

        result = adapter.render_config(manifest, tmp_path)
        assert result.success

        # Should not create README when no skills
        assert not (tmp_path / "README.md").exists()


class TestOpenCodeSkillContentRender:
    """Tests for _render_skill_content symlink preservation in OpenCode adapter."""

    def test_symlink_preserved_on_second_build(self, monkeypatch, tmp_path, symlink_supported):
        """Symlink to installed pack must be preserved on re-build."""
        if not symlink_supported:
            pytest.skip("directory symlinks not supported on this host")
        from vibesop.adapters.opencode import OpenCodeAdapter

        adapter = OpenCodeAdapter()
        output_dir = tmp_path / "output"
        skill_dir = output_dir / "skills" / "gstack-review"
        skill_dir.mkdir(parents=True)

        installed_dir = tmp_path / "installed"
        installed_dir.mkdir(parents=True)
        (installed_dir / "SKILL.md").write_text(
            "# Full Review Skill\n\nExecute review flow.", encoding="utf-8"
        )

        monkeypatch.setattr(
            "vibesop.adapters._shared.is_pack_installed",
            lambda _: installed_dir,
        )

        class _Skill:
            id = "gstack/review"
            namespace = "gstack"
            name = "GStack Review"
            description = "Code review"
            version = "1.0"
            skill_type = "standard"
            tags: ClassVar[list[str]] = ["review"]
            trigger_when = "When asked to review code"

        result = type("Result", (), {"add_file": lambda *a: None, "add_error": lambda *a: None})()

        adapter._render_skill_content(_Skill(), skill_dir, result, dir_name="gstack-review")
        assert skill_dir.is_symlink()
        assert skill_dir.resolve() == installed_dir.resolve()

        adapter._render_skill_content(_Skill(), skill_dir, result, dir_name="gstack-review")
        assert skill_dir.is_symlink(), "Symlink was lost on second build"
        content = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        assert "Full Review Skill" in content
