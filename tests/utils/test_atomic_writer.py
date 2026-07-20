"""Tests for atomic_writer.py."""

from pathlib import Path

import pytest

from vibesop.utils.atomic_writer import (
    AtomicWriteError,
    AtomicWriter,
    write_bytes,
    write_text,
)


class TestAtomicWriter:
    """Tests for AtomicWriter class."""

    def test_write_text_atomic_success(self, tmp_path: Path):
        writer = AtomicWriter()
        target = tmp_path / "test.txt"
        writer.write_text(target, "hello world")
        assert target.exists()
        assert target.read_text() == "hello world"
        # Verify no temp file left behind
        assert not list(tmp_path.glob("*.tmp"))

    def test_write_bytes_atomic_success(self, tmp_path: Path):
        writer = AtomicWriter()
        target = tmp_path / "test.bin"
        writer.write_bytes(target, b"\x00\x01\x02")
        assert target.exists()
        assert target.read_bytes() == b"\x00\x01\x02"

    def test_overwrite_existing_file(self, tmp_path: Path):
        writer = AtomicWriter()
        target = tmp_path / "test.txt"
        writer.write_text(target, "original")
        writer.write_text(target, "updated")
        assert target.read_text() == "updated"

    def test_creates_parent_directories(self, tmp_path: Path):
        writer = AtomicWriter()
        target = tmp_path / "deep" / "nested" / "file.txt"
        writer.write_text(target, "content")
        assert target.exists()

    def test_mkdir_false_still_creates_dirs_via_temp_path(self, tmp_path: Path):
        # _get_temp_path always creates parent dirs; mkdir=False only
        # affects the temp file creation step after _get_temp_path
        writer = AtomicWriter()
        target = tmp_path / "deep" / "file.txt"
        writer.write_text(target, "content", mkdir=False)
        assert target.exists()
        assert target.read_text() == "content"

    def test_custom_temp_dir(self, tmp_path: Path):
        temp_dir = tmp_path / "custom_temp"
        writer = AtomicWriter(temp_dir=temp_dir)
        target = tmp_path / "output.txt"
        writer.write_text(target, "content")
        assert target.read_text() == "content"

    def test_atomic_open_context_manager(self, tmp_path: Path):
        writer = AtomicWriter()
        target = tmp_path / "test.txt"
        with writer.atomic_open(target, "w") as f:
            f.write("line1\n")
            f.write("line2\n")
        assert target.read_text() == "line1\nline2\n"

    def test_atomic_open_writes_multiple_lines(self, tmp_path: Path):
        writer = AtomicWriter()
        target = tmp_path / "test.txt"
        with writer.atomic_open(target, "w") as f:
            for i in range(10):
                f.write(f"line {i}\n")
        lines = target.read_text().strip().split("\n")
        assert len(lines) == 10

    def test_atomic_open_binary_mode(self, tmp_path: Path):
        writer = AtomicWriter()
        target = tmp_path / "test.bin"
        with writer.atomic_open(target, "wb") as f:
            f.write(b"\x00\x01\x02\x03")
        assert target.read_bytes() == b"\x00\x01\x02\x03"

    def test_exception_in_context_raises_atomic_error(self, tmp_path: Path):
        writer = AtomicWriter()
        target = tmp_path / "test.txt"

        class TestError(Exception):
            pass

        with pytest.raises(AtomicWriteError):
            with writer.atomic_open(target, "w") as f:
                f.write("partial")
                raise TestError("simulated failure")

        # File should NOT exist (temp cleaned up)
        assert not target.exists()

    def test_special_characters_in_content(self, tmp_path: Path):
        writer = AtomicWriter()
        target = tmp_path / "unicode.txt"
        content = "你好世界\nこんにちは\n🎉\nemoji: 😀\nnull: \x00"
        writer.write_text(target, content)
        assert target.read_text() == content

    def test_custom_encoding(self, tmp_path: Path):
        writer = AtomicWriter()
        target = tmp_path / "latin1.txt"
        content = "café"
        writer.write_text(target, content, encoding="latin-1")
        assert target.read_text(encoding="latin-1") == content

    def test_atomic_open_mkdir_false_uses_temp_path_dirs(self, tmp_path: Path):
        # _get_temp_path always creates parent dirs
        writer = AtomicWriter()
        target = tmp_path / "dir" / "test.txt"
        with writer.atomic_open(target, "w", mkdir=False) as f:
            f.write("content")
        assert target.read_text() == "content"

    def test_temp_file_cleanup_on_write_failure(self, tmp_path: Path, monkeypatch):
        """Temp file should be removed when write fails."""
        writer = AtomicWriter(temp_dir=tmp_path)
        target = tmp_path / "output.txt"

        # Force write failure by making the temp file unwritable after creation
        original_write = Path.write_text

        def failing_write(self, content, encoding=None):
            raise OSError("disk full")

        monkeypatch.setattr(Path, "write_text", failing_write)

        with pytest.raises(AtomicWriteError):
            writer.write_text(target, "content")

        # No temp files should remain
        tmps = list(tmp_path.glob("*.tmp"))
        assert len(tmps) == 0


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_write_text_convenience(self, tmp_path: Path):
        target = tmp_path / "test.txt"
        write_text(target, "hello")
        assert target.read_text() == "hello"

    def test_write_bytes_convenience(self, tmp_path: Path):
        target = tmp_path / "test.bin"
        write_bytes(target, b"\xff\xfe")
        assert target.read_bytes() == b"\xff\xfe"

    def test_atomic_open_convenience(self, tmp_path: Path):
        target = tmp_path / "test.txt"
        from vibesop.utils.atomic_writer import atomic_open

        with atomic_open(target, "w") as f:
            f.write("convenience")
        assert target.read_text() == "convenience"


class TestAtomicWriteError:
    """Tests for AtomicWriteError exception."""

    def test_error_str_representation(self):
        err = AtomicWriteError("write failed")
        assert "write failed" in str(err)

    def test_error_with_path(self, tmp_path: Path):
        target = tmp_path / "test.txt"
        err = AtomicWriteError("write failed")
        assert str(err) == "write failed"
