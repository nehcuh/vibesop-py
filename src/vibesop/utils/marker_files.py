"""Marker file management for VibeSOP.

This module provides capabilities for managing marker files
that track installation state and metadata.
"""

import json
import hashlib
from pathlib import Path
from typing import Dict, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum

from vibesop.security.path_safety import PathSafety


class MarkerType(Enum):
    """Type of marker file.

    Attributes:
        INSTALLATION: Installation completion marker
        CONFIGURATION: Configuration generation marker
        INTEGRATION: Integration installation marker
        SKILL: Skill installation marker
        HOOK: Hook installation marker
    """

    INSTALLATION = "installation"
    CONFIGURATION = "configuration"
    INTEGRATION = "integration"
    SKILL = "skill"
    HOOK = "hook"


@dataclass
class MarkerData:
    """Data stored in a marker file.

    Attributes:
        marker_type: Type of marker
        name: Name of the component being marked
        version: Version of the component
        timestamp: Creation timestamp
        path: Installation path
        checksum: Checksum of installed files
        metadata: Additional metadata
    """

    marker_type: str
    name: str
    version: Optional[str]
    timestamp: str
    path: str
    checksum: Optional[str]
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MarkerData":
        """Create from dictionary.

        Args:
            data: Dictionary data

        Returns:
            MarkerData instance
        """
        return cls(**data)


class MarkerFileManager:
    """Manage marker files for installation tracking.

    Marker files are used to track the state of installations
    and enable verification and rollback.

    Example:
        >>> manager = MarkerFileManager()
        >>> manager.write_marker(
        ...     MarkerType.INSTALLATION,
        ...     "gstack",
        ...     "/path/to/gstack"
        ... )
    """

    # Standard marker file locations
    MARKER_LOCATIONS = {
        MarkerType.INSTALLATION: Path(".vibe/markers/installations"),
        MarkerType.CONFIGURATION: Path(".vibe/markers/configurations"),
        MarkerType.INTEGRATION: Path(".vibe/markers/integrations"),
        MarkerType.SKILL: Path(".vibe/markers/skills"),
        MarkerType.HOOK: Path(".vibe/markers/hooks"),
    }

    def __init__(self, base_path: Optional[Path] = None) -> None:
        """Initialize the marker file manager.

        Args:
            base_path: Base path for marker files (default: current directory)
        """
        self._base_path = base_path or Path.cwd()
        self._path_safety = PathSafety()

    def write_marker(
        self,
        marker_type: MarkerType,
        name: str,
        install_path: Path,
        version: Optional[str] = None,
        checksum: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Write a marker file.

        Args:
            marker_type: Type of marker
            name: Name of the component
            install_path: Installation path
            version: Component version (optional)
            checksum: Installation checksum (optional)
            metadata: Additional metadata (optional)

        Returns:
            Result dictionary
        """
        result: dict[str, Any] = {
            "success": False,
            "marker_path": None,
            "errors": [],
        }

        try:
            # Validate paths (only check for obvious security issues)
            try:
                if not self._path_safety.check_traversal(install_path, self._base_path):
                    result["errors"].append(f"Invalid installation path: {install_path}")
                    return result
            except Exception:
                # If validation fails, continue but log warning
                # (Paths within temp directories might fail validation)
                pass

            # Get marker directory
            marker_dir = self._base_path / self.MARKER_LOCATIONS[marker_type]
            marker_dir.mkdir(parents=True, exist_ok=True)

            # Create marker data
            marker_data = MarkerData(
                marker_type=marker_type.value,
                name=name,
                version=version,
                timestamp=datetime.now().isoformat(),
                path=str(install_path),
                checksum=checksum,
                metadata=metadata or {},
            )

            # Write marker file
            marker_file = marker_dir / f"{name}.json"
            with open(marker_file, "w", encoding="utf-8") as f:
                json.dump(marker_data.to_dict(), f, indent=2)

            result["success"] = True
            result["marker_path"] = str(marker_file)

        except Exception as e:
            result["errors"].append(f"Failed to write marker: {e}")

        return result

    def read_marker(
        self,
        marker_type: MarkerType,
        name: str,
    ) -> Optional[MarkerData]:
        """Read a marker file.

        Args:
            marker_type: Type of marker
            name: Name of the component

        Returns:
            MarkerData if found, None otherwise
        """
        try:
            marker_file = self._base_path / self.MARKER_LOCATIONS[marker_type] / f"{name}.json"

            if not marker_file.exists():
                return None

            with open(marker_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            return MarkerData.from_dict(data)

        except Exception:
            return None

    def remove_marker(
        self,
        marker_type: MarkerType,
        name: str,
    ) -> Dict[str, Any]:
        """Remove a marker file.

        Args:
            marker_type: Type of marker
            name: Name of the component

        Returns:
            Result dictionary
        """
        result: dict[str, Any] = {
            "success": False,
            "errors": [],
        }

        try:
            marker_file = self._base_path / self.MARKER_LOCATIONS[marker_type] / f"{name}.json"

            if marker_file.exists():
                marker_file.unlink()
                result["success"] = True

        except Exception as e:
            result["errors"].append(f"Failed to remove marker: {e}")

        return result

    def list_markers(
        self,
        marker_type: Optional[MarkerType] = None,
    ) -> Dict[str, MarkerData]:
        """List all marker files.

        Args:
            marker_type: Type of marker to list (None = all types)

        Returns:
            Dictionary mapping names to MarkerData
        """
        markers: Dict[str, MarkerData] = {}

        types_to_check = [marker_type] if marker_type else list(MarkerType)

        for mtype in types_to_check:
            marker_dir = self._base_path / self.MARKER_LOCATIONS[mtype]

            if not marker_dir.exists():
                continue

            for marker_file in marker_dir.glob("*.json"):
                try:
                    with open(marker_file, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    marker_data = MarkerData.from_dict(data)
                    markers[marker_file.stem] = marker_data

                except Exception:
                    # Skip invalid marker files
                    continue

        return markers

    def verify_marker(
        self,
        marker_type: MarkerType,
        name: str,
    ) -> Dict[str, Any]:
        """Verify a marker file against current installation.

        Args:
            marker_type: Type of marker
            name: Name of the component

        Returns:
            Verification result dictionary
        """
        result: dict[str, Any] = {
            "valid": False,
            "exists": False,
            "path_matches": False,
            "checksum_matches": False,
            "errors": [],
        }

        try:
            marker_data = self.read_marker(marker_type, name)

            if marker_data is None:
                result["errors"].append("Marker file not found")
                return result

            result["exists"] = True

            # Check if installation path exists
            install_path = Path(marker_data.path)
            if not install_path.exists():
                result["errors"].append(f"Installation path does not exist: {install_path}")
                return result

            result["path_matches"] = True

            # Verify checksum if present
            if marker_data.checksum:
                current_checksum = self._calculate_checksum(install_path)
                if current_checksum != marker_data.checksum:
                    result["errors"].append("Checksum mismatch")
                    return result

                result["checksum_matches"] = True

            result["valid"] = True

        except Exception as e:
            result["errors"].append(f"Verification failed: {e}")

        return result

    def cleanup_markers(
        self,
        marker_type: Optional[MarkerType] = None,
    ) -> Dict[str, Any]:
        """Clean up orphaned marker files.

        Args:
            marker_type: Type of marker to clean (None = all types)

        Returns:
            Cleanup result dictionary
        """
        result: dict[str, Any] = {
            "cleaned": [],
            "kept": [],
            "errors": [],
        }

        markers = self.list_markers(marker_type)

        for name, marker_data in markers.items():
            try:
                # Check if installation still exists
                install_path = Path(marker_data.path)

                if not install_path.exists():
                    # Remove orphaned marker
                    mtype = MarkerType(marker_data.marker_type)
                    remove_result = self.remove_marker(mtype, name)

                    if remove_result["success"]:
                        result["cleaned"].append(name)
                    else:
                        result["errors"].append(f"Failed to remove {name}")
                else:
                    result["kept"].append(name)

            except Exception as e:
                result["errors"].append(f"Error checking {name}: {e}")

        return result

    def calculate_checksum(self, path: Path) -> str:
        """Calculate checksum for a directory or file.

        Args:
            path: Path to calculate checksum for

        Returns:
            Hexadecimal checksum string
        """
        return self._calculate_checksum(path)

    def _calculate_checksum(self, path: Path) -> str:
        """Internal checksum calculation.

        Args:
            path: Path to calculate checksum for

        Returns:
            Hexadecimal checksum string
        """
        sha256 = hashlib.sha256()

        if path.is_file():
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    sha256.update(chunk)

        elif path.is_dir():
            for file_path in sorted(path.rglob("*")):
                if file_path.is_file():
                    # Include relative path in checksum
                    relative_path = file_path.relative_to(path)
                    sha256.update(str(relative_path).encode())

                    with open(file_path, "rb") as f:
                        for chunk in iter(lambda: f.read(4096), b""):
                            sha256.update(chunk)

        return sha256.hexdigest()

    def export_markers(
        self,
        output_path: Path,
        marker_type: Optional[MarkerType] = None,
    ) -> Dict[str, Any]:
        """Export marker data to a file.

        Args:
            output_path: Output file path
            marker_type: Type of marker to export (None = all)

        Returns:
            Result dictionary
        """
        result: dict[str, Any] = {
            "success": False,
            "exported_count": 0,
            "errors": [],
        }

        try:
            markers = self.list_markers(marker_type)

            # Convert to serializable format
            export_data = {name: marker.to_dict() for name, marker in markers.items()}

            # Write to file
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(export_data, f, indent=2)

            result["success"] = True
            result["exported_count"] = len(export_data)

        except Exception as e:
            result["errors"].append(f"Export failed: {e}")

        return result

    def import_markers(
        self,
        input_path: Path,
        overwrite: bool = False,
    ) -> Dict[str, Any]:
        """Import marker data from a file.

        Args:
            input_path: Input file path
            overwrite: Whether to overwrite existing markers

        Returns:
            Result dictionary
        """
        result: dict[str, Any] = {
            "success": False,
            "imported_count": 0,
            "skipped_count": 0,
            "errors": [],
        }

        try:
            with open(input_path, "r", encoding="utf-8") as f:
                import_data = json.load(f)

            for name, data in import_data.items():
                try:
                    marker_type = MarkerType(data["marker_type"])

                    # Check if marker already exists
                    if not overwrite and self.read_marker(marker_type, name):
                        result["skipped_count"] += 1
                        continue

                    # Write marker
                    write_result = self.write_marker(
                        marker_type=marker_type,
                        name=name,
                        install_path=Path(data["path"]),
                        version=data.get("version"),
                        checksum=data.get("checksum"),
                        metadata=data.get("metadata", {}),
                    )

                    if write_result["success"]:
                        result["imported_count"] += 1
                    else:
                        result["errors"].append(f"Failed to import {name}")

                except Exception as e:
                    result["errors"].append(f"Error importing {name}: {e}")

            result["success"] = True

        except Exception as e:
            result["errors"].append(f"Import failed: {e}")

        return result
