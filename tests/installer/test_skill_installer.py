"""Tests for SkillInstaller."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from vibesop.installer.skill_installer import SkillInstaller, SkillManifest

if TYPE_CHECKING:
    from pathlib import Path


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
            "# Content\n",
            encoding="utf-8",
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
            "---\nid: my-skill\nname: My Skill\n---\n", encoding="utf-8"
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
        assert "my-skill" in registry.read_text(encoding="utf-8")

    def test_install_skill_already_exists_no_force(self, tmp_path: Path) -> None:
        """Test installing when already exists without force."""
        installer = SkillInstaller()
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nid: my-skill\n---\n", encoding="utf-8")
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
        (skill_dir / "SKILL.md").write_text("---\nid: my-skill\n---\n", encoding="utf-8")
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
            "---\nid: my-skill\nname: My Skill\n---\n", encoding="utf-8"
        )
        # Create dependency skill
        dep_dir = tmp_path / "dep-skill"
        dep_dir.mkdir()
        (dep_dir / "SKILL.md").write_text("---\nid: dep-skill\n---\n", encoding="utf-8")
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
            "---\nid: my-skill\nname: My Skill\n---\n", encoding="utf-8"
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
        (skill_dir / "SKILL.md").write_text("---\nid: my-skill\n---\n", encoding="utf-8")
        project_path = tmp_path / "project"
        project_path.mkdir()
        installer.install_skill(skill_dir, project_path)

        result = installer.uninstall_skill("my-skill", project_path)

        assert result["success"] is True
        assert not (project_path / ".vibe" / "skills" / "my-skill").exists()
        registry = project_path / ".vibe" / "skills" / "registry.yaml"
        assert "my-skill" not in registry.read_text(encoding="utf-8")

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
            "---\nid: listed-skill\nname: Listed Skill\n---\n", encoding="utf-8"
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
        (skill_dir / "SKILL.md").write_text("---\nid: my-skill\n---\n", encoding="utf-8")
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
        (src / "SKILL.md").write_text("---\nid: s\n---\n", encoding="utf-8")
        sub = src / "templates"
        sub.mkdir()
        (sub / "template.txt").write_text("hello", encoding="utf-8")

        dst = tmp_path / "dst"
        installer._copy_skill_files(src, dst)

        assert (dst / "SKILL.md").exists()
        assert (dst / "templates" / "template.txt").exists()


class TestSkillInstallerIdValidation:
    """D01 counterexamples (B1): a malicious skill id must never let
    ``install_skill`` / ``uninstall_skill`` / ``verify_skill`` touch files
    outside ``<project>/.vibe/skills``.

    Legal pack-style namespace ids (``demo-scope/demo``) must keep working —
    the validation is per logical segment, not a blanket ``validate_filename``
    on the whole id.
    """

    @staticmethod
    def _make_skill(tmp_path: Path, dir_name: str, skill_id: str) -> Path:
        skill_dir = tmp_path / dir_name
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            f"---\nid: {skill_id}\nname: Evil Skill\n---\n# Evil\n",
            encoding="utf-8",
        )
        return skill_dir

    def test_install_rejects_traversal_manifest_id(self, tmp_path: Path) -> None:
        installer = SkillInstaller()
        skill_dir = self._make_skill(tmp_path, "evil-skill", "../../../outside")
        project_path = tmp_path / "project"
        project_path.mkdir()

        result = installer.install_skill(skill_dir, project_path)

        assert result["success"] is False
        # project/.vibe/skills/../../../outside resolves to <tmp>/outside —
        # the install root must not be escaped.
        assert not (tmp_path / "outside").exists()

    @pytest.mark.parametrize("id_kind", ["absolute", "empty-segment", "backslash"])
    def test_install_rejects_malformed_ids(self, tmp_path: Path, id_kind: str) -> None:
        if id_kind == "absolute":
            skill_id = str(tmp_path / "evil-abs")
            escaped = tmp_path / "evil-abs"
        elif id_kind == "empty-segment":
            skill_id = "demo-scope//demo"
            escaped = tmp_path / "project" / ".vibe" / "skills" / "demo-scope" / "demo"
        else:
            skill_id = "evil\\segment"
            escaped = tmp_path / "project" / ".vibe" / "skills" / "evil\\segment"

        installer = SkillInstaller()
        skill_dir = self._make_skill(tmp_path, f"src-{id_kind}", skill_id)
        project_path = tmp_path / "project"
        project_path.mkdir()

        result = installer.install_skill(skill_dir, project_path)

        assert result["success"] is False
        assert not escaped.exists()

    def test_install_rejects_symlinked_namespace_segment(
        self, tmp_path: Path, symlink_supported: bool
    ) -> None:
        if not symlink_supported:
            pytest.skip("directory symlinks not supported on this host")

        installer = SkillInstaller()
        skill_dir = self._make_skill(tmp_path, "link-escape-src", "link-escape/demo")
        project_path = tmp_path / "project"
        skills_dir = project_path / ".vibe" / "skills"
        skills_dir.mkdir(parents=True)

        outside = tmp_path / "outside"
        outside.mkdir()
        (skills_dir / "link-escape").symlink_to(outside, target_is_directory=True)

        result = installer.install_skill(skill_dir, project_path)

        assert result["success"] is False
        # The intermediate symlink must not let the copy land outside the project.
        assert not (outside / "demo").exists()

    def test_uninstall_and_verify_reject_traversal_id(self, tmp_path: Path) -> None:
        installer = SkillInstaller()
        project_path = tmp_path / "project"
        # The lexical chain must exist or the kernel refuses to resolve ".."
        # and the escape never becomes reachable.
        skills_root = project_path / ".vibe" / "skills"
        skills_root.mkdir(parents=True)
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "keep.txt").write_text("keep", encoding="utf-8")

        # project/.vibe/skills/../../../outside resolves to <tmp>/outside.
        uninstall = installer.uninstall_skill("../../../outside", project_path)
        verify = installer.verify_skill("../../../outside", project_path)

        assert uninstall["success"] is False
        assert (outside / "keep.txt").exists(), "uninstall must not remove outside the skills root"
        assert verify["installed"] is False

    def test_install_namespaced_id_still_works(self, tmp_path: Path) -> None:
        """Legal pack/skill namespace ids (demo-scope/demo) stay compatible."""
        installer = SkillInstaller()
        skill_dir = tmp_path / "demo"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nid: demo-scope/demo\nname: Demo\n---\n", encoding="utf-8"
        )
        project_path = tmp_path / "project"
        project_path.mkdir()

        result = installer.install_skill(skill_dir, project_path)

        assert result["success"] is True
        installed = project_path / ".vibe" / "skills" / "demo-scope" / "demo"
        assert (installed / "SKILL.md").exists()


class TestSkillInstallerProjectRootNormalization:
    """R3 counterexamples (B1 Codex review): a legal RELATIVE project root
    must install, verify, and uninstall at exactly one location — the old
    code double-joined (``project/project/.vibe/skills/...``) and split the
    install dir from the registry.
    """

    def test_relative_project_path_install_verify_uninstall_roundtrip(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from pathlib import Path

        monkeypatch.chdir(tmp_path)
        installer = SkillInstaller()
        src = tmp_path / "src-demo"
        src.mkdir()
        (src / "SKILL.md").write_text(
            "---\nid: demo\nname: Demo\ndescription: Dummy\n---\n# dummy\n", encoding="utf-8"
        )
        relative_project = Path("project")
        relative_project.mkdir()

        result = installer.install_skill(src, relative_project)

        assert result["success"] is True, result["errors"]
        installed = tmp_path / "project" / ".vibe" / "skills" / "demo"
        assert (installed / "SKILL.md").exists(), "single join: skill lands in project/.vibe/skills"
        assert result["installed_path"] == str(installed)
        assert not (tmp_path / "project" / "project").exists(), "no double-joined project/project"
        assert (tmp_path / "project" / ".vibe" / "skills" / "registry.yaml").exists(), (
            "registry must live beside the installed skill"
        )

        # Verify agrees whether the caller passes the relative or the
        # absolute project root.
        assert installer.verify_skill("demo", relative_project)["installed"] is True
        assert installer.verify_skill("demo", tmp_path / "project")["installed"] is True

        removed = installer.uninstall_skill("demo", relative_project)
        assert removed["success"] is True, removed["errors"]
        assert not installed.exists()
        assert "demo" not in (
            tmp_path / "project" / ".vibe" / "skills" / "registry.yaml"
        ).read_text(encoding="utf-8")


class TestSkillInstallerEarlyIdRejection:
    """R3 early-reject ordering (B1 Codex review): the logical id must be
    validated BEFORE any dependency handling, and validation must not
    create directories.
    """

    def _recording_installer(self) -> tuple[SkillInstaller, list[str]]:
        events: list[str] = []

        class RecordingInstaller(SkillInstaller):
            def _validate_skill_id(self, skill_id: str) -> None:
                events.append(f"validate:{skill_id}")
                super()._validate_skill_id(skill_id)

            def _install_dependencies(self, dependencies, project_path):  # type: ignore[no-untyped-def]
                events.append(f"dependencies:{dependencies!r}")
                return super()._install_dependencies(dependencies, project_path)

        return RecordingInstaller(), events

    def test_invalid_id_rejected_before_dependencies_without_creating_dirs(
        self, tmp_path: Path
    ) -> None:
        installer, events = self._recording_installer()
        bad_src = tmp_path / "bad-src"
        bad_src.mkdir()
        (bad_src / "SKILL.md").write_text(
            "---\nid: ../../outside\nname: bad\ndescription: Dummy\n---\n# dummy\n",
            encoding="utf-8",
        )
        project_path = tmp_path / "project"

        result = installer.install_skill(bad_src, project_path)

        assert result["success"] is False
        assert events == ["validate:../../outside"], (
            f"id validation must run (and fail) before dependency handling: {events}"
        )
        assert not (project_path / ".vibe").exists(), "rejection must not create directories"
        assert not (tmp_path / "outside").exists()

    def test_valid_id_still_installs_dependencies_after_validation(self, tmp_path: Path) -> None:
        installer, events = self._recording_installer()
        src = tmp_path / "src-demo"
        src.mkdir()
        (src / "SKILL.md").write_text(
            "---\nid: demo\nname: Demo\ndescription: Dummy\n---\n# dummy\n", encoding="utf-8"
        )
        project_path = tmp_path / "project"
        project_path.mkdir()

        result = installer.install_skill(src, project_path)

        assert result["success"] is True, result["errors"]
        # The id is validated early (before dependencies) and again when the
        # target dir is computed — ordering is what matters here.
        assert events[0] == "validate:demo", events
        assert "dependencies:[]" in events, events


class TestSkillInstallerWindowsSpecialCharSegments:
    """Each id segment goes through the project's existing cross-platform
    filename validation: Windows-illegal special characters are rejected
    per segment while the pack/skill namespace shape stays legal.
    """

    @pytest.mark.parametrize(
        "bad_segment", ["bad|seg", "bad?seg", "bad*seg", "bad<seg>", "bad;seg"]
    )
    def test_install_rejects_windows_special_char_segment(
        self, tmp_path: Path, bad_segment: str
    ) -> None:
        installer = SkillInstaller()
        skill_dir = tmp_path / "evil"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            f"---\nid: {bad_segment}\nname: Evil\n---\n# Evil\n", encoding="utf-8"
        )
        project_path = tmp_path / "project"
        project_path.mkdir()

        result = installer.install_skill(skill_dir, project_path)

        assert result["success"] is False
        assert not (project_path / ".vibe").exists(), "rejection must not create directories"

    def test_verify_rejects_windows_special_char_segment(self, tmp_path: Path) -> None:
        installer = SkillInstaller()
        result = installer.verify_skill("bad|seg", tmp_path)
        assert result["installed"] is False
        assert result["errors"], "verify must report the invalid id"
