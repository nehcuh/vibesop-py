"""Base class for installers.

This module provides the BaseInstaller class that all
installers should inherit from.
"""

import shutil
import subprocess
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar


class BaseInstaller(ABC):
    """Abstract base class for installers.

    Provides common functionality for all installers.
    """

    def __init__(self) -> None:
        """Initialize the installer."""
        self._name = self.__class__.__name__

    @abstractmethod
    def install(
        self,
        platform: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Install the component.

        Args:
            platform: Target platform
            force: Force reinstall if already installed

        Returns:
            Dictionary with installation results
        """
        pass

        return {"status": "not_implemented"}

    @abstractmethod
    def uninstall(self) -> dict[str, Any]:
        """Uninstall the component.

        Returns:
            Dictionary with uninstallation results
        """
        pass
        return {"status": "not_implemented"}

    @abstractmethod
    def verify(self) -> dict[str, Any]:
        """Verify the installation.

        Returns:
            Dictionary with verification results
        """
        pass
        return {"status": "not_implemented"}

    def _ensure_directory(self, path: Path) -> None:
        """Ensure a directory exists, creating it if necessary.

        Args:
            path: Directory path
        """
        path.expanduser().mkdir(parents=True, exist_ok=True)

    def _remove_directory(self, path: Path) -> bool:
        """Remove a directory if it exists.

        Args:
            path: Directory path

        Returns:
            True if removed, False otherwise
        """
        try:
            expanded_path = path.expanduser()
            if expanded_path.exists():
                shutil.rmtree(expanded_path)
            return True
        except Exception:
            return False

    def _check_command_available(self, command: str) -> bool:
        """Check if a command is available.

        Args:
            command: Command to check

        Returns:
            True if available, False otherwise
        """
        try:
            subprocess.run(
                [command, "--version"],
                capture_output=True,
                check=True,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False


class GitBasedInstaller(BaseInstaller):
    """Base class for Git-based skill pack installers.

       Provides shared logic for cloning, symlink creation, verification,
       and version detection. Subclasses only need to define pack-specific
    configuration and marker detection.
    """

    repo_urls: list[str]
    repo_name: str
    unified_path: Path = Path()
    platform_symlink_paths: ClassVar[dict[str, Path]] = {}
    clone_timeout: int = 300
    max_retries: int = 3

    def __init__(self) -> None:
        super().__init__()

    @abstractmethod
    def _check_markers(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def _find_skill_entries(self) -> list[Path]:
        raise NotImplementedError

    def _count_skills(self) -> int:
        return 0

    def install(
        self,
        platform: str | None = None,
        force: bool = False,
        progress: Any | None = None,
    ) -> dict[str, Any]:
        from vibesop.cli import ProgressTracker

        result: dict[str, Any] = {
            "success": False,
            "installed_path": str(self.unified_path),
            "symlinks_created": [],
            "errors": [],
            "warnings": [],
        }

        if progress is None:
            progress = ProgressTracker(f"Installing {self.repo_name} Skill Pack")
            progress.start()
            manage_progress = True
        else:
            manage_progress = False

        try:
            progress.update(10, "Checking Git availability...")
            if not self._check_git_available():
                result["errors"].append("Git is not installed. Please install Git first.")
                progress.error("Git not found")
                return result

            progress.update(20, "Checking existing installation...")
            if not force and self._is_installed():
                result["warnings"].append(
                    f"{self.repo_name} already installed at {self.unified_path}"
                )
                result["success"] = True
                progress.warning("Already installed")
                if manage_progress:
                    progress.finish("Already installed")
                return result

            progress.update(30, f"Cloning {self.repo_name} repository...")
            clone_success = self._clone_repository(progress)

            if not clone_success:
                result["errors"].append(f"Failed to clone {self.repo_name} repository")
                progress.error("Failed to clone repository")
                return result

            progress.update(70, "Creating platform symlinks...")
            platforms = [platform] if platform else list(self.platform_symlink_paths.keys())
            for plat in platforms:
                symlink_result = self._create_platform_symlink(plat, progress)
                if symlink_result:
                    result["symlinks_created"].append(plat)

            progress.update(90, "Verifying installation...")
            if self._verify_installation():
                result["success"] = True
                progress.success(f"{self.repo_name} installed successfully at {self.unified_path}")
                if manage_progress:
                    progress.finish("Installation complete")
            else:
                result["errors"].append("Installation verification failed")
                progress.error("Verification failed")

        except Exception as e:
            result["errors"].append(f"Installation failed: {e}")
            progress.error(f"Installation failed: {e}")

        return result

    def uninstall(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "success": False,
            "removed_path": str(self.unified_path),
            "symlinks_removed": [],
            "errors": [],
        }

        try:
            for _platform, link_dir in self.platform_symlink_paths.items():
                symlink_dir = link_dir.expanduser()
                if not symlink_dir.exists():
                    continue

                removed_count = 0
                for entry in symlink_dir.iterdir():
                    if entry.is_symlink() and entry.name.startswith(f"{self.repo_name}-"):
                        try:
                            entry.unlink()
                            removed_count += 1
                        except OSError as e:
                            result["errors"].append(f"Failed to remove {entry.name}: {e}")

                if removed_count > 0:
                    result["symlinks_removed"].append(f"{_platform} ({removed_count} links)")

            if self.unified_path.exists():
                shutil.rmtree(self.unified_path)
                result["success"] = True
            else:
                result["errors"].append(f"{self.repo_name} not found at {self.unified_path}")

        except Exception as e:
            result["errors"].append(f"Uninstallation failed: {e}")

        return result

    def verify(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "installed": False,
            "path": str(self.unified_path),
            "git_repo": False,
            "symlinks": {},
            "markers_present": False,
            "skills_count": 0,
        }

        if not self.unified_path.exists():
            return result

        result["installed"] = True
        result["git_repo"] = (self.unified_path / ".git").exists()
        result["markers_present"] = self._check_markers()

        if result["markers_present"]:
            result["skills_count"] = self._count_skills()

        for platform, link_dir in self.platform_symlink_paths.items():
            symlink_dir = link_dir.expanduser()
            platform_links: dict[str, Any] = {
                "directory_exists": symlink_dir.exists(),
                "links": [],
                "total_count": 0,
            }

            if symlink_dir.exists():
                for entry in symlink_dir.iterdir():
                    if entry.is_symlink() and entry.name.startswith(f"{self.repo_name}-"):
                        platform_links["links"].append(entry.name)
                        platform_links["total_count"] += 1

            result["symlinks"][platform] = platform_links

        return result

    def _check_git_available(self) -> bool:
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
        return self.unified_path.exists() and self._check_markers()

    def _clone_repository(self, progress: Any) -> bool:
        self.unified_path.parent.mkdir(parents=True, exist_ok=True)

        for repo_url in self.repo_urls:
            for attempt in range(self.max_retries):
                try:
                    progress.update(
                        30 + (attempt * 10),
                        f"Cloning from {repo_url} (attempt {attempt + 1}/{self.max_retries})...",
                    )

                    if self.unified_path.exists():
                        shutil.rmtree(self.unified_path)

                    subprocess.run(
                        ["git", "clone", "--depth", "1", repo_url, str(self.unified_path)],
                        capture_output=True,
                        check=True,
                        timeout=self.clone_timeout,
                    )

                    progress.success(f"Successfully cloned from {repo_url}")
                    return True

                except subprocess.TimeoutExpired:
                    progress.error(f"Timeout cloning from {repo_url}")
                    break
                except subprocess.CalledProcessError as e:
                    progress.warning(f"Failed to clone from {repo_url}: {e}")
                    if attempt < self.max_retries - 1:
                        wait_time = (attempt + 1) * 5
                        progress.update(
                            30 + (attempt * 10),
                            f"Retrying in {wait_time} seconds...",
                        )
                        time.sleep(wait_time)
                    continue
                except Exception as e:
                    progress.error(f"Unexpected error: {e}")
                    break

        return False

    def _create_platform_symlink(self, platform: str, progress: Any) -> bool:
        if platform not in self.platform_symlink_paths:
            progress.warning(f"Unknown platform: {platform}")
            return False

        try:
            link_dir = self.platform_symlink_paths[platform].expanduser()
            skill_entries = self._find_skill_entries()

            if not skill_entries:
                progress.warning(f"No skills found in {self.repo_name} directory")
                return False

            link_dir.mkdir(parents=True, exist_ok=True)

            created = 0
            skipped = 0

            for skill_path in skill_entries:
                skill_name = skill_path.name
                link_name = f"{self.repo_name}-{skill_name}"
                link_path = link_dir / link_name

                if link_path.is_symlink():
                    try:
                        if link_path.resolve() == skill_path:
                            skipped += 1
                            continue
                    except OSError:
                        pass

                if link_path.exists() and not link_path.is_symlink():
                    progress.warning(f"Skipping {link_name}: already exists")
                    continue

                if link_path.is_symlink():
                    link_path.unlink()

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
        if not self.unified_path.exists():
            return False
        if not self._check_markers():
            return False
        return (self.unified_path / ".git").exists()

    def get_status(self) -> dict[str, Any]:
        verify_result = self.verify()
        return {
            "installed": verify_result["installed"],
            "version": self._get_version(),
            "path": verify_result["path"],
            "git_repo": verify_result["git_repo"],
            "symlinks": verify_result["symlinks"],
            "marker_files": verify_result["markers_present"],
        }

    def _get_version(self) -> str | None:
        try:
            result = subprocess.run(
                ["git", "describe", "--tags", "--always"],
                cwd=self.unified_path,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None
