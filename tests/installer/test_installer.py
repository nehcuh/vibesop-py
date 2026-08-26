"""Tests for VibeSOP installer."""

import tempfile
from pathlib import Path

from vibesop.installer import VibeSOPInstaller


class TestVibeSOPInstaller:
    """Test VibeSOPInstaller functionality."""

    def test_create_installer(self) -> None:
        """Test creating installer."""
        installer = VibeSOPInstaller()
        assert installer is not None

    def test_list_platforms(self) -> None:
        """Test listing supported platforms."""
        installer = VibeSOPInstaller()
        platforms = installer.list_platforms()

        assert len(platforms) >= 2
        assert any(p["name"] == "claude-code" for p in platforms)
        assert any(p["name"] == "opencode" for p in platforms)
        assert any(p["name"] == "grok-build" for p in platforms)

        # Check structure
        for platform in platforms:
            assert "name" in platform
            assert "description" in platform
            assert "config_dir" in platform

    def test_install_claude_code(self) -> None:
        """Test installing Claude Code configuration."""
        installer = VibeSOPInstaller()

        with tempfile.TemporaryDirectory() as tmpdir:
            result = installer.install("claude-code", Path(tmpdir))

            # Installation may fail if templates are missing, which is OK
            assert result["platform"] == "claude-code"
            assert result["config_dir"] == tmpdir

    def test_install_opencode(self) -> None:
        """Test installing OpenCode configuration."""
        installer = VibeSOPInstaller()

        with tempfile.TemporaryDirectory() as tmpdir:
            result = installer.install("opencode", Path(tmpdir))

            assert result["success"]
            assert result["platform"] == "opencode"
            assert len(result["files_created"]) > 0

            # Check files exist
            config_dir = Path(tmpdir)
            assert (config_dir / "config.yaml").exists()

    def test_install_grok_build(self) -> None:
        """Grok Build install must write native JSON hooks and routing rules."""
        installer = VibeSOPInstaller()

        with tempfile.TemporaryDirectory() as tmpdir:
            result = installer.install("grok-build", Path(tmpdir), force=True)

            assert result["success"], result.get("errors")
            assert result["platform"] == "grok-build"
            config_dir = Path(tmpdir)
            assert (config_dir / "rules" / "routing.md").exists()
            assert (config_dir / "hooks" / "vibesop-route.json").exists()
            hooks = result.get("hooks_installed", [])
            assert hooks, "adapter-rendered grok-build hooks must be reported"
            assert any("vibesop-route" in str(h) for h in hooks)
            assert installer._is_configured(config_dir)

    def test_install_unknown_platform(self) -> None:
        """Test installing for unknown platform."""
        installer = VibeSOPInstaller()

        with tempfile.TemporaryDirectory() as tmpdir:
            result = installer.install("unknown-platform", Path(tmpdir))

            assert not result["success"]
            assert "Unknown platform" in result["errors"][0]

    def test_install_with_force(self) -> None:
        """Test installing with force flag."""
        installer = VibeSOPInstaller()

        with tempfile.TemporaryDirectory() as tmpdir:
            # First installation
            result1 = installer.install("claude-code", Path(tmpdir), force=False)
            assert result1["success"]

            # Second installation without force (should warn)
            result2 = installer.install("claude-code", Path(tmpdir), force=False)
            assert result2["success"]  # Still succeeds
            assert len(result2["warnings"]) > 0
            assert "already exists" in result2["warnings"][0]

            # Third installation with force (should overwrite)
            result3 = installer.install("claude-code", Path(tmpdir), force=True)
            assert result3["success"]

    def test_uninstall(self) -> None:
        """Test uninstalling configuration."""
        installer = VibeSOPInstaller()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Install first
            install_result = installer.install("claude-code", Path(tmpdir))
            assert install_result["success"]

            # Check files exist
            config_dir = Path(tmpdir)
            assert (config_dir / "CLAUDE.md").exists()

            # Uninstall
            uninstall_result = installer.uninstall("claude-code", Path(tmpdir))
            assert uninstall_result["success"]
            assert len(uninstall_result["files_removed"]) > 0

            # Check files removed
            assert not (config_dir / "CLAUDE.md").exists()

    def test_uninstall_unknown_platform(self) -> None:
        """Test uninstalling unknown platform."""
        installer = VibeSOPInstaller()

        with tempfile.TemporaryDirectory() as tmpdir:
            result = installer.uninstall("unknown-platform", Path(tmpdir))

            assert not result["success"]
            assert "Unknown platform" in result["errors"][0]

    def test_verify_installed(self) -> None:
        """Test verifying installed configuration."""
        installer = VibeSOPInstaller()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Install first
            install_result = installer.install("claude-code", Path(tmpdir))
            assert install_result["success"]

            # Verify
            verify_result = installer.verify("claude-code", Path(tmpdir))

            assert verify_result["installed"]
            assert verify_result["config_valid"]
            assert len(verify_result["issues"]) == 0
            assert len(verify_result["hooks_installed"]) > 0

    def test_verify_not_installed(self) -> None:
        """Test verifying when not installed."""
        installer = VibeSOPInstaller()

        with tempfile.TemporaryDirectory() as tmpdir:
            verify_result = installer.verify("claude-code", Path(tmpdir))

            assert not verify_result["installed"]
            assert not verify_result["config_valid"]
            assert len(verify_result["issues"]) > 0

    def test_verify_unknown_platform(self) -> None:
        """Test verifying unknown platform."""
        installer = VibeSOPInstaller()

        verify_result = installer.verify("unknown-platform")

        assert not verify_result["installed"]
        assert "Unknown platform" in verify_result["issues"][0]

    def test_is_configured(self) -> None:
        """Test _is_configured method."""
        installer = VibeSOPInstaller()

        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)

            # Not configured initially
            assert not installer._is_configured(config_dir)

            # Create config file
            (config_dir / "CLAUDE.md").write_text("# Test", encoding="utf-8")

            # Now configured
            assert installer._is_configured(config_dir)

    def test_host_native_config_is_not_vibesop_configured(self) -> None:
        """Stock host configs must not skip VibeSOP hook deploy.

        Kimi/Grok ship config.toml; Pi ships settings.json. Those files
        are not VibeSOP markers (docs/dev/platform-invariants.md).
        """
        installer = VibeSOPInstaller()
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            (config_dir / "config.toml").write_text('[cli]\ninstaller = "npm"\n', encoding="utf-8")
            (config_dir / "settings.json").write_text("{}", encoding="utf-8")
            assert not installer._is_configured(config_dir, "grok-build")
            assert not installer._is_configured(config_dir, "kimi-cli")
            assert not installer._is_configured(config_dir, "pi")
            (config_dir / "hooks").mkdir()
            (config_dir / "hooks" / "vibesop-route.json").write_text("{}", encoding="utf-8")
            assert installer._is_configured(config_dir, "grok-build")
            (config_dir / "hooks" / "vibesop-route.sh").write_text("# hook\n", encoding="utf-8")
            assert installer._is_configured(config_dir, "kimi-cli")

    def test_verify_config_files(self) -> None:
        """Test _verify_config_files method."""
        installer = VibeSOPInstaller()

        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)

            # No files - should have issues
            issues = installer._verify_config_files("claude-code", config_dir)
            assert len(issues) > 0

            # Create CLAUDE.md without VibeSOP section
            (config_dir / "CLAUDE.md").write_text("# Test", encoding="utf-8")
            issues = installer._verify_config_files("claude-code", config_dir)
            assert len(issues) > 0
            assert "missing VibeSOP configuration" in issues[0]

            # Create proper CLAUDE.md
            (config_dir / "CLAUDE.md").write_text("# VibeSOP Configuration", encoding="utf-8")
            issues = installer._verify_config_files("claude-code", config_dir)
            assert len(issues) == 0


class TestVibeSOPInstallerIntegration:
    """Integration tests for VibeSOPInstaller."""

    def test_full_lifecycle(self) -> None:
        """Test complete install-verify-uninstall lifecycle."""
        installer = VibeSOPInstaller()

        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)

            # Install
            install_result = installer.install("claude-code", config_dir)
            assert install_result["success"]

            # Verify
            verify_result = installer.verify("claude-code", config_dir)
            assert verify_result["installed"]

            # Uninstall
            uninstall_result = installer.uninstall("claude-code", config_dir)
            assert uninstall_result["success"]

            # Verify removal
            verify_result = installer.verify("claude-code", config_dir)
            assert not verify_result["installed"]

    def test_multiple_platforms(self) -> None:
        """Test installing multiple platforms."""
        installer = VibeSOPInstaller()

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            # Install Claude Code
            cc_dir = base_dir / "claude-code"
            cc_result = installer.install("claude-code", cc_dir)
            assert cc_result["success"]

            # Install OpenCode
            oc_dir = base_dir / "opencode"
            oc_result = installer.install("opencode", oc_dir)
            assert oc_result["success"]

            # Verify both
            cc_verify = installer.verify("claude-code", cc_dir)
            oc_verify = installer.verify("opencode", oc_dir)

            assert cc_verify["installed"]
            assert oc_verify["installed"]

    def test_reinstall_with_hooks(self) -> None:
        """Test reinstalling preserves hooks."""
        installer = VibeSOPInstaller()

        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)

            # Initial install
            installer.install("claude-code", config_dir)

            # Verify hooks installed
            verify1 = installer.verify("claude-code", config_dir)
            hooks1 = verify1["hooks_installed"]
            initial_hook_count = sum(1 for v in hooks1.values() if v)

            # Reinstall with force
            installer.install("claude-code", config_dir, force=True)

            # Verify hooks still present
            verify2 = installer.verify("claude-code", config_dir)
            hooks2 = verify2["hooks_installed"]
            final_hook_count = sum(1 for v in hooks2.values() if v)

            assert final_hook_count >= initial_hook_count
