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

        Removes all superpowers symlinks from each platform and deletes
        the unified installation directory.

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
            # Remove platform symlinks (all superpowers-* links)
            for platform, link_dir in self.SUPERPOWERS_PLATFORM_SYMLINK_PATHS.items():
                symlink_dir = link_dir.expanduser()
                if not symlink_dir.exists():
                    continue

                removed_count = 0
                for entry in symlink_dir.iterdir():
                    # Only remove superpowers symlinks
                    if entry.is_symlink() and entry.name.startswith(f"{self.SUPERPOWERS_REPO_NAME}-"):
                        try:
                            entry.unlink()
                            removed_count += 1
                        except OSError as e:
                            result["errors"].append(f"Failed to remove {entry.name}: {e}")

                if removed_count > 0:
                    result["symlinks_removed"].append(f"{platform} ({removed_count} links)")

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
            "skills_count": 0,
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

        # Count skills
        skills_dir = self._unified_path / "skills"
        if result["markers_present"] and skills_dir.exists():
            skill_count = 0
            for entry in skills_dir.iterdir():
                if entry.is_dir():
                    skill_count += 1
            result["skills_count"] = skill_count

        # Check symlinks for each platform
        for platform, link_dir in self.SUPERPOWERS_PLATFORM_SYMLINK_PATHS.items():
            symlink_dir = link_dir.expanduser()
            platform_links = {
                "directory_exists": symlink_dir.exists(),
                "superpowers_links": [],
                "total_count": 0,
            }

            if symlink_dir.exists():
                # Count superpowers symlinks
                for entry in symlink_dir.iterdir():
                    if entry.is_symlink() and entry.name.startswith(f"{self.SUPERPOWERS_REPO_NAME}-"):
                        platform_links["superpowers_links"].append(entry.name)
                        platform_links["total_count"] += 1

            result["symlinks"][platform] = platform_links

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
        # Check for superpowers-specific marker files
        # superpowers has a skills directory with subdirectories
        skills_dir = self._unified_path / "skills"
        return (
            self._unified_path.exists()
            and skills_dir.exists()
            and any(skills_dir.iterdir())  # At least one skill subdirectory
        )

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
        """Create symlinks for each skill in a platform.

        Creates individual symlinks for each skill subdirectory,
        following the pattern: superpowers-{skill_name}

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
            link_dir = self.SUPERPOWERS_PLATFORM_SYMLINK_PATHS[platform].expanduser()
            skills_dir = self._unified_path / "skills"

            # Create parent directory
            link_dir.mkdir(parents=True, exist_ok=True)

            # Check if skills directory exists
            if not skills_dir.exists():
                progress.warning(f"Skills directory not found: {skills_dir}")
                return False

            # Get all skill subdirectories
            skill_entries = []
            for entry in skills_dir.iterdir():
                if entry.is_dir():
                    skill_entries.append(entry)

            if not skill_entries:
                progress.warning(f"No skills found in superpowers skills directory")
                return False

            created = 0
            skipped = 0

            # Create individual symlink for each skill
            for skill_path in skill_entries:
                skill_name = skill_path.name
                link_name = f"{self.SUPERPOWERS_REPO_NAME}-{skill_name}"
                link_path = link_dir / link_name

                # Check if already correctly linked
                if link_path.is_symlink():
                    try:
                        if link_path.resolve() == skill_path:
                            skipped += 1
                            continue
                    except OSError:
                        pass

                # Skip if exists but not a symlink
                if link_path.exists() and not link_path.is_symlink():
                    progress.warning(f"Skipping {link_name}: already exists")
                    continue

                # Remove old symlink if present
                if link_path.is_symlink():
                    link_path.unlink()

                # Create symlink
                try:
                    link_path.symlink_to(skill_path)
                    created += 1
                except OSError as e:
                    progress.warning(f"Failed to create {link_name}: {e}")

            progress.success(f"{platform}: {created} created, {skipped} up to date")
            return created > 0

        except Exception as e:
            progress.error(f"Failed to create symlinks for {platform}: {e}")
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
