"""Tests for atomic file writer."""

import tempfile
from pathlib import Path

import pytest

from vibesop.utils.atomic_writer import (
    AtomicWriteError,
    AtomicWriter,
    atomic_open,
    write_bytes,
    write_text,
)


class TestAtomicWriter:
    """Test AtomicWriter functionality."""

    def test_write_text_basic(self) -> None:
        """Test basic text writing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = AtomicWriter()
            path = Path(tmpdir) / "test.txt"

            writer.write_text(path, "Hello, World!")

            assert path.exists()
            assert path.read_text() == "Hello, World!"

    def test_write_text_with_encoding(self) -> None:
        """Test text writing with encoding."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = AtomicWriter()
            path = Path(tmpdir) / "test_utf8.txt"

            content = "你好, 世界!"
            writer.write_text(path, content, encoding="utf-8")

            assert path.read_text(encoding="utf-8") == content

    def test_write_bytes(self) -> None:
        """Test bytes writing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = AtomicWriter()
            path = Path(tmpdir) / "test.bin"

            content = b"\x00\x01\x02\x03"
            writer.write_bytes(path, content)

            assert path.read_bytes() == content

    def test_write_creates_parent_dirs(self) -> None:
        """Test that write creates parent directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = AtomicWriter()
            path = Path(tmpdir) / "deep" / "nested" / "test.txt"

            writer.write_text(path, "content")

            assert path.exists()
            assert path.read_text() == "content"

    def test_write_overwrites_existing(self) -> None:
        """Test that write overwrites existing file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = AtomicWriter()
            path = Path(tmpdir) / "test.txt"

            # Write initial content
            writer.write_text(path, "original")
            assert path.read_text() == "original"

            # Overwrite
            writer.write_text(path, "new content")
            assert path.read_text() == "new content"

    def test_atomic_open_context_manager(self) -> None:
        """Test atomic_open context manager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.txt"

            with atomic_open(path, "w") as f:
                f.write("Line 1\n")
                f.write("Line 2\n")

            assert path.exists()
            assert path.read_text() == "Line 1\nLine 2\n"

    def test_atomic_open_with_bytes(self) -> None:
        """Test atomic_open with binary mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.bin"

            with atomic_open(path, "wb") as f:
                f.write(b"\x00\x01\x02")

            assert path.read_bytes() == b"\x00\x01\x02"

    def test_write_text_convenience_function(self) -> None:
        """Test write_text convenience function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.txt"

            write_text(path, "convenience")

            assert path.read_text() == "convenience"

    def test_write_bytes_convenience_function(self) -> None:
        """Test write_bytes convenience function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.bin"

            write_bytes(path, b"\xff\xfe")

            assert path.read_bytes() == b"\xff\xfe"

    def test_cleanup_on_error(self) -> None:
        """Test that temp file is cleaned up on error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = AtomicWriter(temp_dir=Path(tmpdir) / "temp")
            path = Path(tmpdir) / "test.txt"

            # Write some content first
            path.write_text("existing")

            # Try to overwrite with invalid unicode that will cause error
            with pytest.raises(AtomicWriteError), writer.atomic_open(path, "w", encoding="utf-8") as f:
                # Using atomic_open with invalid content
                f.write("valid")
                # Force an error
                raise ValueError("Simulated error")

            # Original content should be preserved
            assert path.read_text() == "existing"

            # Temp file should be cleaned up
            temp_files = list((Path(tmpdir) / "temp").glob("*.tmp"))
            assert len(temp_files) == 0

    def test_custom_temp_dir(self) -> None:
        """Test AtomicWriter with custom temp directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_dir = Path(tmpdir) / "custom_temp"
            writer = AtomicWriter(temp_dir=temp_dir)
            path = Path(tmpdir) / "output.txt"

            writer.write_text(path, "custom temp")

            assert path.exists()
            assert path.read_text() == "custom temp"

    def test_large_file(self) -> None:
        """Test writing a large file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = AtomicWriter()
            path = Path(tmpdir) / "large.txt"

            # Create 1MB content
            content = "x" * (1024 * 1024)
            writer.write_text(path, content)

            assert path.read_text() == content
            assert len(path.read_bytes()) == 1024 * 1024

    def test_multiline_text(self) -> None:
        """Test writing multiline text."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = AtomicWriter()
            path = Path(tmpdir) / "multiline.txt"

            content = """Line 1
Line 2
Line 3
"""
            writer.write_text(path, content)

            assert path.read_text() == content

    def test_empty_content(self) -> None:
        """Test writing empty content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = AtomicWriter()
            path = Path(tmpdir) / "empty.txt"

            writer.write_text(path, "")

            assert path.exists()
            assert path.read_text() == ""
