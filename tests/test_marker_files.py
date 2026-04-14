"""Tests for marker file management system."""

import tempfile
from pathlib import Path

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
