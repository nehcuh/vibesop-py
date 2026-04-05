"""VibeSOP installer.

This module provides installation and setup functionality
for VibeSOP configurations.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
import shutil


class VibeSOPInstaller:
    """VibeSOP configuration installer.

    Handles installation of VibeSOP configurations for
    different platforms (Claude Code, OpenCode, etc.).

    Example:
        >>> installer = VibeSOPInstaller()
        >>> result = installer.install("claude-code", Path("~/.claude"))
        >>> print(result["success"])
    """

    def __init__(self) -> None:
        """Initialize the installer."""
        self._platforms: dict[str, dict[str, Any]] = {
            "claude-code": {
                "config_dir": Path.home() / ".claude",
                "description": "Claude Code CLI",
            },
            "opencode": {
                "config_dir": Path.home() / ".opencode",
                "description": "OpenCode CLI",
            },
        }

    def install(
        self,
        platform: str,
        config_dir: Optional[Path] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Install VibeSOP configuration for a platform.

        Args:
            platform: Platform identifier
            config_dir: Configuration directory (uses default if None)
            force: Force overwrite existing configuration

        Returns:
            Dictionary with installation result
        """
        result: Dict[str, Any] = {
            "success": False,
            "platform": platform,
            "config_dir": None,
            "files_created": [],
            "errors": [],
            "warnings": [],
        }

        try:
            # Validate platform
            if platform not in self._platforms:
                result["errors"].append(f"Unknown platform: {platform}")
                return result

            # Get config directory
            target_dir: Path
            if config_dir is None:
                target_dir = self._platforms[platform]["config_dir"]
            else:
                target_dir = config_dir

            target_dir = target_dir.expanduser()
            result["config_dir"] = str(target_dir)

            # Check if already configured
            if not force and self._is_configured(target_dir):
                result["warnings"].append(
                    f"Configuration already exists in {target_dir}. Use --force to overwrite."
                )
                result["success"] = True  # Not a failure
                return result

            # Install configuration
            from vibesop.builder import ConfigRenderer, QuickBuilder
            from vibesop.hooks import HookInstaller
            from vibesop.core.skills import SkillStorage

            # Create manifest
            manifest = QuickBuilder.default(platform=platform)

            # Render configuration (CLAUDE.md, rules/, docs/) - NOT skills/
            renderer = ConfigRenderer(project_root=self._get_project_root())
            render_result = renderer.render_config_only(manifest, target_dir)

            if not render_result.success:
                result["errors"].extend(render_result.errors)
                return result

            result["files_created"] = [str(f) for f in render_result.files_created]

            # Install skills using central storage with symlinks
            storage = SkillStorage()
            installed, linked, messages = storage.sync_project_skills(
                project_root=self._get_project_root(),
                platform=platform,
                force=force,
            )
            result["skills_installed"] = installed
            result["skills_linked"] = linked
            result["skill_messages"] = messages

            # Install hooks
            hook_installer = HookInstaller()
            hook_results = hook_installer.install_hooks(platform, target_dir)

            installed_hooks = [name for name, status in hook_results.items() if status]
            failed_hooks = [name for name, status in hook_results.items() if not status]

            if installed_hooks:
                result["hooks_installed"] = installed_hooks

            if failed_hooks:
                result["warnings"].append(f"Failed to install hooks: {', '.join(failed_hooks)}")

            result["success"] = True

        except Exception as e:
            result["errors"].append(f"Installation failed: {e}")

        return result

    def uninstall(
        self,
        platform: str,
        config_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Uninstall VibeSOP configuration.

        Args:
            platform: Platform identifier
            config_dir: Configuration directory (uses default if None)

        Returns:
            Dictionary with uninstallation result
        """
        result: Dict[str, Any] = {
            "success": False,
            "platform": platform,
            "files_removed": [],
            "errors": [],
        }

        try:
            # Validate platform
            if platform not in self._platforms:
                result["errors"].append(f"Unknown platform: {platform}")
                return result

            # Get config directory
            target_dir: Path
            if config_dir is None:
                target_dir = self._platforms[platform]["config_dir"]
            else:
                target_dir = config_dir

            target_dir = target_dir.expanduser()

            # Uninstall hooks
            from vibesop.hooks import HookInstaller

            hook_installer = HookInstaller()
            hook_installer.uninstall_hooks(platform, target_dir)

            # Remove configuration files
            if not target_dir.exists():
                result["errors"].append(f"Configuration directory not found: {target_dir}")
                return result

            # Remove VibeSOP files (keeping user data)
            files_to_remove = [
                target_dir / "CLAUDE.md",
                target_dir / "config.yaml",
                target_dir / "settings.json",
                target_dir / "rules",
                target_dir / "docs",
                target_dir / "hooks",
            ]

            for file_path in files_to_remove:
                if file_path.exists():
                    if file_path.is_dir():
                        shutil.rmtree(file_path)
                    else:
                        file_path.unlink()
                    result["files_removed"].append(str(file_path))

            result["success"] = True

        except Exception as e:
            result["errors"].append(f"Uninstallation failed: {e}")

        return result

    def verify(
        self,
        platform: str,
        config_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Verify VibeSOP installation.

        Args:
            platform: Platform identifier
            config_dir: Configuration directory (uses default if None)

        Returns:
            Dictionary with verification results
        """
        result: Dict[str, Any] = {
            "platform": platform,
            "installed": False,
            "config_valid": False,
            "hooks_installed": {},
            "issues": [],
        }

        try:
            # Get config directory
            target_dir: Optional[Path] = None
            if config_dir is None:
                platform_info = self._platforms.get(platform)
                if platform_info is not None:
                    target_dir = platform_info.get("config_dir")
            else:
                target_dir = config_dir

            if not target_dir:
                result["issues"].append(f"Unknown platform: {platform}")
                return result

            target_dir = target_dir.expanduser()

            # Check if configured
            if not self._is_configured(target_dir):
                result["issues"].append(f"Not configured in {target_dir}")
                return result

            result["installed"] = True

            # Verify configuration files
            config_issues = self._verify_config_files(platform, target_dir)
            result["issues"].extend(config_issues)
            result["config_valid"] = len(config_issues) == 0

            # Verify hooks
            from vibesop.hooks import HookInstaller

            hook_installer = HookInstaller()
            hook_status = hook_installer.verify_hooks(platform, target_dir)
            result["hooks_installed"] = hook_status

        except Exception as e:
            result["issues"].append(f"Verification failed: {e}")

        return result

    def list_platforms(self) -> List[Dict[str, str]]:
        """List supported platforms.

        Returns:
            List of platform information dictionaries
        """
        platforms: List[Dict[str, str]] = []

        for name, config in self._platforms.items():
            platforms.append(
                {
                    "name": name,
                    "description": config["description"],
                    "config_dir": str(config["config_dir"]),
                }
            )

        return platforms

    def _get_project_root(self) -> Path:
        """Get the VibeSOP project root directory.

        Returns:
            Path to project root containing core/skills/
        """
        # Try to find project root by looking for core/ directory
        current = Path.cwd()
        for path in [current, current / "src", Path(__file__).parent.parent.parent]:
            if (path / "core" / "skills").exists():
                return path.resolve()
        return Path(".").resolve()

    def _is_configured(self, config_dir: Path) -> bool:
        """Check if platform is configured.

        Args:
            config_dir: Configuration directory

        Returns:
            True if configured, False otherwise
        """
        if not config_dir.exists():
            return False

        # Check for key configuration files
        key_files = [
            config_dir / "CLAUDE.md",
            config_dir / "config.yaml",
            config_dir / "settings.json",
        ]

        return any(f.exists() for f in key_files)

    def _verify_config_files(
        self,
        platform: str,
        config_dir: Path,
    ) -> List[str]:
        """Verify configuration files.

        Args:
            platform: Platform identifier
            config_dir: Configuration directory

        Returns:
            List of issue descriptions (empty if all OK)
        """
        issues: List[str] = []

        # Platform-specific verification
        if platform == "claude-code":
            # Check for CLAUDE.md
            claude_md = config_dir / "CLAUDE.md"
            if not claude_md.exists():
                issues.append("CLAUDE.md not found")
            else:
                # Check for key sections
                content = claude_md.read_text()
                if "# VibeSOP" not in content and "## VibeSOP" not in content:
                    issues.append("CLAUDE.md missing VibeSOP configuration")

        elif platform == "opencode":
            # Check for config.yaml
            config_yaml = config_dir / "config.yaml"
            if not config_yaml.exists():
                issues.append("config.yaml not found")

        return issues
