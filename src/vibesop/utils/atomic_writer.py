"""Atomic file writing utilities.

This module provides atomic file operations to prevent
data corruption during write operations.

Atomic writes ensure that either:
1. The write completes successfully, OR
2. The original file remains unchanged

This is critical for configuration files to prevent
corruption if the process is interrupted.
"""

from contextlib import contextmanager
from pathlib import Path


class AtomicWriteError(Exception):
    """Base exception for atomic write errors."""

    pass


class AtomicWriter:
    """Atomic file writer with rollback support.

    Uses temporary file + rename pattern for atomicity.
    The rename operation is atomic on POSIX systems.

    Example:
        >>> writer = AtomicWriter()
        >>> writer.write_text(path, "content")
        >>> writer.write_bytes(path, b"content")
        >>> with writer.atomic_open(path, "w") as f:
        ...     f.write("content")
    """

    def __init__(self, temp_dir: Path | None = None) -> None:
        """Initialize the atomic writer.

        Args:
            temp_dir: Directory for temporary files.
                     Defaults to system temp directory.
        """
        self._temp_dir = temp_dir

    def write_text(
        self,
        path: Path | str,
        content: str,
        encoding: str = "utf-8",
        mkdir: bool = True,
    ) -> None:
        """Atomically write text content to a file.

        Args:
            path: Target file path
            content: Text content to write
            encoding: File encoding (default: utf-8)
            mkdir: Create parent directories if needed (default: True)

        Raises:
            AtomicWriteError: If write operation fails
        """
        path = Path(path)
        tmp_path = self._get_temp_path(path)

        try:
            # Ensure parent directory exists
            if mkdir:
                tmp_path.parent.mkdir(parents=True, exist_ok=True)

            # Write to temporary file
            tmp_path.write_text(content, encoding=encoding)

            # Atomic rename
            self._atomic_replace(tmp_path, path)

        except Exception as e:
            # Clean up temp file on error
            tmp_path.unlink(missing_ok=True)
            raise AtomicWriteError(f"Failed to write {path}: {e}") from e

    def write_bytes(
        self,
        path: Path | str,
        content: bytes,
        mkdir: bool = True,
    ) -> None:
        """Atomically write bytes content to a file.

        Args:
            path: Target file path
            content: Bytes content to write
            mkdir: Create parent directories if needed (default: True)

        Raises:
            AtomicWriteError: If write operation fails
        """
        path = Path(path)
        tmp_path = self._get_temp_path(path)

        try:
            if mkdir:
                tmp_path.parent.mkdir(parents=True, exist_ok=True)

            tmp_path.write_bytes(content)
            self._atomic_replace(tmp_path, path)

        except Exception as e:
            tmp_path.unlink(missing_ok=True)
            raise AtomicWriteError(f"Failed to write {path}: {e}") from e

    @contextmanager
    def atomic_open(
        self,
        path: Path | str,
        mode: str = "w",
        encoding: str | None = "utf-8",
        mkdir: bool = True,
    ):
        """Context manager for atomic file operations.

        Args:
            path: Target file path
            mode: File open mode (default: "w")
            encoding: File encoding (default: utf-8), ignored for binary mode
            mkdir: Create parent directories if needed (default: True)

        Yields:
            File object for writing

        Example:
            >>> writer = AtomicWriter()
            >>> with writer.atomic_open(path, "w") as f:
            ...     f.write("content")
            # File is atomically written on context exit
        """
        path = Path(path)
        tmp_path = self._get_temp_path(path)

        if mkdir:
            tmp_path.parent.mkdir(parents=True, exist_ok=True)

        f = None
        try:
            # Don't pass encoding for binary mode
            open_kwargs = {}
            if "b" not in mode and encoding is not None:
                open_kwargs["encoding"] = encoding

            with tmp_path.open(mode, **open_kwargs) as f:
                yield f

            # Atomic rename
            self._atomic_replace(tmp_path, path)

        except Exception as e:
            tmp_path.unlink(missing_ok=True)
            raise AtomicWriteError(f"Failed to write {path}: {e}") from e

    def _get_temp_path(self, target_path: Path) -> Path:
        """Get a temporary file path for the target.

        Args:
            target_path: The target file path

        Returns:
            Path to temporary file
        """
        if self._temp_dir:
            self._temp_dir.mkdir(parents=True, exist_ok=True)
            # Use target filename in temp dir
            return self._temp_dir / f"{target_path.name}.tmp"

        # Use same directory as target for atomic rename
        target_path.parent.mkdir(parents=True, exist_ok=True)
        return target_path.with_suffix(target_path.suffix + ".tmp")

    def _atomic_replace(self, src: Path, dst: Path) -> None:
        """Atomically replace destination with source.

        Args:
            src: Source file path
            dst: Destination file path

        Note:
            Path.replace() is atomic on POSIX systems when
            src and dst are on the same filesystem.
        """
        # Ensure destination directory exists
        dst.parent.mkdir(parents=True, exist_ok=True)

        # Atomic rename
        src.replace(dst)


# Singleton instance for convenience
_default_writer = AtomicWriter()


def write_text(path: Path | str, content: str, encoding: str = "utf-8") -> None:
    """Convenience function for atomic text writing.

    Args:
        path: Target file path
        content: Text content to write
        encoding: File encoding (default: utf-8)
    """
    _default_writer.write_text(path, content, encoding)


def write_bytes(path: Path | str, content: bytes) -> None:
    """Convenience function for atomic bytes writing.

    Args:
        path: Target file path
        content: Bytes content to write
    """
    _default_writer.write_bytes(path, content)


@contextmanager
def atomic_open(path: Path | str, mode: str = "w", encoding: str = "utf-8"):
    """Context manager for atomic file operations.

    Args:
        path: Target file path
        mode: File open mode (default: "w")
        encoding: File encoding (default: utf-8)

    Yields:
        File object for writing
    """
    with _default_writer.atomic_open(path, mode, encoding) as f:
        yield f
