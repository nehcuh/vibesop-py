"""Superpowers skill pack installer.

This module handles installation of the Superpowers skill pack
from GitHub, including repository cloning and symlink setup.
"""

import subprocess
import shutil
from pathlib import Path
from typing import Optional, Dict, Any
import time

from vibesop.installer.base import BaseInstaller
from vibesop.cli import ProgressTracker


class SuperpowersInstaller(BaseInstaller):
    """Installer for Superpowers skill pack.

    Clones the Superpowers repository and sets up symlinks
    for different platforms.

    Example:
        >>> installer = SuperpowersInstaller()
        >>> success = installer.install()
        >>> print(f"Installed: {success}")
    """

    # Superpowers repository URLs
    SUPERPOWERS_REPO_URLS = [
        "https://github.com/obra/superpowers.git",
        "https://gitee.com/mirrors/superpowers.git",  # China mirror
    ]

    # Platform-specific paths
    SUPERPOWERS_PLATFORM_PATHS = {
        "unified": Path("~/.config/skills/superpowers"),  # Unified storage
    }

    SUPERPOWERS_PLATFORM_SYMLINK_PATHS = {
        "claude-code": Path("~/.config/claude/skills"),
        "opencode": Path("~/.config/opencode/skills"),
    }

    SUPERPOWERS_REPO_NAME = "superpowers"
    CLONE_TIMEOUT = 300  # 5 minutes
    MAX_RETRIES = 3

    def __init__(self) -> None:
        """Initialize the Superpowers installer."""
        self._unified_path = self.SUPERPOWERS_PLATFORM_PATHS["unified"].expanduser()

    def install(
        self,
        platform: Optional[str] = None,
        force: bool = False,
        progress: Optional[ProgressTracker] = None,
    ) -> Dict[str, Any]:
        """Install Superpowers skill pack.

        Args:
            platform: Target platform (None = all platforms)
            force: Force reinstall even if already installed
            progress: Optional progress tracker for UI updates

        Returns:
            Dictionary with installation results
        """
        result = {
            "success": False,
            "installed_path": str(self._unified_path),
            "symlinks_created": [],
            "errors": [],
            "warnings": [],
        }

        # Use default progress tracker if none provided
        if progress is None:
            progress = ProgressTracker("Installing Superpowers Skill Pack")
            progress.start()
            manage_progress = True
        else:
            manage_progress = False

        try:
            # Check if git is available
            progress.update(10, "Checking Git availability...")
            if not self._check_git_available():
                result["errors"].append("Git is not installed. Please install Git first.")
                progress.error("Git not found")
                return result

            # Check if already installed
            progress.update(20, "Checking existing installation...")
            if not force and self._is_installed():
                result["warnings"].append(f"Superpowers already installed at {self._unified_path}")
                result["success"] = True
                progress.warning("Already installed")
                if manage_progress:
                    progress.finish("Already installed")
                return result

            # Clone repository
            progress.update(30, "Cloning Superpowers repository...")
            clone_success = self._clone_repository(progress)

            if not clone_success:
                result["errors"].append("Failed to clone Superpowers repository")
                progress.error("Failed to clone repository")
                return result

            progress.update(70, "Creating platform symlinks...")
            # Create platform symlinks
            platforms = (
                [platform] if platform else list(self.SUPERPOWERS_PLATFORM_SYMLINK_PATHS.keys())
            )
            for plat in platforms:
                symlink_result = self._create_platform_symlink(plat, progress)
                if symlink_result:
                    result["symlinks_created"].append(plat)

            # Verify installation
            progress.update(90, "Verifying installation...")
            if self._verify_installation():
                result["success"] = True
                progress.success(f"Superpowers installed successfully at {self._unified_path}")
                if manage_progress:
                    progress.finish("Installation complete")
            else:
                result["errors"].append("Installation verification failed")
                progress.error("Verification failed")

        except Exception as e:
            result["errors"].append(f"Installation failed: {e}")
            progress.error(f"Installation failed: {e}")

        return result

    def uninstall(self) -> Dict[str, any]:
        """Uninstall Superpowers skill pack.

        Returns:
            Dictionary with uninstallation results
        """
        result = {
            "success": False,
            "removed_path": str(self._unified_path),
            "symlinks_removed": [],
            "errors": [],
        }

        try:
            # Remove platform symlinks
            for platform, link_path in self.SUPERPOWERS_PLATFORM_SYMLINK_PATHS.items():
                symlink_path = link_path.expanduser()
                if symlink_path.exists() and symlink_path.is_symlink():
                    symlink_path.unlink()
                    result["symlinks_removed"].append(platform)

            # Remove unified installation directory
            if self._unified_path.exists():
                shutil.rmtree(self._unified_path)
                result["success"] = True
            else:
                result["errors"].append(f"Superpowers not found at {self._unified_path}")

        except Exception as e:
            result["errors"].append(f"Uninstallation failed: {e}")

        return result

    def verify(self) -> Dict[str, any]:
        """Verify Superpowers installation.

        Returns:
            Dictionary with verification results
        """
        result = {
            "installed": False,
            "path": str(self._unified_path),
            "git_repo": False,
            "symlinks": {},
            "markers_present": False,
        }

        # Check if directory exists
        if not self._unified_path.exists():
            return result

        result["installed"] = True

        # Check if it's a git repository
        git_dir = self._unified_path / ".git"
        result["git_repo"] = git_dir.exists()

        # Check marker files
        result["markers_present"] = self._superpowers_markers_present()

        # Check symlinks
        for platform, link_path in self.SUPERPOWERS_PLATFORM_SYMLINK_PATHS.items():
            symlink_path = link_path.expanduser()
            result["symlinks"][platform] = {
                "exists": symlink_path.exists(),
                "is_symlink": symlink_path.is_symlink() if symlink_path.exists() else False,
                "target": str(symlink_path.resolve()) if symlink_path.exists() else None,
            }

        return result

    def _check_git_available(self) -> bool:
        """Check if git is available.

        Returns:
            True if git is installed, False otherwise
        """
        try:
            subprocess.run(
                ["git", "--version"],
                capture_output=True,
                check=True,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def _is_installed(self) -> bool:
        """Check if Superpowers is already installed.

        Returns:
            True if installed, False otherwise
        """
        return self._unified_path.exists() and self._superpowers_markers_present()

    def _superpowers_markers_present(self) -> bool:
        """Check if Superpowers marker files are present.

        Returns:
            True if markers are present, False otherwise
        """
        # Check for common Superpowers files/directories
        markers = [
            self._unified_path / "skills",
            self._unified_path / "README.md",
            self._unified_path / ".git",
        ]

        return all(marker.exists() for marker in markers)

    def _clone_repository(self, progress: ProgressTracker) -> bool:
        """Clone Superpowers repository.

        Args:
            progress: Progress tracker for updates

        Returns:
            True if successful, False otherwise
        """
        import shutil

        # Create parent directory
        self._unified_path.parent.mkdir(parents=True, exist_ok=True)

        # Try each repository URL
        for repo_url in self.SUPERPOWERS_REPO_URLS:
            for attempt in range(self.MAX_RETRIES):
                try:
                    progress.update(
                        30 + (attempt * 10),
                        f"Cloning from {repo_url} (attempt {attempt + 1}/{self.MAX_RETRIES})...",
                    )

                    # Remove existing directory if force reinstall
                    if self._unified_path.exists():
                        shutil.rmtree(self._unified_path)

                    # Clone repository
                    subprocess.run(
                        [
                            "git",
                            "clone",
                            "--depth",
                            "1",
                            repo_url,
                            str(self._unified_path),
                        ],
                        capture_output=True,
                        check=True,
                        timeout=self.CLONE_TIMEOUT,
                    )

                    progress.success(f"Successfully cloned from {repo_url}")
                    return True

                except subprocess.TimeoutExpired:
                    progress.error(f"Timeout cloning from {repo_url}")
                    break
                except subprocess.CalledProcessError as e:
                    progress.warning(f"Failed to clone from {repo_url}: {e}")
                    if attempt < self.MAX_RETRIES - 1:
                        wait_time = (attempt + 1) * 5
                        progress.update(30 + (attempt * 10), f"Retrying in {wait_time} seconds...")
                        time.sleep(wait_time)
                    continue
                except Exception as e:
                    progress.error(f"Unexpected error: {e}")
                    break

        return False

    def _create_platform_symlink(self, platform: str, progress: ProgressTracker) -> bool:
        """Create symlink for a platform.

        Args:
            platform: Platform name (claude-code, opencode)
            progress: Progress tracker for updates

        Returns:
            True if successful, False otherwise
        """
        if platform not in self.SUPERPOWERS_PLATFORM_SYMLINK_PATHS:
            progress.warning(f"Unknown platform: {platform}")
            return False

        try:
            link_path = self.SUPERPOWERS_PLATFORM_SYMLINK_PATHS[platform].expanduser()

            # Create parent directory
            link_path.parent.mkdir(parents=True, exist_ok=True)

            # Remove existing symlink if present
            if link_path.exists():
                if link_path.is_symlink():
                    link_path.unlink()
                else:
                    # Not a symlink, don't overwrite
                    progress.warning(f"Cannot overwrite existing directory: {link_path}")
                    return False

            # Create symlink
            link_path.symlink_to(self._unified_path)
            progress.success(f"Created symlink: {link_path} -> {self._unified_path}")
            return True

        except Exception as e:
            progress.error(f"Failed to create symlink for {platform}: {e}")
            return False

    def _verify_installation(self) -> bool:
        """Verify that Superpowers was installed correctly.

        Returns:
            True if verification passes, False otherwise
        """
        # Check if unified path exists
        if not self._unified_path.exists():
            return False

        # Check for marker files
        if not self._superpowers_markers_present():
            return False

        # Check if it's a git repository
        git_dir = self._unified_path / ".git"
        if not git_dir.exists():
            return False

        return True

    def get_status(self) -> Dict[str, any]:
        """Get current installation status.

        Returns:
            Dictionary with status information
        """
        verify_result = self.verify()

        return {
            "installed": verify_result["installed"],
            "version": self._get_version(),
            "path": str(verify_result["path"]),
            "git_repo": verify_result["git_repo"],
            "symlinks": verify_result["symlinks"],
            "marker_files": verify_result["markers_present"],
        }

    def _get_version(self) -> Optional[str]:
        """Get Superpowers version.

        Returns:
            Version string, or None if not available
        """
        try:
            # Try to get version from git
            result = subprocess.run(
                ["git", "describe", "--tags", "--always"],
                cwd=self._unified_path,
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                return result.stdout.strip()

        except Exception:
            pass

        return None
