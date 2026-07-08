"""Tests for PackInstaller."""

import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from vibesop.installer.pack_installer import PackInstaller
from vibesop.security.skill_auditor import PackAuditResult


@contextmanager
def _allow_local_build():
    """Mock the F-03 interactive gate so tests can exercise local build execution."""
    with (
        patch("vibesop.installer.pack_installer.sys.stdin.isatty", return_value=True),
        patch("vibesop.installer.pack_installer.Confirm.ask", return_value=True),
    ):
        yield


def _clean_pack_audit() -> PackAuditResult:
    """Helper: a passing pre-install audit result for use in tests that mock
    SkillSecurityAuditor. Returns no critical/high threats so the install
    proceeds past the pre-audit gate introduced in v7.0.1."""
    return PackAuditResult(is_safe=True, files_scanned=1)


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

                success, msg = installer.install_pack("test-pack", "https://example.com/test-pack")

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

                success, msg = installer.install_pack("test-pack", "https://example.com/test-pack")

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
        mock_auditor.audit_pack_files.return_value = _clean_pack_audit()
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
        mock_auditor.audit_pack_files.return_value = _clean_pack_audit()
        mock_auditor_cls.return_value = mock_auditor

        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir) / "test-pack"

            installer = PackInstaller(
                external_paths=[Path(tmpdir)],
                sandbox_builds=False,
                allow_unsafe_build=True,
            )

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

                    with _allow_local_build():
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
        mock_auditor.audit_pack_files.return_value = _clean_pack_audit()
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
    """Tests for create_skill_symlinks and _copy_skill_dirs."""

    def test_create_skill_symlinks_flat_layout(self, tmp_path):
        """Skill symlinks are created with correct flattened names for flat layout."""
        from vibesop.installer.pack_installer import PackInstaller

        # Create a mock pack structure
        central = tmp_path / "central"
        pack = central / "testpack"
        review_dir = pack / "review"
        review_dir.mkdir(parents=True)
        (review_dir / "SKILL.md").write_text(
            "---\nname: review\ndescription: Review code changes\n---\n# Test skill"
        )
        qa_dir = pack / "qa"
        qa_dir.mkdir(parents=True)
        (qa_dir / "SKILL.md").write_text(
            "---\nname: qa\ndescription: QA test the application\n---\n# QA skill"
        )

        platform = tmp_path / "platform"
        platform.mkdir(parents=True)

        installer = PackInstaller(central_storage=central, platform_paths=[platform])
        try:
            count = installer.create_skill_symlinks(pack, platform, "testpack")
        except OSError:
            # Fallback for Windows without symlink privileges
            count = installer._copy_skill_dirs(pack, platform, "testpack")

        assert count == 2


class TestPostInstallHook:
    """Tests for _run_post_install build script detection and execution."""

    def test_symlinked_build_script_outside_pack_rejected(self, tmp_path):
        """A BUILD.sh symlink pointing outside the pack must not be executed."""
        from vibesop.installer.pack_installer import PackInstaller

        installer = PackInstaller(external_paths=[tmp_path], allow_unsafe_build=True)
        pack_dir = tmp_path / "pack"
        pack_dir.mkdir()
        secret = tmp_path / "secret.txt"
        secret.write_text("sensitive data")
        (pack_dir / "BUILD.sh").symlink_to(secret)

        with _allow_local_build():
            result = installer._run_post_install(pack_dir, object())
        # The confirmation gate should reject the symlink and decline execution.
        assert "declined" in result.lower()

    def test_build_sh_executed(self, tmp_path):
        """BUILD.sh is detected and executed."""
        from vibesop.installer.pack_installer import PackInstaller

        installer = PackInstaller(external_paths=[tmp_path], allow_unsafe_build=True)
        pack_dir = tmp_path / "pack"
        pack_dir.mkdir()
        (pack_dir / "BUILD.sh").write_text("#!/bin/sh\necho 'built'")

        with _allow_local_build():
            result = installer._run_post_install(pack_dir, object())
        assert "BUILD.sh" in result

    def test_vibesop_build_priority(self, tmp_path):
        """.vibesop-build takes priority over BUILD.sh."""
        from vibesop.installer.pack_installer import PackInstaller

        installer = PackInstaller(external_paths=[tmp_path], allow_unsafe_build=True)
        pack_dir = tmp_path / "pack"
        pack_dir.mkdir()
        (pack_dir / ".vibesop-build").write_text("#!/bin/sh\necho 'vibesop'")
        (pack_dir / "BUILD.sh").write_text("#!/bin/sh\necho 'build'")

        with _allow_local_build():
            result = installer._run_post_install(pack_dir, object())
        assert "vibesop-build" in result

    def test_package_json_bun_fallback(self, tmp_path, monkeypatch):
        """If no build script, bun run gen:skill-docs is attempted."""
        import shutil as _shutil

        from vibesop.installer.pack_installer import PackInstaller

        installer = PackInstaller(external_paths=[tmp_path], allow_unsafe_build=True)
        pack_dir = tmp_path / "pack"
        pack_dir.mkdir()
        (pack_dir / "package.json").write_text('{"scripts":{"gen:skill-docs":"echo skills"}}')

        def _mock_which(cmd):
            if cmd == "bun":
                return "/usr/local/bin/bun"
            return _shutil.which(cmd)

        monkeypatch.setattr("shutil.which", _mock_which)

        with _allow_local_build():
            result = installer._run_post_install(pack_dir, object())
        assert isinstance(result, str)

    def test_setup_sh_executed(self, tmp_path):
        """setup.sh is also detected as a build script."""
        from vibesop.installer.pack_installer import PackInstaller

        installer = PackInstaller(external_paths=[tmp_path], allow_unsafe_build=True)
        pack_dir = tmp_path / "pack"
        pack_dir.mkdir()
        (pack_dir / "setup.sh").write_text("#!/bin/sh\necho 'setup'")

        with _allow_local_build():
            result = installer._run_post_install(pack_dir, object())
        assert "setup.sh" in result

    def test_create_skill_symlinks_root_skill_md(self, tmp_path):
        """Root-level SKILL.md is symlinked using pack_name as the flat name."""
        from vibesop.installer.pack_installer import PackInstaller

        central = tmp_path / "central"
        pack = central / "testpack"
        pack.mkdir(parents=True)
        (pack / "SKILL.md").write_text(
            "---\nname: testpack\ndescription: Root level test pack skill\n---\n# Pack manifest"
        )

        platform = tmp_path / "platform"
        platform.mkdir(parents=True)

        installer = PackInstaller(central_storage=central, platform_paths=[platform])
        try:
            count = installer.create_skill_symlinks(pack, platform, "testpack")
        except OSError:
            # Fallback for Windows without symlink privileges
            count = installer._copy_skill_dirs(pack, platform, "testpack")

        assert count == 1


class TestSkillNameDedup:
    """Tests for cross-pack deduplication by frontmatter ``name:``."""

    def _make_pack(
        self, central: Path, pack_name: str, skill_name: str, rel: str = "review"
    ) -> Path:
        pack = central / pack_name
        skill_dir = pack / rel
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {skill_name}\ndescription: A test skill for dedup verification\n---\n# {skill_name}\n"
        )
        return pack

    def test_dedup_skips_same_name_across_packs(self, tmp_path):
        """Two packs installing a skill with the same ``name:`` → only first lands."""
        from vibesop.installer.pack_installer import PackInstaller

        central = tmp_path / "central"
        platform = tmp_path / "platform"
        platform.mkdir(parents=True)

        pack_a = self._make_pack(central, "packA", "shared-skill", rel="review")
        pack_b = self._make_pack(central, "packB", "shared-skill", rel="deeply/nested/review")

        installer = PackInstaller(central_storage=central, platform_paths=[platform])

        count_a = installer.create_skill_symlinks(pack_a, platform, "packA")
        count_b = installer.create_skill_symlinks(pack_b, platform, "packB")

        assert count_a == 1
        assert count_b == 0
        entries = sorted(p.name for p in platform.iterdir())
        assert entries == ["packA-review"]

    def test_dedupe_disabled_installs_both(self, tmp_path):
        """``dedupe_by_name=False`` preserves the legacy duplicate behavior."""
        from vibesop.installer.pack_installer import PackInstaller

        central = tmp_path / "central"
        platform = tmp_path / "platform"
        platform.mkdir(parents=True)

        pack_a = self._make_pack(central, "packA", "shared-skill", rel="review")
        pack_b = self._make_pack(central, "packB", "shared-skill", rel="deeply/nested/review")

        installer = PackInstaller(central_storage=central, platform_paths=[platform])

        count_a = installer.create_skill_symlinks(pack_a, platform, "packA", dedupe_by_name=False)
        count_b = installer.create_skill_symlinks(pack_b, platform, "packB", dedupe_by_name=False)

        assert count_a == 1
        assert count_b == 1
        entries = sorted(p.name for p in platform.iterdir())
        assert entries == ["packA-review", "packB-deeply-nested-review"]

    def test_different_names_both_installed(self, tmp_path):
        """Distinct ``name:`` values are never deduped."""
        from vibesop.installer.pack_installer import PackInstaller

        central = tmp_path / "central"
        platform = tmp_path / "platform"
        platform.mkdir(parents=True)

        pack_a = self._make_pack(central, "packA", "alpha", rel="alpha")
        pack_b = self._make_pack(central, "packB", "beta", rel="beta")

        installer = PackInstaller(central_storage=central, platform_paths=[platform])

        count_a = installer.create_skill_symlinks(pack_a, platform, "packA")
        count_b = installer.create_skill_symlinks(pack_b, platform, "packB")

        assert count_a == 1
        assert count_b == 1
        entries = sorted(p.name for p in platform.iterdir())
        assert entries == ["packA-alpha", "packB-beta"]

    def test_missing_name_field_falls_back_to_path_dedup(self, tmp_path):
        """A SKILL.md without ``name:`` is not deduped (falls back to path-based logic)."""
        from vibesop.installer.pack_installer import PackInstaller

        central = tmp_path / "central"
        platform = tmp_path / "platform"
        platform.mkdir(parents=True)

        # Pack A has a name, pack B does not
        pack_a = central / "packA" / "review"
        pack_a.mkdir(parents=True)
        (pack_a / "SKILL.md").write_text(
            "---\nname: alpha\ndescription: Has a name field\n---\n# alpha\n"
        )

        pack_b = central / "packB" / "review"
        pack_b.mkdir(parents=True)
        (pack_b / "SKILL.md").write_text(
            "---\ndescription: No name field here at all\n---\n# beta\n"
        )

        installer = PackInstaller(central_storage=central, platform_paths=[platform])
        count_a = installer.create_skill_symlinks(pack_a.parent, platform, "packA")
        count_b = installer.create_skill_symlinks(pack_b.parent, platform, "packB")

        # Both installed because packB has no resolvable name
        assert count_a == 1
        assert count_b == 1
        entries = sorted(p.name for p in platform.iterdir())
        assert entries == ["packA-review", "packB-review"]
