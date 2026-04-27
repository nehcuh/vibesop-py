"""Tests for KimiCliAdapter."""

from pathlib import Path

from vibesop.adapters.kimi_cli import KimiCliAdapter
from vibesop.adapters.models import (
    Manifest,
    ManifestMetadata,
    PolicySet,
    RoutingPolicy,
    SecurityPolicy,
)
from vibesop.core.models import SkillDefinition


class TestKimiCliAdapter:
    """Test KimiCliAdapter functionality."""

    def test_platform_name(self) -> None:
        """Test platform name."""
        adapter = KimiCliAdapter()
        assert adapter.platform_name == "kimi-cli"

    def test_config_dir(self) -> None:
        """Test config directory."""
        adapter = KimiCliAdapter()
        assert adapter.config_dir == Path("~/.kimi").expanduser()

    def test_get_settings_schema(self) -> None:
        """Test settings schema generation."""
        adapter = KimiCliAdapter()
        schema = adapter.get_settings_schema()

        assert isinstance(schema, dict)
        assert "$schema" in schema
        assert "properties" in schema
        assert "default_model" in schema["properties"]
        assert "loop_control" in schema["properties"]

    def test_render_config_basic(self, tmp_path: Path) -> None:
        """Test basic config rendering."""
        adapter = KimiCliAdapter()
        metadata = ManifestMetadata(platform="kimi-cli")
        manifest = Manifest(metadata=metadata)

        result = adapter.render_config(manifest, tmp_path)

        assert result.success
        assert result.file_count == 3  # config.toml + AGENTS.md + hook
        assert (tmp_path / "config.toml").exists()
        assert (tmp_path / "AGENTS.md").exists()
        assert (tmp_path / "hooks" / "vibesop-route.sh").exists()

    def test_render_config_with_skills(self, tmp_path: Path) -> None:
        """Test rendering with skills."""
        adapter = KimiCliAdapter()
        metadata = ManifestMetadata(platform="kimi-cli")

        skill = SkillDefinition(
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
        assert result.file_count == 5  # config.toml + README.md + skill + AGENTS.md + hook
        assert (tmp_path / "config.toml").exists()
        assert (tmp_path / "README.md").exists()
        assert (tmp_path / "AGENTS.md").exists()
        assert (tmp_path / "skills" / "test-skill" / "SKILL.md").exists()
        assert (tmp_path / "hooks" / "vibesop-route.sh").exists()

    def test_config_toml_content(self, tmp_path: Path) -> None:
        """Test config.toml content."""
        adapter = KimiCliAdapter()
        metadata = ManifestMetadata(
            platform="kimi-cli",
            version="1.0.0",
            author="Test Author",
        )
        manifest = Manifest(metadata=metadata)

        result = adapter.render_config(manifest, tmp_path)
        assert result.success

        config_toml = (tmp_path / "config.toml").read_text()

        # Check for key sections
        assert "# VibeSOP Configuration for Kimi Code CLI" in config_toml
        assert "# Version: 1.0.0" in config_toml
        assert "# Platform: kimi-cli" in config_toml
        assert "# Author: Test Author" in config_toml
        assert "[vibesop.security]" in config_toml
        assert "[vibesop.routing]" in config_toml
        assert "merge_all_available_skills = true" not in config_toml
        assert "[models.kimi-for-coding]" not in config_toml

    def test_readme_content(self, tmp_path: Path) -> None:
        """Test README.md content."""
        adapter = KimiCliAdapter()
        metadata = ManifestMetadata(platform="kimi-cli")

        skill = SkillDefinition(
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

        readme = (tmp_path / "README.md").read_text()

        assert "# Kimi Code CLI Configuration" in readme
        assert "## Skills" in readme
        assert "test-skill" in readme
        assert "Test Skill" in readme
        # Should include correct 10-layer routing description
        assert "10-Layer Routing System" in readme
        assert "Layer 0**: Explicit override" in readme
        assert "Layer 2**: AI Semantic Triage" in readme
        # Should mention Kimi Code CLI skill directories
        assert "~/.kimi/skills/" in readme

    def test_render_config_with_custom_policies(self, tmp_path: Path) -> None:
        """Test rendering with custom policies."""
        adapter = KimiCliAdapter()
        metadata = ManifestMetadata(platform="kimi-cli")

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

        config_toml = (tmp_path / "config.toml").read_text()

        # Check policies are reflected
        assert "scan_external_content = false" in config_toml
        assert "enable_ai_routing = false" in config_toml
        assert "confidence_threshold = 0.8" in config_toml

    def test_render_config_invalid_platform(self, tmp_path: Path) -> None:
        """Test rendering with wrong platform."""
        adapter = KimiCliAdapter()
        metadata = ManifestMetadata(platform="wrong-platform")
        manifest = Manifest(metadata=metadata)

        result = adapter.render_config(manifest, tmp_path)

        assert not result.success
        assert len(result.errors) > 0

    def test_render_config_multiple_skills(self, tmp_path: Path) -> None:
        """Test rendering with multiple skills."""
        adapter = KimiCliAdapter()
        metadata = ManifestMetadata(platform="kimi-cli")

        skills = [
            SkillDefinition(
                id="skill-1",
                name="Skill 1",
                description="First skill",
                trigger_when="Scenario 1",
            ),
            SkillDefinition(
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

        config_toml = (tmp_path / "config.toml").read_text()
        # Skills are no longer listed in config.toml (they are auto-discovered from directory)
        assert "VibeSOP Skills" in config_toml
        assert "2 skills configured" in config_toml

        # Skills should be rendered to skills/ directory
        assert (tmp_path / "skills" / "skill-1" / "SKILL.md").exists()
        assert (tmp_path / "skills" / "skill-2" / "SKILL.md").exists()

    def test_render_config_only(self, tmp_path: Path) -> None:
        """Test render_config_only does not create skills directory."""
        adapter = KimiCliAdapter()
        metadata = ManifestMetadata(platform="kimi-cli")

        skill = SkillDefinition(
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
        assert result.file_count == 3  # config.toml + README.md + hook
        assert (tmp_path / "config.toml").exists()
        assert (tmp_path / "README.md").exists()
        assert (tmp_path / "hooks" / "vibesop-route.sh").exists()
        assert not (tmp_path / "skills").exists()

    def test_render_config_only_without_skills(self, tmp_path: Path) -> None:
        """Test render_config_only with no skills."""
        adapter = KimiCliAdapter()
        metadata = ManifestMetadata(platform="kimi-cli")
        manifest = Manifest(metadata=metadata, skills=[])

        result = adapter.render_config_only(manifest, tmp_path)

        assert result.success
        assert result.file_count == 2  # config.toml + hook
        assert not (tmp_path / "README.md").exists()
        assert (tmp_path / "hooks" / "vibesop-route.sh").exists()

    def test_install_hooks_default(self, tmp_path: Path) -> None:
        """Test default hook installation."""
        adapter = KimiCliAdapter()

        result = adapter.install_hooks(tmp_path)

        assert result == {}

    def test_hook_script_content(self, tmp_path: Path) -> None:
        """Generated hook script contains critical cross-platform logic."""
        adapter = KimiCliAdapter()
        metadata = ManifestMetadata(platform="kimi-cli")
        manifest = Manifest(metadata=metadata)

        result = adapter.render_config(manifest, tmp_path)
        assert result.success

        hook_path = tmp_path / "hooks" / "vibesop-route.sh"
        assert hook_path.exists()
        assert hook_path.stat().st_mode & 0o111  # executable

        content = hook_path.read_text()
        assert "shasum -a 256" in content, "macOS hash fallback missing"
        assert "python3 -c" in content, "Python hash fallback missing"
        assert "^/vibe-" in content, "Slash command detection missing"
        assert "vibe route" in content, "vibe route call missing"

    def test_config_toml_has_hooks_section(self, tmp_path: Path) -> None:
        """config.toml includes [[hooks]] configuration for auto-routing."""
        adapter = KimiCliAdapter()
        metadata = ManifestMetadata(platform="kimi-cli")
        manifest = Manifest(metadata=metadata)

        result = adapter.render_config(manifest, tmp_path)
        assert result.success

        config_toml = (tmp_path / "config.toml").read_text()
        assert "[[hooks]]" in config_toml
        assert 'name = "vibesop-route"' in config_toml
        assert 'event = "UserPromptSubmit"' in config_toml
        assert 'command = "bash ~/.kimi/hooks/vibesop-route.sh"' in config_toml
        # Kimi Code CLI doesn't use file-based hooks

    def test_toml_is_valid(self, tmp_path: Path) -> None:
        """Test that generated TOML is valid."""
        adapter = KimiCliAdapter()
        metadata = ManifestMetadata(platform="kimi-cli")
        manifest = Manifest(metadata=metadata)

        result = adapter.render_config(manifest, tmp_path)
        assert result.success

        # Try to parse the TOML
        import tomllib

        with (tmp_path / "config.toml").open("rb") as f:
            config: dict[str, object] = tomllib.load(f)

        assert isinstance(config, dict)
        # VibeSOP only generates a config fragment, not a full config
        assert "vibesop" in config
        assert "loop_control" not in config
        assert "background" not in config


class TestKimiCliAdapterEdgeCases:
    """Test edge cases and error conditions."""

    def test_render_with_empty_skill_list(self, tmp_path: Path) -> None:
        """Test rendering with no skills."""
        adapter = KimiCliAdapter()
        metadata = ManifestMetadata(platform="kimi-cli")
        manifest = Manifest(
            metadata=metadata,
            skills=[],
        )

        result = adapter.render_config(manifest, tmp_path)
        assert result.success
        assert result.file_count == 3  # config.toml + AGENTS.md + hook, no README

    def test_render_with_full_metadata(self, tmp_path: Path) -> None:
        """Test rendering with full metadata."""
        adapter = KimiCliAdapter()
        from datetime import datetime

        now = datetime.now()
        metadata = ManifestMetadata(
            platform="kimi-cli",
            version="2.0.0",
            author="Test Author",
            description="Test manifest",
            created_at=now,
            updated_at=now,
        )
        manifest = Manifest(metadata=metadata)

        result = adapter.render_config(manifest, tmp_path)
        assert result.success

        config_toml = (tmp_path / "config.toml").read_text()
        assert "# Version: 2.0.0" in config_toml
        assert "# Author: Test Author" in config_toml
        assert "# Description: Test manifest" in config_toml

    def test_concurrent_render(self, tmp_path: Path) -> None:
        """Test that multiple renders don't interfere."""
        adapter = KimiCliAdapter()
        metadata = ManifestMetadata(platform="kimi-cli")
        manifest = Manifest(metadata=metadata)

        result1 = adapter.render_config(manifest, tmp_path / "config1")
        result2 = adapter.render_config(manifest, tmp_path / "config2")

        assert result1.success
        assert result2.success

        assert (tmp_path / "config1" / "config.toml").exists()
        assert (tmp_path / "config2" / "config.toml").exists()

    def test_readme_without_skills(self, tmp_path: Path) -> None:
        """Test that README is not created when no skills."""
        adapter = KimiCliAdapter()
        metadata = ManifestMetadata(platform="kimi-cli")
        manifest = Manifest(
            metadata=metadata,
            skills=[],
        )

        result = adapter.render_config(manifest, tmp_path)
        assert result.success

        # Should not create README when no skills
        assert not (tmp_path / "README.md").exists()
