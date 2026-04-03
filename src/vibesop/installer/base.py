"""Base class for installers.

This module provides the BaseInstaller class that all
installers should inherit from.
"""

from pathlib import Path
from typing import Dict, List, Optional
from abc import ABC, abstractmethod


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
        platform: Optional[str] = None,
        force: bool = False,
    ) -> Dict[str, any]:
        """Install the component.

        Args:
            platform: Target platform
            force: Force reinstall if already installed

        Returns:
            Dictionary with installation results
        """
        pass

    @abstractmethod
    def uninstall(self) -> Dict[str, any]:
        """Uninstall the component.

        Returns:
            Dictionary with uninstallation results
        """
        pass

    @abstractmethod
    def verify(self) -> Dict[str, any]:
        """Verify the installation.

        Returns:
            Dictionary with verification results
        """
        pass

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
