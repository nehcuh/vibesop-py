"""Tests for PackInstaller."""

import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from vibesop.installer.omx_cli import OmxCliResult
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
                (dest / "SKILL.md").write_text("# Test Skill\n", encoding="utf-8")
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
                (dest / "SKILL.md").write_text("# Test\n", encoding="utf-8")
                (dest / "BUILD.sh").write_text("#!/bin/sh\necho 'built'", encoding="utf-8")
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
                (dest / "SKILL.md").write_text("# Test\n", encoding="utf-8")
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


class TestOmxCliCompanion:
    """Successful omx installs must ensure the CLI; other packs must not."""

    def test_omx_fresh_install_appends_cli_detail(self) -> None:
        cli = OmxCliResult("installed", "omx CLI installed (/usr/bin/omx)", "/usr/bin/omx")
        with tempfile.TemporaryDirectory() as tmpdir:
            installer = PackInstaller(external_paths=[Path(tmpdir)])
            with patch("vibesop.installer.pack_installer.RepoAnalyzer") as mock_cls:
                mock_analyzer = MagicMock()
                mock_analyzer.analyze.return_value = MagicMock(
                    errors=[],
                    skill_files=[Path("skills/autopilot/SKILL.md")],
                )
                mock_analyzer.git_clone.return_value = True
                mock_cls.return_value = mock_analyzer
                with patch("vibesop.installer.pack_installer.InstallPlanner") as planner_cls:
                    mock_plan = MagicMock()
                    mock_plan.target_path = Path(tmpdir) / "omx"
                    planner_cls.return_value.plan.return_value = mock_plan
                    with patch(
                        "vibesop.installer.pack_installer.ensure_omx_cli",
                        return_value=cli,
                    ) as mock_cli:
                        success, msg = installer.install_pack(
                            "omx", "https://github.com/Yeachan-Heo/oh-my-codex"
                        )
        assert success is True
        mock_cli.assert_called_once()
        assert "omx CLI installed (/usr/bin/omx)" in msg

    def test_non_omx_pack_does_not_ensure_cli(self) -> None:
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
                    with patch("vibesop.installer.pack_installer.ensure_omx_cli") as mock_cli:
                        success, _msg = installer.install_pack(
                            "test-pack", "https://example.com/test-pack"
                        )
        assert success is True
        mock_cli.assert_not_called()

    def test_omx_already_installed_still_ensures_cli(self) -> None:
        cli = OmxCliResult("present", "omx CLI already on PATH (/usr/bin/omx)", "/usr/bin/omx")
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "omx"
            target.mkdir()
            (target / "SKILL.md").write_text("# omx\n", encoding="utf-8")
            installer = PackInstaller(external_paths=[Path(tmpdir)])
            with patch("vibesop.installer.pack_installer.RepoAnalyzer") as mock_cls:
                mock_analyzer = MagicMock()
                mock_analyzer.analyze.return_value = MagicMock(
                    errors=[],
                    skill_files=[target / "SKILL.md"],
                )
                mock_cls.return_value = mock_analyzer
                with patch("vibesop.installer.pack_installer.InstallPlanner") as planner_cls:
                    mock_plan = MagicMock()
                    mock_plan.target_path = target
                    planner_cls.return_value.plan.return_value = mock_plan
                    with patch(
                        "vibesop.installer.pack_installer.ensure_omx_cli",
                        return_value=cli,
                    ) as mock_cli:
                        success, msg = installer.install_pack(
                            "omx", "https://github.com/Yeachan-Heo/oh-my-codex"
                        )
        assert success is True
        mock_cli.assert_called_once()
        assert "Already installed" in msg
        assert "omx CLI already on PATH" in msg


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
            "---\nname: review\ndescription: Review code changes\n---\n# Test skill",
            encoding="utf-8",
        )
        qa_dir = pack / "qa"
        qa_dir.mkdir(parents=True)
        (qa_dir / "SKILL.md").write_text(
            "---\nname: qa\ndescription: QA test the application\n---\n# QA skill",
            encoding="utf-8",
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

    def test_copy_skill_dirs_writes_ownership_marker(self, tmp_path):
        """Copied skill dirs get .vibe-manifest.json so clean_orphan_skills
        can reclaim them later."""
        import json

        from vibesop.installer.pack_installer import PackInstaller

        central = tmp_path / "central"
        pack = central / "testpack"
        skill_dir = pack / "review"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: review\ndescription: Review code changes\n---\n# Test skill",
            encoding="utf-8",
        )

        platform = tmp_path / "platform"
        platform.mkdir(parents=True)

        installer = PackInstaller(central_storage=central, platform_paths=[platform])
        count = installer._copy_skill_dirs(pack, platform, "testpack")

        assert count == 1
        marker = platform / "testpack-review" / ".vibe-manifest.json"
        assert marker.exists(), "pack copy must write the ownership marker"
        data = json.loads(marker.read_text(encoding="utf-8"))
        assert data["source"]["type"] == "pack-copy"

    def test_copy_skill_dirs_preserves_source_marker(self, tmp_path):
        """A marker already present in central storage is kept as-is."""
        central = tmp_path / "central"
        pack = central / "testpack"
        skill_dir = pack / "review"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: review\ndescription: Review code changes\n---\n# Test skill",
            encoding="utf-8",
        )
        (skill_dir / ".vibe-manifest.json").write_text(
            '{"id": "review", "source": {"type": "local"}}', encoding="utf-8"
        )

        platform = tmp_path / "platform"
        platform.mkdir(parents=True)

        installer = PackInstaller(central_storage=central, platform_paths=[platform])
        installer._copy_skill_dirs(pack, platform, "testpack")

        marker = platform / "testpack-review" / ".vibe-manifest.json"
        assert marker.read_text(encoding="utf-8") == (
            '{"id": "review", "source": {"type": "local"}}'
        ), "source marker must be preserved"


class TestPostInstallHook:
    """Tests for _run_post_install build script detection and execution."""

    def test_symlinked_build_script_outside_pack_rejected(self, tmp_path, symlink_supported):
        """A BUILD.sh symlink pointing outside the pack must not be executed."""
        if not symlink_supported:
            pytest.skip("directory symlinks not supported on this host")
        from vibesop.installer.pack_installer import PackInstaller

        installer = PackInstaller(external_paths=[tmp_path], allow_unsafe_build=True)
        pack_dir = tmp_path / "pack"
        pack_dir.mkdir()
        secret = tmp_path / "secret.txt"
        secret.write_text("sensitive data", encoding="utf-8")
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
        (pack_dir / "BUILD.sh").write_text("#!/bin/sh\necho 'built'", encoding="utf-8")

        with _allow_local_build():
            result = installer._run_post_install(pack_dir, object())
        assert "BUILD.sh" in result

    def test_vibesop_build_priority(self, tmp_path):
        """.vibesop-build takes priority over BUILD.sh."""
        from vibesop.installer.pack_installer import PackInstaller

        installer = PackInstaller(external_paths=[tmp_path], allow_unsafe_build=True)
        pack_dir = tmp_path / "pack"
        pack_dir.mkdir()
        (pack_dir / ".vibesop-build").write_text("#!/bin/sh\necho 'vibesop'", encoding="utf-8")
        (pack_dir / "BUILD.sh").write_text("#!/bin/sh\necho 'build'", encoding="utf-8")

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
        (pack_dir / "package.json").write_text(
            '{"scripts":{"gen:skill-docs":"echo skills"}}', encoding="utf-8"
        )

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
        (pack_dir / "setup.sh").write_text("#!/bin/sh\necho 'setup'", encoding="utf-8")

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
            "---\nname: testpack\ndescription: Root level test pack skill\n---\n# Pack manifest",
            encoding="utf-8",
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
            f"---\nname: {skill_name}\ndescription: A test skill for dedup verification\n---\n# {skill_name}\n",
            encoding="utf-8",
        )
        return pack

    def test_flatten_skill_name_normalizes_separators(self) -> None:
        """rel_path from Path.relative_to() uses native separators — backslashes
        on Windows must flatten too, else the link target lands in a nested
        non-existent directory (WinError 3 on windows-latest CI)."""
        from vibesop.installer.pack_installer import PackInstaller

        assert (
            PackInstaller._flatten_skill_name("packB", "deeply/nested/review")
            == "packB-deeply-nested-review"
        )
        assert (
            PackInstaller._flatten_skill_name("packB", "deeply\\nested\\review")
            == "packB-deeply-nested-review"
        )
        assert PackInstaller._flatten_skill_name("packB", ".") == "packB"

    def test_dedup_skips_same_name_across_packs(self, tmp_path, symlink_supported):
        """Two packs installing a skill with the same ``name:`` → only first lands."""
        if not symlink_supported:
            pytest.skip("directory symlinks not supported on this host")
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

    def test_dedupe_disabled_installs_both(self, tmp_path, symlink_supported):
        """``dedupe_by_name=False`` preserves the legacy duplicate behavior."""
        if not symlink_supported:
            pytest.skip("directory symlinks not supported on this host")
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

    def test_different_names_both_installed(self, tmp_path, symlink_supported):
        """Distinct ``name:`` values are never deduped."""
        if not symlink_supported:
            pytest.skip("directory symlinks not supported on this host")
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

    def test_missing_name_field_falls_back_to_path_dedup(self, tmp_path, symlink_supported):
        """A SKILL.md without ``name:`` is not deduped (falls back to path-based logic)."""
        if not symlink_supported:
            pytest.skip("directory symlinks not supported on this host")
        from vibesop.installer.pack_installer import PackInstaller

        central = tmp_path / "central"
        platform = tmp_path / "platform"
        platform.mkdir(parents=True)

        # Pack A has a name, pack B does not
        pack_a = central / "packA" / "review"
        pack_a.mkdir(parents=True)
        (pack_a / "SKILL.md").write_text(
            "---\nname: alpha\ndescription: Has a name field\n---\n# alpha\n",
            encoding="utf-8",
        )

        pack_b = central / "packB" / "review"
        pack_b.mkdir(parents=True)
        (pack_b / "SKILL.md").write_text(
            "---\ndescription: No name field here at all\n---\n# beta\n",
            encoding="utf-8",
        )

        installer = PackInstaller(central_storage=central, platform_paths=[platform])
        count_a = installer.create_skill_symlinks(pack_a.parent, platform, "packA")
        count_b = installer.create_skill_symlinks(pack_b.parent, platform, "packB")

        # Both installed because packB has no resolvable name
        assert count_a == 1
        assert count_b == 1
        entries = sorted(p.name for p in platform.iterdir())
        assert entries == ["packA-review", "packB-review"]


class TestProjectScopeInstall:
    """``scope="project"`` installs into ``<project_root>/.vibe/skills/<pack>/``.

    The full security chain (pre-audit, F-02 pack-lock, F-03 build gate) runs
    exactly as for global installs; only platform symlinks and the global
    index rebuild are skipped.
    """

    @patch("vibesop.installer.pack_installer.SkillSecurityAuditor")
    def test_project_scope_layout_and_discovery(self, mock_auditor_cls: Any, tmp_path) -> None:
        mock_audit = MagicMock()
        mock_audit.is_safe = True
        mock_auditor = MagicMock()
        mock_auditor.audit_skill_file.return_value = mock_audit
        mock_auditor.audit_pack_files.return_value = _clean_pack_audit()
        mock_auditor_cls.return_value = mock_auditor

        project_root = tmp_path / "proj"
        central = tmp_path / "central"
        platform = tmp_path / "platform"
        installer = PackInstaller(
            central_storage=central,
            platform_paths=[platform],
            project_root=project_root,
        )

        def _mock_clone(url: str, dest: Path) -> bool:
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "SKILL.md").write_text(
                "---\nname: proj-pack\ndescription: A project-scope test skill pack\n---\n# Test\n",
                encoding="utf-8",
            )
            return True

        with patch("vibesop.installer.pack_installer.RepoAnalyzer") as mock_cls:
            mock_analyzer = MagicMock()
            mock_analyzer.analyze.return_value = MagicMock(
                errors=[],
                skill_files=[Path("SKILL.md")],
                pack_name="proj-pack",
                source_url="https://example.com/proj-pack",
                readme_install_hint="",
                setup_scripts=[],
            )
            mock_analyzer.git_clone.side_effect = _mock_clone
            mock_cls.return_value = mock_analyzer

            success, msg = installer.install_pack(
                "proj-pack", "https://example.com/proj-pack", scope="project"
            )

        assert success is True, msg
        pack_dir = project_root / ".vibe" / "skills" / "proj-pack"
        assert (pack_dir / "SKILL.md").is_file()
        assert str(pack_dir) in msg

        # Project scope skips platform symlinks and the central-storage copy.
        assert not (central / "proj-pack").exists()
        assert not platform.exists()

        # F-02: the pack lock is recorded (conftest isolates the lock store).
        from vibesop.core.skills.pack_lock import PackLockStore

        assert PackLockStore().get("proj-pack") is not None

        # The project-level pack is discovered by the skill loader, like any
        # other .vibe/skills/ skill (e.g. instinct-evolved ones).
        from vibesop.core.skills.loader import SkillLoader

        skills = SkillLoader(project_root=project_root, enable_external=False).discover_all()
        assert "proj-pack" in skills
        source_file = skills["proj-pack"].source_file
        assert source_file is not None
        assert ".vibe/skills/proj-pack" in source_file.as_posix()

    @patch("vibesop.installer.pack_installer.SkillSecurityAuditor")
    def test_project_scope_already_installed_branch(self, mock_auditor_cls: Any, tmp_path) -> None:
        mock_audit = MagicMock()
        mock_audit.is_safe = True
        mock_auditor = MagicMock()
        mock_auditor.audit_skill_file.return_value = mock_audit
        mock_auditor.audit_pack_files.return_value = _clean_pack_audit()
        mock_auditor_cls.return_value = mock_auditor

        project_root = tmp_path / "proj"
        installer = PackInstaller(
            central_storage=tmp_path / "central",
            platform_paths=[tmp_path / "platform"],
            project_root=project_root,
        )

        def _mock_clone(url: str, dest: Path) -> bool:
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "SKILL.md").write_text(
                "---\nname: proj-pack\ndescription: A project-scope test skill pack\n---\n# Test\n",
                encoding="utf-8",
            )
            return True

        with patch("vibesop.installer.pack_installer.RepoAnalyzer") as mock_cls:
            mock_analyzer = MagicMock()
            mock_analyzer.analyze.return_value = MagicMock(
                errors=[],
                skill_files=[Path("SKILL.md")],
                pack_name="proj-pack",
                source_url="https://example.com/proj-pack",
                readme_install_hint="",
                setup_scripts=[],
            )
            mock_analyzer.git_clone.side_effect = _mock_clone
            mock_cls.return_value = mock_analyzer

            url = "https://example.com/proj-pack"
            first, _ = installer.install_pack("proj-pack", url, scope="project")
            second, msg = installer.install_pack("proj-pack", url, scope="project")

        assert first is True
        assert second is True
        assert "Already installed" in msg
        # The second install short-circuits before re-cloning.
        mock_analyzer.git_clone.assert_called_once()

    @patch("vibesop.installer.pack_installer.SkillSecurityAuditor")
    def test_global_scope_unchanged(self, mock_auditor_cls: Any, tmp_path) -> None:
        """Default scope still installs to central storage."""
        mock_audit = MagicMock()
        mock_audit.is_safe = True
        mock_auditor = MagicMock()
        mock_auditor.audit_skill_file.return_value = mock_audit
        mock_auditor.audit_pack_files.return_value = _clean_pack_audit()
        mock_auditor_cls.return_value = mock_auditor

        central = tmp_path / "central"
        project_root = tmp_path / "proj"
        installer = PackInstaller(
            central_storage=central,
            platform_paths=[tmp_path / "platform"],
            project_root=project_root,
        )

        def _mock_clone(url: str, dest: Path) -> bool:
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "SKILL.md").write_text(
                "---\nname: glob-pack\ndescription: A global-scope test skill pack\n---\n# Test\n",
                encoding="utf-8",
            )
            return True

        with patch("vibesop.installer.pack_installer.RepoAnalyzer") as mock_cls:
            mock_analyzer = MagicMock()
            mock_analyzer.analyze.return_value = MagicMock(
                errors=[],
                skill_files=[Path("SKILL.md")],
                pack_name="glob-pack",
                source_url="https://example.com/glob-pack",
                readme_install_hint="",
                setup_scripts=[],
            )
            mock_analyzer.git_clone.side_effect = _mock_clone
            mock_cls.return_value = mock_analyzer

            with patch.object(installer, "_create_symlinks", return_value=[]):
                success, msg = installer.install_pack("glob-pack", "https://example.com/glob-pack")

        assert success is True, msg
        assert (central / "glob-pack" / "SKILL.md").is_file()
        assert not (project_root / ".vibe" / "skills" / "glob-pack").exists()
