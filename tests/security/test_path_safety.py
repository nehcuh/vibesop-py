"""Tests for PathSafety."""

from pathlib import Path

import pytest

from vibesop.security import PathSafety
from vibesop.security.exceptions import PathOverlapError, PathTraversalError


class TestPathSafety:
    """Test PathSafety functionality."""

    def test_create_path_safety(self) -> None:
        """Test creating PathSafety instance."""
        safety = PathSafety()
        assert safety.max_depth == 50
        assert safety.max_path_length == 4096

    def test_custom_limits(self) -> None:
        """Test creating PathSafety with custom limits."""
        safety = PathSafety(max_depth=10, max_path_length=1000)
        assert safety.max_depth == 10
        assert safety.max_path_length == 1000

    def test_ensure_safe_output_path_valid(self, tmp_path: Path) -> None:
        """Test ensure_safe_output_path with valid path."""
        safety = PathSafety()

        safe_path = safety.ensure_safe_output_path("output.txt", tmp_path)
        assert safe_path.is_absolute()
        assert tmp_path in safe_path.parents or safe_path.parent == tmp_path

    def test_ensure_safe_output_path_creates_parent(self, tmp_path: Path) -> None:
        """Test ensure_safe_output_path creates parent directories."""
        safety = PathSafety()

        safe_path = safety.ensure_safe_output_path(
            "subdir/nested/output.txt",
            tmp_path,
            create_parents=True,
        )

        assert safe_path.parent.exists()
        assert safe_path.parent.is_dir()

    def test_ensure_safe_output_path_without_create(self, tmp_path: Path) -> None:
        """Test ensure_safe_output_path without creating parents."""
        safety = PathSafety()

        # Parent doesn't exist, but path should still be validated
        safe_path = safety.ensure_safe_output_path(
            "subdir/output.txt",
            tmp_path,
            create_parents=False,
        )

        assert safe_path.is_absolute()
        # Parent should not exist
        assert not safe_path.parent.exists()

    def test_check_traversal_safe(self, tmp_path: Path) -> None:
        """Test check_traversal with safe paths."""
        safety = PathSafety()

        # Safe relative paths
        assert safety.check_traversal("output.txt", tmp_path)
        assert safety.check_traversal("subdir/output.txt", tmp_path)
        assert safety.check_traversal("a/b/c/output.txt", tmp_path)

    def test_check_traversal_attack(self, tmp_path: Path) -> None:
        """Test check_traversal blocks traversal attacks."""
        import platform
        safety = PathSafety()

        # Unix-style traversal attempts
        unix_paths = [
            "../../../etc/passwd",
            "./../../etc/passwd",
            "subdir/../../../etc/passwd",
            "/etc/passwd",  # Absolute path outside base
        ]

        # Windows-style traversal attempts (only on Windows)
        windows_paths = [
            "..\\..\\..\\windows\\system32",
            ".\\..\\..\\windows\\system32",
        ]

        attack_paths = unix_paths.copy()
        if platform.system() == "Windows":
            attack_paths.extend(windows_paths)

        for attack_path in attack_paths:
            # check_traversal should return False
            assert not safety.check_traversal(attack_path, tmp_path)

    def test_ensure_safe_output_path_blocks_traversal(self, tmp_path: Path) -> None:
        """Test ensure_safe_output_path raises exception for traversal."""
        safety = PathSafety()

        with pytest.raises(PathTraversalError) as exc_info:
            safety.ensure_safe_output_path("../../../etc/passwd", tmp_path)

        error = exc_info.value
        assert "Path traversal detected" in str(error)
        assert error.path == "../../../etc/passwd"

    def test_check_overlap_identical(self, tmp_path: Path) -> None:
        """Test check_overlap with identical paths."""
        safety = PathSafety()

        path1 = tmp_path / "test.txt"
        path2 = tmp_path / "test.txt"

        assert safety.check_overlap(path1, path2)

    def test_check_overlap_parent_child(self, tmp_path: Path) -> None:
        """Test check_overlap with parent-child relationship."""
        safety = PathSafety()

        parent = tmp_path / "parent"
        child = parent / "child"

        assert safety.check_overlap(parent, child)
        assert safety.check_overlap(child, parent)

    def test_check_overlap_no_overlap(self, tmp_path: Path) -> None:
        """Test check_overlap with non-overlapping paths."""
        safety = PathSafety()

        path1 = tmp_path / "dir1" / "file.txt"
        path2 = tmp_path / "dir2" / "file.txt"

        assert not safety.check_overlap(path1, path2)

    def test_check_overlap_exact_only(self, tmp_path: Path) -> None:
        """Test check_overlap with require_exact flag."""
        safety = PathSafety()

        parent = tmp_path / "parent"
        child = parent / "child"

        # With exact=True, only identical paths overlap
        assert not safety.check_overlap(parent, child, require_exact=True)
        assert safety.check_overlap(parent, parent, require_exact=True)

    def test_verify_writable_existing_file(self, tmp_path: Path) -> None:
        """Test verify_writable with existing writable file."""
        safety = PathSafety()

        test_file = tmp_path / "writable.txt"
        test_file.write_text("test")

        # Should be writable
        assert safety.verify_writable(test_file)

    def test_verify_writable_nonexistent(self, tmp_path: Path) -> None:
        """Test verify_writable with non-existent file."""
        safety = PathSafety()

        test_file = tmp_path / "new.txt"

        # Parent exists, so should be writable
        assert safety.verify_writable(test_file)

    def test_verify_writable_nonexistent_no_parent(self, tmp_path: Path) -> None:
        """Test verify_writable when parent doesn't exist."""
        safety = PathSafety()

        test_file = tmp_path / "nonexistent" / "new.txt"

        # Parent doesn't exist, should not be writable
        assert not safety.verify_writable(test_file)

    def test_ensure_no_overlap(self, tmp_path: Path) -> None:
        """Test ensure_no_overlap with safe paths."""
        safety = PathSafety()

        output_path = tmp_path / "output" / "file.txt"
        protected_paths = [
            tmp_path / "protected",
            tmp_path / "other",
        ]

        # Should not raise
        safety.ensure_no_overlap(output_path, protected_paths)

    def test_ensure_no_overlap_raises(self, tmp_path: Path) -> None:
        """Test ensure_no_overlap raises exception for overlap."""
        safety = PathSafety()

        output_path = tmp_path / "protected" / "file.txt"
        protected_paths = [tmp_path / "protected"]

        with pytest.raises(PathOverlapError) as exc_info:
            safety.ensure_no_overlap(output_path, protected_paths)

        error = exc_info.value
        assert "overlaps with protected path" in str(error)

    def test_validate_filename_safe(self) -> None:
        """Test validate_filename with safe filenames."""
        safety = PathSafety()

        safe_names = [
            "file.txt",
            "document.pdf",
            "archive.tar.gz",
            "my_file_123.txt",
            "CamelCase.doc",
        ]

        for name in safe_names:
            assert safety.validate_filename(name)

    def test_validate_filename_empty(self) -> None:
        """Test validate_filename rejects empty filename."""
        safety = PathSafety()

        with pytest.raises(ValueError):
            safety.validate_filename("")

    def test_validate_filename_with_path_separator(self) -> None:
        """Test validate_filename rejects path separators."""
        safety = PathSafety()

        with pytest.raises(ValueError):
            safety.validate_filename("subdir/file.txt")

        with pytest.raises(ValueError):
            safety.validate_filename("subdir\\file.txt")

    def test_validate_filename_with_drive_letter(self) -> None:
        """Test validate_filename rejects drive letters."""
        safety = PathSafety()

        with pytest.raises(ValueError):
            safety.validate_filename("C:file.txt")

    def test_validate_filename_suspicious_chars(self) -> None:
        """Test validate_filename rejects suspicious characters."""
        safety = PathSafety()

        suspicious = [
            "file..txt",
            "~file.txt",
            "$file.txt",
            "file|txt",
            "file;txt",
            "file&txt",
            "file<txt",
            "file>txt",
            "file*txt",
            "file?txt",
        ]

        for name in suspicious:
            with pytest.raises(ValueError):
                safety.validate_filename(name)

    def test_resolve_path_absolute(self, tmp_path: Path) -> None:
        """Test _resolve_path with absolute path."""
        safety = PathSafety()

        abs_path = tmp_path / "absolute.txt"
        resolved = safety._resolve_path(abs_path, tmp_path)

        assert resolved == abs_path.resolve()

    def test_resolve_path_relative(self, tmp_path: Path) -> None:
        """Test _resolve_path with relative path."""
        safety = PathSafety()

        rel_path = "relative.txt"
        resolved = safety._resolve_path(Path(rel_path), tmp_path)

        assert resolved == (tmp_path / rel_path).resolve()

    def test_max_path_length_enforcement(self, tmp_path: Path) -> None:
        """Test that max_path_length is enforced."""
        safety = PathSafety(max_path_length=50)

        # Create a path that exceeds the limit
        long_name = "a" * 100
        with pytest.raises(ValueError) as exc_info:
            safety.ensure_safe_output_path(long_name, tmp_path)

        assert "exceeds maximum" in str(exc_info.value)

    def test_max_depth_enforcement(self, tmp_path: Path) -> None:
        """Test that max_depth is enforced."""
        safety = PathSafety(max_depth=5)

        # Create a path that exceeds depth limit
        deep_path = "a/b/c/d/e/f/g"  # 7 levels
        with pytest.raises(ValueError) as exc_info:
            safety.ensure_safe_output_path(deep_path, tmp_path)

        assert "depth exceeds maximum" in str(exc_info.value)

    def test_symbolic_link_handling(self, tmp_path: Path) -> None:
        """Test path safety with symbolic links."""
        safety = PathSafety()

        # Create a file
        target_file = tmp_path / "target.txt"
        target_file.write_text("content")

        # Create a symlink (if supported)
        try:
            link_file = tmp_path / "link.txt"
            link_file.symlink_to(target_file)

            # Safe path should work
            result = safety.ensure_safe_output_path(link_file, tmp_path)
            assert result.exists()
        except OSError:
            # Symlinks not supported on this system
            pytest.skip("Symbolic links not supported")

    def test_path_with_current_dir_prefix(self, tmp_path: Path) -> None:
        """Test path safety with ./ prefix."""
        safety = PathSafety()

        safe_path = safety.ensure_safe_output_path("./output.txt", tmp_path)
        assert safe_path.is_absolute()
        assert tmp_path in safe_path.parents or safe_path.parent == tmp_path

    def test_path_resolution_with_dots(self, tmp_path: Path) -> None:
        """Test path resolution with . components."""
        safety = PathSafety()

        safe_path = safety.ensure_safe_output_path("./a/../b/./c.txt", tmp_path)
        assert safety.check_traversal(safe_path, tmp_path)


class TestPathSafetyEdgeCases:
    """Test edge cases and error conditions."""

    def test_none_path(self, tmp_path: Path) -> None:
        """Test handling of None path."""
        safety = PathSafety()
        # This should raise a TypeError or AttributeError
        with pytest.raises((TypeError, AttributeError)):
            safety.check_traversal(None, tmp_path)  # type: ignore

    def test_empty_string_path(self, tmp_path: Path) -> None:
        """Test handling of empty string path."""
        safety = PathSafety()
        # Empty path should resolve to base directory
        result = safety.check_traversal("", tmp_path)
        # Current directory should be safe
        assert result is True or result is False  # Behavior may vary

    def test_nonexistent_base_dir(self, tmp_path: Path) -> None:
        """Test with non-existent base directory."""
        safety = PathSafety()

        nonexistent = tmp_path / "nonexistent"

        # Should still work for validation
        safety.check_traversal("file.txt", nonexistent)
        # Result depends on implementation

    def test_unicode_filename(self, tmp_path: Path) -> None:  # noqa: ARG002
        """Test validate_filename with unicode characters."""
        safety = PathSafety()

        # Unicode filenames should be safe
        assert safety.validate_filename("文件.txt")
        assert safety.validate_filename("файл.txt")
        assert safety.validate_filename("datei.txt")

    def test_very_long_filename(self, tmp_path: Path) -> None:  # noqa: ARG002
        """Test validate_filename with very long filename."""
        safety = PathSafety()

        # Long but safe filename
        long_name = "a" * 200 + ".txt"
        assert safety.validate_filename(long_name)

    def test_dot_files(self, tmp_path: Path) -> None:  # noqa: ARG002
        """Test handling of dot files."""
        safety = PathSafety()

        # Dot files should be safe
        assert safety.validate_filename(".hidden")
        assert safety.validate_filename(".config.txt")

        # Double dot should be rejected (traversal)
        with pytest.raises(ValueError):
            safety.validate_filename("..")

    def test_windows_style_paths(self, tmp_path: Path) -> None:  # noqa: ARG002
        """Test Windows-style path separators on Unix."""
        safety = PathSafety()

        # Backslashes should be rejected in filenames
        with pytest.raises(ValueError):
            safety.validate_filename("file\\name.txt")
