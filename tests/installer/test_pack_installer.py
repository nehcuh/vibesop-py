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
