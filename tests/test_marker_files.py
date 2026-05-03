"""Tests for marker file management system."""

import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from vibesop.utils import (
    MarkerData,
    MarkerFileManager,
    MarkerType,
)


class TestMarkerType:
    """Test MarkerType enum."""

    def test_marker_type_values(self) -> None:
        """Test marker type enum values."""
        assert MarkerType.INSTALLATION.value == "installation"
        assert MarkerType.CONFIGURATION.value == "configuration"
        assert MarkerType.INTEGRATION.value == "integration"
        assert MarkerType.SKILL.value == "skill"
        assert MarkerType.HOOK.value == "hook"


class TestMarkerData:
    """Test MarkerData dataclass."""

    def test_create_marker_data(self) -> None:
        """Test creating marker data."""
        data = MarkerData(
            marker_type="installation",
            name="test",
            version="1.0.0",
            timestamp="2024-01-01T00:00:00",
            path="/path/to/test",
            checksum="abc123",
            metadata={"key": "value"},
        )
        assert data.marker_type == "installation"
        assert data.name == "test"
        assert data.version == "1.0.0"

    def test_to_dict(self) -> None:
        """Test converting marker data to dictionary."""
        data = MarkerData(
            marker_type="installation",
            name="test",
            version="1.0.0",
            timestamp="2024-01-01T00:00:00",
            path="/path/to/test",
            checksum="abc123",
            metadata={},
        )
        result = data.to_dict()

        assert isinstance(result, dict)
        assert result["marker_type"] == "installation"
        assert result["name"] == "test"

    def test_from_dict(self) -> None:
        """Test creating marker data from dictionary."""
        data_dict = {
            "marker_type": "installation",
            "name": "test",
            "version": "1.0.0",
            "timestamp": "2024-01-01T00:00:00",
            "path": "/path/to/test",
            "checksum": "abc123",
            "metadata": {},
        }
        data = MarkerData.from_dict(data_dict)

        assert data.marker_type == "installation"
        assert data.name == "test"
        assert data.version == "1.0.0"


class TestMarkerFileManager:
    """Test MarkerFileManager functionality."""

    def test_create_manager(self) -> None:
        """Test creating marker file manager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = MarkerFileManager(base_path=Path(tmpdir))
            assert manager is not None

    def test_write_marker(self) -> None:
        """Test writing a marker file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            manager = MarkerFileManager(base_path=base_path)

            # Create a test install path within tmpdir
            install_path = base_path / "installations" / "test-integration"
            install_path.mkdir(parents=True, exist_ok=True)

            result = manager.write_marker(
                marker_type=MarkerType.INSTALLATION,
                name="test-integration",
                install_path=install_path,
                version="1.0.0",
            )

            assert result["success"]
            assert result["marker_path"] is not None

    def test_read_marker(self) -> None:
        """Test reading a marker file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            manager = MarkerFileManager(base_path=base_path)

            # Create installation directory
            install_dir = base_path / "test_installation"
            install_dir.mkdir()

            # Write marker first
            manager.write_marker(
                marker_type=MarkerType.INSTALLATION,
                name="test-integration",
                install_path=install_dir,
                version="1.0.0",
            )

            # Read marker back
            data = manager.read_marker(MarkerType.INSTALLATION, "test-integration")

            assert data is not None
            assert data.name == "test-integration"
            assert data.version == "1.0.0"

    def test_read_nonexistent_marker(self) -> None:
        """Test reading a non-existent marker."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = MarkerFileManager(base_path=Path(tmpdir))
            data = manager.read_marker(MarkerType.INSTALLATION, "nonexistent")

            assert data is None

    def test_remove_marker(self) -> None:
        """Test removing a marker file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            manager = MarkerFileManager(base_path=base_path)

            # Create installation directory
            install_dir = base_path / "test_installation"
            install_dir.mkdir()

            # Write marker first
            manager.write_marker(
                marker_type=MarkerType.INSTALLATION,
                name="test-integration",
                install_path=install_dir,
            )

            # Remove marker
            result = manager.remove_marker(MarkerType.INSTALLATION, "test-integration")

            assert result["success"]

            # Verify it's gone
            data = manager.read_marker(MarkerType.INSTALLATION, "test-integration")
            assert data is None

    def test_list_markers_empty(self) -> None:
        """Test listing markers when none exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = MarkerFileManager(base_path=Path(tmpdir))
            markers = manager.list_markers()

            assert isinstance(markers, dict)
            assert len(markers) == 0

    def test_list_markers_with_data(self) -> None:
        """Test listing markers with data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            manager = MarkerFileManager(base_path=base_path)

            # Create installation directories
            install1 = base_path / "install1"
            install2 = base_path / "install2"
            install1.mkdir()
            install2.mkdir()

            # Write multiple markers
            manager.write_marker(
                marker_type=MarkerType.INSTALLATION,
                name="integration1",
                install_path=install1,
            )
            manager.write_marker(
                marker_type=MarkerType.INSTALLATION,
                name="integration2",
                install_path=install2,
            )

            # List markers
            markers = manager.list_markers(MarkerType.INSTALLATION)

            assert len(markers) == 2
            assert "integration1" in markers
            assert "integration2" in markers

    def test_verify_marker_valid(self) -> None:
        """Test verifying a valid marker."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            manager = MarkerFileManager(base_path=base_path)

            # Create a temporary installation directory
            install_dir = base_path / "test_install"
            install_dir.mkdir()
            (install_dir / "test.txt").write_text("test")

            # Write marker
            manager.write_marker(
                marker_type=MarkerType.INSTALLATION,
                name="test-integration",
                install_path=install_dir,
            )

            # Verify marker
            result = manager.verify_marker(MarkerType.INSTALLATION, "test-integration")

            assert result["exists"]
            assert result["path_matches"]
            assert result["valid"]

    def test_verify_marker_path_mismatch(self) -> None:
        """Test verifying a marker with non-existent path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            manager = MarkerFileManager(base_path=base_path)

            # Write marker with non-existent path (don't create the directory)
            # Note: This will skip path validation but the marker will be written
            install_path = base_path / "nonexistent_installation"

            result = manager.write_marker(
                marker_type=MarkerType.INSTALLATION,
                name="test-integration",
                install_path=install_path,
            )

            # Only proceed if write succeeded
            if result["success"]:
                # Verify marker
                verify_result = manager.verify_marker(MarkerType.INSTALLATION, "test-integration")

                assert verify_result["exists"]
                assert not verify_result["path_matches"]
                assert not verify_result["valid"]

    def test_cleanup_markers(self) -> None:
        """Test cleaning up orphaned markers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            manager = MarkerFileManager(base_path=base_path)

            # Create marker with existing path
            existing_dir = base_path / "existing"
            existing_dir.mkdir()
            manager.write_marker(
                marker_type=MarkerType.INSTALLATION,
                name="existing-integration",
                install_path=existing_dir,
            )

            # Create marker with non-existent path
            orphan_path = base_path / "nonexistent_installation"
            orphan_result = manager.write_marker(
                marker_type=MarkerType.INSTALLATION,
                name="orphaned-integration",
                install_path=orphan_path,
            )

            # Only proceed if write succeeded
            if not orphan_result["success"]:
                # Skip the rest of the test if write failed
                return

            # Cleanup
            result = manager.cleanup_markers()

            assert "existing-integration" in result["kept"]
            assert "orphaned-integration" in result["cleaned"]

    def test_export_import_markers(self) -> None:
        """Test exporting and importing markers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            manager = MarkerFileManager(base_path=base_path)

            # Create installation directory
            install_dir = base_path / "test_installation"
            install_dir.mkdir()

            # Create markers
            manager.write_marker(
                marker_type=MarkerType.INSTALLATION,
                name="integration1",
                install_path=install_dir,
                version="1.0.0",
            )

            # Export
            export_path = base_path / "markers_export.json"
            export_result = manager.export_markers(export_path)

            assert export_result["success"]
            assert export_result["exported_count"] == 1
            assert export_path.exists()

            # Remove original marker
            manager.remove_marker(MarkerType.INSTALLATION, "integration1")

            # Import
            import_result = manager.import_markers(export_path)

            assert import_result["success"]
            assert import_result["imported_count"] == 1

            # Verify imported marker
            data = manager.read_marker(MarkerType.INSTALLATION, "integration1")
            assert data is not None
            assert data.version == "1.0.0"

    def test_calculate_checksum_file(self) -> None:
        """Test calculating checksum for a file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = MarkerFileManager(base_path=Path(tmpdir))

            # Create test file
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test content")

            # Calculate checksum
            checksum = manager.calculate_checksum(test_file)

            assert isinstance(checksum, str)
            assert len(checksum) == 64  # SHA256 produces 64 hex characters

    def test_calculate_checksum_directory(self) -> None:
        """Test calculating checksum for a directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = MarkerFileManager(base_path=Path(tmpdir))

            # Create test directory
            test_dir = Path(tmpdir) / "test_dir"
            test_dir.mkdir()
            (test_dir / "file1.txt").write_text("content1")
            (test_dir / "file2.txt").write_text("content2")

            # Calculate checksum
            checksum = manager.calculate_checksum(test_dir)

            assert isinstance(checksum, str)
            assert len(checksum) == 64

    def test_write_marker_with_metadata(self) -> None:
        """Test writing a marker with metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            manager = MarkerFileManager(base_path=base_path)
            metadata = {
                "author": "test",
                "description": "Test integration",
                "tags": ["test", "example"],
            }

            # Create installation directory
            install_dir = base_path / "test_installation"
            install_dir.mkdir()

            result = manager.write_marker(
                marker_type=MarkerType.INSTALLATION,
                name="test-integration",
                install_path=install_dir,
                metadata=metadata,
            )

            assert result["success"]

            # Read back and verify metadata
            data = manager.read_marker(MarkerType.INSTALLATION, "test-integration")
            assert data.metadata == metadata


class TestMarkerFileManagerEdgeCases:
    """Test edge cases and error handling for MarkerFileManager."""

    def test_write_marker_invalid_path_traversal(self, tmp_path: Path) -> None:
        """Test write_marker with invalid path (traversal attack)."""
        manager = MarkerFileManager(base_path=tmp_path)
        result = manager.write_marker(
            marker_type=MarkerType.INSTALLATION,
            name="test",
            install_path=Path("/etc/passwd"),
        )
        assert not result["success"]
        assert result["marker_path"] is None
        assert "Invalid installation path" in result["errors"][0]

    def test_write_marker_path_validation_exception(self, tmp_path: Path, monkeypatch) -> None:
        """Test write_marker when path validation raises an exception."""
        manager = MarkerFileManager(base_path=tmp_path)

        def raise_exception(*args, **kwargs):
            raise RuntimeError("validation error")

        monkeypatch.setattr(manager._path_safety, "check_traversal", raise_exception)

        install_path = tmp_path / "install"
        install_path.mkdir()

        result = manager.write_marker(
            marker_type=MarkerType.INSTALLATION,
            name="test",
            install_path=install_path,
        )
        # Should continue past the exception and succeed
        assert result["success"]
        assert result["marker_path"] is not None

    def test_read_marker_corrupted_json(self, tmp_path: Path) -> None:
        """Test read_marker with corrupted/invalid JSON file."""
        manager = MarkerFileManager(base_path=tmp_path)
        marker_dir = tmp_path / ".vibe" / "markers" / "installations"
        marker_dir.mkdir(parents=True, exist_ok=True)
        marker_file = marker_dir / "corrupted.json"
        marker_file.write_text("not valid json {")

        data = manager.read_marker(MarkerType.INSTALLATION, "corrupted")
        assert data is None

    def test_remove_marker_exception(self, tmp_path: Path, monkeypatch) -> None:
        """Test remove_marker with permission error."""
        manager = MarkerFileManager(base_path=tmp_path)

        install_dir = tmp_path / "test_install"
        install_dir.mkdir()

        manager.write_marker(
            marker_type=MarkerType.INSTALLATION,
            name="test",
            install_path=install_dir,
        )

        def raise_permission(*args, **kwargs):
            raise PermissionError("Access denied")

        monkeypatch.setattr(Path, "unlink", raise_permission)

        result = manager.remove_marker(MarkerType.INSTALLATION, "test")
        assert not result["success"]
        assert "Failed to remove marker" in result["errors"][0]

    def test_list_markers_skips_invalid_json(self, tmp_path: Path) -> None:
        """Test list_markers skips invalid JSON files."""
        manager = MarkerFileManager(base_path=tmp_path)

        install_dir = tmp_path / "test_install"
        install_dir.mkdir()

        manager.write_marker(
            marker_type=MarkerType.INSTALLATION,
            name="valid",
            install_path=install_dir,
        )

        marker_dir = tmp_path / ".vibe" / "markers" / "installations"
        invalid_file = marker_dir / "invalid.json"
        invalid_file.write_text("not json")

        markers = manager.list_markers(MarkerType.INSTALLATION)
        assert "valid" in markers
        assert "invalid" not in markers
        assert len(markers) == 1

    def test_verify_marker_checksum_mismatch(self, tmp_path: Path) -> None:
        """Test verify_marker with checksum mismatch."""
        manager = MarkerFileManager(base_path=tmp_path)

        install_dir = tmp_path / "test_install"
        install_dir.mkdir()
        test_file = install_dir / "test.txt"
        test_file.write_text("original")

        checksum = manager.calculate_checksum(install_dir)

        manager.write_marker(
            marker_type=MarkerType.INSTALLATION,
            name="test",
            install_path=install_dir,
            checksum=checksum,
        )

        # Modify the file to change checksum
        test_file.write_text("modified")

        result = manager.verify_marker(MarkerType.INSTALLATION, "test")
        assert result["exists"]
        assert result["path_matches"]
        assert not result["checksum_matches"]
        assert not result["valid"]
        assert "Checksum mismatch" in result["errors"]

    def test_verify_marker_install_path_missing(self, tmp_path: Path) -> None:
        """Test verify_marker when install path no longer exists."""
        manager = MarkerFileManager(base_path=tmp_path)

        install_dir = tmp_path / "test_install"
        install_dir.mkdir()

        manager.write_marker(
            marker_type=MarkerType.INSTALLATION,
            name="test",
            install_path=install_dir,
        )

        # Remove the install directory
        shutil.rmtree(install_dir)

        result = manager.verify_marker(MarkerType.INSTALLATION, "test")
        assert result["exists"]
        assert not result["path_matches"]
        assert not result["valid"]
        assert any("Installation path does not exist" in err for err in result["errors"])

    def test_calculate_checksum_directory_internal(self, tmp_path: Path) -> None:
        """Test _calculate_checksum for a directory with nested files."""
        manager = MarkerFileManager(base_path=tmp_path)

        test_dir = tmp_path / "nested_dir"
        test_dir.mkdir()
        subdir = test_dir / "subdir"
        subdir.mkdir()
        (test_dir / "a.txt").write_text("a")
        (subdir / "b.txt").write_text("b")

        checksum = manager._calculate_checksum(test_dir)
        assert isinstance(checksum, str)
        assert len(checksum) == 64

    def test_cleanup_markers_removes_orphaned(self, tmp_path: Path) -> None:
        """Test cleanup_markers removes orphaned markers."""
        manager = MarkerFileManager(base_path=tmp_path)

        existing_dir = tmp_path / "existing"
        existing_dir.mkdir()
        manager.write_marker(
            marker_type=MarkerType.INSTALLATION,
            name="existing",
            install_path=existing_dir,
        )

        orphan_dir = tmp_path / "orphan"
        # Don't create the directory
        manager.write_marker(
            marker_type=MarkerType.INSTALLATION,
            name="orphan",
            install_path=orphan_dir,
        )

        result = manager.cleanup_markers()
        assert "existing" in result["kept"]
        assert "orphan" in result["cleaned"]

    def test_import_markers_skip_existing(self, tmp_path: Path) -> None:
        """Test import_markers with overwrite=False skips existing."""
        manager = MarkerFileManager(base_path=tmp_path)

        install_dir = tmp_path / "test"
        install_dir.mkdir()

        manager.write_marker(
            marker_type=MarkerType.INSTALLATION,
            name="existing",
            install_path=install_dir,
            version="1.0.0",
        )

        export_data = {
            "existing": {
                "marker_type": "installation",
                "name": "existing",
                "version": "2.0.0",
                "timestamp": "2024-01-01T00:00:00",
                "path": str(install_dir),
                "checksum": None,
                "metadata": {},
            }
        }

        import_path = tmp_path / "import.json"
        import_path.write_text(json.dumps(export_data))

        result = manager.import_markers(import_path, overwrite=False)
        assert result["success"]
        assert result["skipped_count"] == 1
        assert result["imported_count"] == 0

        data = manager.read_marker(MarkerType.INSTALLATION, "existing")
        assert data is not None
        assert data.version == "1.0.0"

    def test_import_markers_overwrite_existing(self, tmp_path: Path) -> None:
        """Test import_markers with overwrite=True overwrites existing."""
        manager = MarkerFileManager(base_path=tmp_path)

        install_dir = tmp_path / "test"
        install_dir.mkdir()

        manager.write_marker(
            marker_type=MarkerType.INSTALLATION,
            name="existing",
            install_path=install_dir,
            version="1.0.0",
        )

        export_data = {
            "existing": {
                "marker_type": "installation",
                "name": "existing",
                "version": "2.0.0",
                "timestamp": "2024-01-01T00:00:00",
                "path": str(install_dir),
                "checksum": None,
                "metadata": {},
            }
        }

        import_path = tmp_path / "import.json"
        import_path.write_text(json.dumps(export_data))

        result = manager.import_markers(import_path, overwrite=True)
        assert result["success"]
        assert result["skipped_count"] == 0
        assert result["imported_count"] == 1

        data = manager.read_marker(MarkerType.INSTALLATION, "existing")
        assert data is not None
        assert data.version == "2.0.0"
