"""Tests for PackInstaller."""

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from vibesop.installer.pack_installer import PackInstaller


class TestPackInstaller:
    """Test PackInstaller functionality."""

    def test_install_unknown_pack(self) -> None:
        """Installing an unknown pack without URL should fail."""
        with tempfile.TemporaryDirectory() as tmpdir:
            installer = PackInstaller(external_paths=[Path(tmpdir)])
            success, msg = installer.install_pack("unknown-pack")
            assert success is False
            assert "Unknown pack" in msg

    def test_install_pack_with_url(self) -> None:
        """Installing a pack from a direct URL should succeed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            installer = PackInstaller(external_paths=[Path(tmpdir)])

            with patch("vibesop.installer.pack_installer.RepoAnalyzer") as mock_cls:
                mock_analyzer = MagicMock()
                mock_analyzer.analyze.return_value = MagicMock(
                    errors=[],
                    skill_files=[Path("skills/test/SKILL.md")],
                )
                mock_analyzer.git_clone.return_value = True
                mock_cls.return_value = mock_analyzer

                with patch("vibesop.installer.pack_installer.InstallPlanner") as planner_cls:
                    mock_plan = MagicMock()
                    mock_plan.target_path = Path(tmpdir) / "test-pack"
                    planner_cls.return_value.plan.return_value = mock_plan

                    success, msg = installer.install_pack(
                        "test-pack", "https://example.com/test-pack"
                    )

            assert success is True
            assert "Installed test-pack" in msg
            mock_analyzer.git_clone.assert_called_once()

    def test_install_pack_analysis_errors(self) -> None:
        """Installation should fail when repository analysis returns errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            installer = PackInstaller(external_paths=[Path(tmpdir)])

            with patch("vibesop.installer.pack_installer.RepoAnalyzer") as mock_cls:
                mock_analyzer = MagicMock()
                mock_analyzer.analyze.return_value = MagicMock(
                    errors=["Network unreachable"],
                    skill_files=[],
                )
                mock_cls.return_value = mock_analyzer

                success, msg = installer.install_pack(
                    "test-pack", "https://example.com/test-pack"
                )

            assert success is False
            assert "Network unreachable" in msg

    def test_install_pack_no_skills_found(self) -> None:
        """Installation should fail when no SKILL.md files are found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            installer = PackInstaller(external_paths=[Path(tmpdir)])

            with patch("vibesop.installer.pack_installer.RepoAnalyzer") as mock_cls:
                mock_analyzer = MagicMock()
                mock_analyzer.analyze.return_value = MagicMock(
                    errors=[],
                    skill_files=[],
                )
                mock_cls.return_value = mock_analyzer

                success, msg = installer.install_pack(
                    "test-pack", "https://example.com/test-pack"
                )

            assert success is False
            assert "No SKILL.md files found" in msg

    def test_install_pack_clone_failure(self) -> None:
        """Installation should fail when git clone fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            installer = PackInstaller(external_paths=[Path(tmpdir)])

            with patch("vibesop.installer.pack_installer.RepoAnalyzer") as mock_cls:
                mock_analyzer = MagicMock()
                mock_analyzer.analyze.return_value = MagicMock(
                    errors=[],
                    skill_files=[Path("skills/test/SKILL.md")],
                )
                mock_analyzer.git_clone.return_value = False
                mock_cls.return_value = mock_analyzer

                with patch("vibesop.installer.pack_installer.InstallPlanner") as planner_cls:
                    mock_plan = MagicMock()
                    mock_plan.target_path = Path(tmpdir) / "test-pack"
                    planner_cls.return_value.plan.return_value = mock_plan

                    success, msg = installer.install_pack(
                        "test-pack", "https://example.com/test-pack"
                    )

            assert success is False
            assert "Failed to clone" in msg

    @patch("vibesop.installer.pack_installer.SkillSecurityAuditor")
    def test_install_pack_security_audit(self, mock_auditor_cls: Any) -> None:
        """Installed skills should be security audited."""
        mock_audit = MagicMock()
        mock_audit.is_safe = True
        mock_auditor = MagicMock()
        mock_auditor.audit_skill_file.return_value = mock_audit
        mock_auditor_cls.return_value = mock_auditor

        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir) / "test-pack"

            installer = PackInstaller(external_paths=[Path(tmpdir)])

            def _mock_clone(url: str, dest: Path) -> bool:
                """Simulate git clone by creating the skill file."""
                dest.mkdir(parents=True, exist_ok=True)
                (dest / "SKILL.md").write_text("# Test Skill\n")
                return True

            with patch("vibesop.installer.pack_installer.RepoAnalyzer") as mock_cls:
                mock_analyzer = MagicMock()
                mock_analyzer.analyze.return_value = MagicMock(
                    errors=[],
                    skill_files=[target_path / "SKILL.md"],
                )
                mock_analyzer.git_clone.side_effect = _mock_clone
                mock_cls.return_value = mock_analyzer

                with patch("vibesop.installer.pack_installer.InstallPlanner") as planner_cls:
                    mock_plan = MagicMock()
                    mock_plan.target_path = target_path
                    planner_cls.return_value.plan.return_value = mock_plan

                    success, msg = installer.install_pack(
                        "test-pack", "https://example.com/test-pack"
                    )

            assert success is True
            assert "PASS" in msg
            mock_auditor.audit_skill_file.assert_called_once()

    @patch("vibesop.installer.pack_installer.SkillSecurityAuditor")
    def test_install_pack_with_build_sh(self, mock_auditor_cls: Any) -> None:
        """Pack with BUILD.sh should run build and report output."""
        mock_audit = MagicMock()
        mock_audit.is_safe = True
        mock_auditor = MagicMock()
        mock_auditor.audit_skill_file.return_value = mock_audit
        mock_auditor_cls.return_value = mock_auditor

        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir) / "test-pack"

            installer = PackInstaller(external_paths=[Path(tmpdir)])

            def _mock_clone(url: str, dest: Path) -> bool:
                dest.mkdir(parents=True, exist_ok=True)
                (dest / "SKILL.md").write_text("# Test\n")
                (dest / "BUILD.sh").write_text("#!/bin/sh\necho 'built'")
                return True

            with patch("vibesop.installer.pack_installer.RepoAnalyzer") as mock_cls:
                mock_analyzer = MagicMock()
                mock_analyzer.analyze.return_value = MagicMock(
                    errors=[],
                    skill_files=[target_path / "SKILL.md"],
                    setup_scripts=["BUILD.sh"],
                )
                mock_analyzer.git_clone.side_effect = _mock_clone
                mock_cls.return_value = mock_analyzer

                with patch("vibesop.installer.pack_installer.InstallPlanner") as planner_cls:
                    mock_plan = MagicMock()
                    mock_plan.target_path = target_path
                    planner_cls.return_value.plan.return_value = mock_plan

                    success, msg = installer.install_pack(
                        "test-pack", "https://example.com/test-pack"
                    )

            assert success is True
            assert "Build:" in msg
            assert "BUILD.sh" in msg or "built" in msg

    @patch("vibesop.installer.pack_installer.SkillSecurityAuditor")
    def test_install_pack_without_build_script(self, mock_auditor_cls: Any) -> None:
        """Pack without build script should not report Build line."""
        mock_audit = MagicMock()
        mock_audit.is_safe = True
        mock_auditor = MagicMock()
        mock_auditor.audit_skill_file.return_value = mock_audit
        mock_auditor_cls.return_value = mock_auditor

        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir) / "test-pack"

            installer = PackInstaller(external_paths=[Path(tmpdir)])

            def _mock_clone(url: str, dest: Path) -> bool:
                dest.mkdir(parents=True, exist_ok=True)
                (dest / "SKILL.md").write_text("# Test\n")
                return True

            with patch("vibesop.installer.pack_installer.RepoAnalyzer") as mock_cls:
                mock_analyzer = MagicMock()
                mock_analyzer.analyze.return_value = MagicMock(
                    errors=[],
                    skill_files=[target_path / "SKILL.md"],
                    setup_scripts=[],
                )
                mock_analyzer.git_clone.side_effect = _mock_clone
                mock_cls.return_value = mock_analyzer

                with patch("vibesop.installer.pack_installer.InstallPlanner") as planner_cls:
                    mock_plan = MagicMock()
                    mock_plan.target_path = target_path
                    planner_cls.return_value.plan.return_value = mock_plan

                    success, msg = installer.install_pack(
                        "test-pack", "https://example.com/test-pack"
                    )

            assert success is True
            assert "Build:" not in msg


class TestSkillSymlinks:
    """Tests for _create_skill_symlinks and _copy_skill_dirs."""

    def test_create_skill_symlinks_flat_layout(self, tmp_path):
        """Skill symlinks are created with correct flattened names for flat layout."""
        from vibesop.installer.pack_installer import PackInstaller

        # Create a mock pack structure
        central = tmp_path / "central"
        pack = central / "testpack"
        review_dir = pack / "review"
        review_dir.mkdir(parents=True)
        (review_dir / "SKILL.md").write_text("---\nname: review\n---\n# Test skill")
        qa_dir = pack / "qa"
        qa_dir.mkdir(parents=True)
        (qa_dir / "SKILL.md").write_text("---\nname: qa\n---\n# QA skill")

        platform = tmp_path / "platform"
        platform.mkdir(parents=True)

        installer = PackInstaller(central_storage=central, platform_paths=[platform])
        count = installer._create_skill_symlinks(pack, platform, "testpack")

        assert count == 2


class TestPostInstallHook:
    """Tests for _run_post_install build script detection and execution."""

    def test_no_build_script_returns_empty(self, tmp_path):
        """Pack without build scripts returns empty string."""
        from vibesop.installer.pack_installer import PackInstaller

        installer = PackInstaller(external_paths=[tmp_path])
        pack_dir = tmp_path / "pack"
        pack_dir.mkdir()
        (pack_dir / "SKILL.md").write_text("# Test")

        result = installer._run_post_install(pack_dir, object())
        assert result == ""

    def test_build_sh_executed(self, tmp_path):
        """BUILD.sh is detected and executed."""
        from vibesop.installer.pack_installer import PackInstaller

        installer = PackInstaller(external_paths=[tmp_path])
        pack_dir = tmp_path / "pack"
        pack_dir.mkdir()
        (pack_dir / "BUILD.sh").write_text("#!/bin/sh\necho 'built'")

        result = installer._run_post_install(pack_dir, object())
        assert "BUILD.sh" in result

    def test_vibesop_build_priority(self, tmp_path):
        """.vibesop-build takes priority over BUILD.sh."""
        from vibesop.installer.pack_installer import PackInstaller

        installer = PackInstaller(external_paths=[tmp_path])
        pack_dir = tmp_path / "pack"
        pack_dir.mkdir()
        (pack_dir / ".vibesop-build").write_text("#!/bin/sh\necho 'vibesop'")
        (pack_dir / "BUILD.sh").write_text("#!/bin/sh\necho 'build'")

        result = installer._run_post_install(pack_dir, object())
        assert "vibesop-build" in result

    def test_package_json_bun_fallback(self, tmp_path, monkeypatch):
        """If no build script, bun run gen:skill-docs is attempted."""
        import shutil as _shutil

        from vibesop.installer.pack_installer import PackInstaller

        installer = PackInstaller(external_paths=[tmp_path])
        pack_dir = tmp_path / "pack"
        pack_dir.mkdir()
        (pack_dir / "package.json").write_text('{"scripts":{"gen:skill-docs":"echo skills"}}')

        def _mock_which(cmd):
            if cmd == "bun":
                return "/usr/local/bin/bun"
            return _shutil.which(cmd)

        monkeypatch.setattr("shutil.which", _mock_which)

        result = installer._run_post_install(pack_dir, object())
        assert isinstance(result, str)

    def test_setup_sh_executed(self, tmp_path):
        """setup.sh is also detected as a build script."""
        from vibesop.installer.pack_installer import PackInstaller

        installer = PackInstaller(external_paths=[tmp_path])
        pack_dir = tmp_path / "pack"
        pack_dir.mkdir()
        (pack_dir / "setup.sh").write_text("#!/bin/sh\necho 'setup'")

        result = installer._run_post_install(pack_dir, object())
        assert "setup.sh" in result

    def test_create_skill_symlinks_root_skill_md(self, tmp_path):
        """Root-level SKILL.md is symlinked using pack_name as the flat name."""
        from vibesop.installer.pack_installer import PackInstaller

        central = tmp_path / "central"
        pack = central / "testpack"
        pack.mkdir(parents=True)
        (pack / "SKILL.md").write_text("---\nname: testpack\n---\n# Pack manifest")

        platform = tmp_path / "platform"
        platform.mkdir(parents=True)

        installer = PackInstaller(central_storage=central, platform_paths=[platform])
        count = installer._create_skill_symlinks(pack, platform, "testpack")

        assert count == 1
