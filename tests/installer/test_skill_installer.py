"""Tests for SkillInstaller."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from vibesop.installer.skill_installer import SkillInstaller, SkillManifest


class TestSkillManifest:
    """Tests for SkillManifest."""

    def test_manifest_from_file(self, tmp_path: Path) -> None:
        """Test loading manifest from a valid SKILL.md."""
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text(
            "---\n"
            "id: test-skill\n"
            'name: "Test Skill"\n'
            'description: "A test skill"\n'
            "version: 2.0.0\n"
            'author: "Tester"\n'
            'trigger_when: "test"\n'
            "---\n"
            "# Content\n"
        )
        manifest = SkillManifest.from_file(skill_md)
        assert manifest.id == "test-skill"
        assert manifest.name == "Test Skill"
        assert manifest.description == "A test skill"
        assert manifest.version == "2.0.0"
        assert manifest.author == "Tester"
        assert manifest.trigger_when == "test"

    def test_manifest_from_file_missing(self, tmp_path: Path) -> None:
        """Test loading manifest when file is missing returns defaults."""
        missing = tmp_path / "SKILL.md"
        manifest = SkillManifest.from_file(missing)
        assert manifest.id == tmp_path.name
        assert manifest.name == tmp_path.name.replace("-", " ").title()
        assert manifest.description == ""
        assert manifest.version == "1.0.0"
        assert manifest.author == "Unknown"


class TestSkillInstaller:
    """Tests for SkillInstaller."""

    def test_install_skill_success(self, tmp_path: Path) -> None:
        """Test successful skill installation."""
        installer = SkillInstaller()
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nid: my-skill\nname: My Skill\n---\n"
        )
        project_path = tmp_path / "project"
        project_path.mkdir()

        result = installer.install_skill(skill_dir, project_path)

        assert result["success"] is True
        assert result["skill_id"] == "my-skill"
        installed = project_path / ".vibe" / "skills" / "my-skill"
        assert installed.exists()
        assert (installed / "SKILL.md").exists()
        # Registry updated
        registry = project_path / ".vibe" / "skills" / "registry.yaml"
        assert registry.exists()
        assert "my-skill" in registry.read_text()

    def test_install_skill_already_exists_no_force(self, tmp_path: Path) -> None:
        """Test installing when already exists without force."""
        installer = SkillInstaller()
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nid: my-skill\n---\n")
        project_path = tmp_path / "project"
        project_path.mkdir()
        target = project_path / ".vibe" / "skills" / "my-skill"
        target.mkdir(parents=True)

        result = installer.install_skill(skill_dir, project_path, force=False)

        assert result["success"] is True
        assert "already installed" in result["warnings"][0]

    def test_install_skill_force_reinstall(self, tmp_path: Path) -> None:
        """Test force reinstall."""
        installer = SkillInstaller()
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nid: my-skill\n---\n")
        project_path = tmp_path / "project"
        project_path.mkdir()

        installer.install_skill(skill_dir, project_path)
        result = installer.install_skill(skill_dir, project_path, force=True)

        assert result["success"] is True
        assert "already installed" not in str(result.get("warnings", []))

    def test_install_skill_path_not_found(self, tmp_path: Path) -> None:
        """Test installing from non-existent path."""
        installer = SkillInstaller()
        result = installer.install_skill(tmp_path / "missing", tmp_path)
        assert result["success"] is False
        assert "not found" in result["errors"][0]

    def test_install_skill_with_dependencies_met(self, tmp_path: Path) -> None:
        """Test installing skill whose dependencies are already met."""
        installer = SkillInstaller()
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nid: my-skill\nname: My Skill\n---\n"
        )
        # Create dependency skill
        dep_dir = tmp_path / "dep-skill"
        dep_dir.mkdir()
        (dep_dir / "SKILL.md").write_text("---\nid: dep-skill\n---\n")
        project_path = tmp_path / "project"
        project_path.mkdir()
        installer.install_skill(dep_dir, project_path)

        # Monkeypatch manifest loader to include dependency
        original_load = installer._load_skill_manifest

        def _patched_load(path: Path) -> SkillManifest:
            manifest = original_load(path)
            if manifest.id == "my-skill":
                manifest.dependencies = ["dep-skill"]
            return manifest

        installer._load_skill_manifest = _patched_load  # type: ignore[method-assign]
        result = installer.install_skill(skill_dir, project_path)

        assert result["success"] is True
        assert "dep-skill" in result["dependencies_installed"]

    def test_install_skill_with_dependencies_missing(self, tmp_path: Path) -> None:
        """Test installing skill with missing dependencies."""
        installer = SkillInstaller()
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nid: my-skill\nname: My Skill\n---\n"
        )
        project_path = tmp_path / "project"
        project_path.mkdir()

        original_load = installer._load_skill_manifest

        def _patched_load(path: Path) -> SkillManifest:
            manifest = original_load(path)
            if manifest.id == "my-skill":
                manifest.dependencies = ["missing-dep"]
            return manifest

        installer._load_skill_manifest = _patched_load  # type: ignore[method-assign]
        result = installer.install_skill(skill_dir, project_path)

        assert result["success"] is False
        assert "missing-dep" in result["errors"][0]

    def test_uninstall_skill(self, tmp_path: Path) -> None:
        """Test uninstalling a skill."""
        installer = SkillInstaller()
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nid: my-skill\n---\n")
        project_path = tmp_path / "project"
        project_path.mkdir()
        installer.install_skill(skill_dir, project_path)

        result = installer.uninstall_skill("my-skill", project_path)

        assert result["success"] is True
        assert not (project_path / ".vibe" / "skills" / "my-skill").exists()
        registry = project_path / ".vibe" / "skills" / "registry.yaml"
        assert "my-skill" not in registry.read_text()

    def test_uninstall_skill_not_found(self, tmp_path: Path) -> None:
        """Test uninstalling a non-existent skill."""
        installer = SkillInstaller()
        result = installer.uninstall_skill("missing", tmp_path)
        assert result["success"] is False
        assert "not found" in result["errors"][0]

    def test_list_skills(self, tmp_path: Path) -> None:
        """Test listing installed skills."""
        installer = SkillInstaller()
        skill_dir = tmp_path / "listed-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nid: listed-skill\nname: Listed Skill\n---\n"
        )
        project_path = tmp_path / "project"
        project_path.mkdir()
        installer.install_skill(skill_dir, project_path)

        skills = installer.list_skills(project_path)

        assert len(skills) == 1
        assert skills[0]["id"] == "listed-skill"
        assert skills[0]["name"] == "Listed Skill"

    def test_list_skills_empty(self, tmp_path: Path) -> None:
        """Test listing when no skills directory exists."""
        installer = SkillInstaller()
        skills = installer.list_skills(tmp_path)
        assert skills == []

    def test_verify_skill_installed(self, tmp_path: Path) -> None:
        """Test verifying an installed skill."""
        installer = SkillInstaller()
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nid: my-skill\n---\n")
        project_path = tmp_path / "project"
        project_path.mkdir()
        installer.install_skill(skill_dir, project_path)

        result = installer.verify_skill("my-skill", project_path)

        assert result["installed"] is True
        assert result["files_present"] is True
        assert result["in_registry"] is True
        assert result["dependencies_met"] is True

    def test_verify_skill_not_found(self, tmp_path: Path) -> None:
        """Test verifying a missing skill."""
        installer = SkillInstaller()
        result = installer.verify_skill("missing", tmp_path)
        assert result["installed"] is False
        assert "not found" in result["errors"][0]

    def test_copy_skill_files_with_subdirs(self, tmp_path: Path) -> None:
        """Test copying skill files that include subdirectories."""
        installer = SkillInstaller()
        src = tmp_path / "skill-with-subdir"
        src.mkdir()
        (src / "SKILL.md").write_text("---\nid: s\n---\n")
        sub = src / "templates"
        sub.mkdir()
        (sub / "template.txt").write_text("hello")

        dst = tmp_path / "dst"
        installer._copy_skill_files(src, dst)

        assert (dst / "SKILL.md").exists()
        assert (dst / "templates" / "template.txt").exists()
