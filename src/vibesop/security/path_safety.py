"""Path safety utilities for preventing path traversal attacks.

This module provides the PathSafety class that validates file paths
to prevent directory traversal and other path-based attacks.
"""

from pathlib import Path
from typing import Final

from vibesop.security.exceptions import PathOverlapError, PathTraversalError


class PathSafety:
    """Path safety validator for preventing path traversal attacks.

    Provides methods to validate file paths and ensure they don't
    escape designated directories or overlap with protected paths.

    Example:
        >>> safety = PathSafety()
        >>> safe_path = safety.ensure_safe_output_path("output.txt", Path("/tmp/work"))
        >>> # Raises PathTraversalError for "../../../etc/passwd"
    """

    # Maximum number of path components to prevent excessive nesting
    MAX_DEPTH: Final[int] = 50

    # Maximum path length to prevent potential issues
    MAX_PATH_LENGTH: Final[int] = 4096  # Linux PATH_MAX

    def __init__(
        self,
        max_depth: int = MAX_DEPTH,
        max_path_length: int = MAX_PATH_LENGTH,
    ) -> None:
        """Initialize the path safety validator.

        Args:
            max_depth: Maximum allowed path depth
            max_path_length: Maximum allowed path length
        """
        self.max_depth = max_depth
        self.max_path_length = max_path_length

    def ensure_safe_output_path(
        self,
        path: Path | str,
        base_dir: Path | str,
        create_parents: bool = False,
    ) -> Path:
        """Ensure an output path is safe and within base directory.

        This method validates that:
        1. The path doesn't escape the base directory (no traversal)
        2. The path length is within limits
        3. The path depth is within limits

        Args:
            path: Path to validate
            base_dir: Base directory that contains the output
            create_parents: Whether to create parent directories

        Returns:
            Resolved safe path

        Raises:
            PathTraversalError: If path attempts to escape base directory
            ValueError: If path exceeds limits
        """
        path = Path(path)
        base_dir = Path(base_dir).resolve()

        # Resolve to absolute path
        resolved = self._resolve_path(path, base_dir)

        # Validate path length
        if len(str(resolved)) > self.max_path_length:
            msg = f"Path length exceeds maximum: {len(str(resolved))} > {self.max_path_length}"
            raise ValueError(msg)

        # Validate path depth
        depth = len(resolved.parts)
        if depth > self.max_depth:
            msg = f"Path depth exceeds maximum: {depth} > {self.max_depth}"
            raise ValueError(msg)

        # Ensure path is within base directory
        if not self.check_traversal(resolved, base_dir):
            msg = f"Path traversal detected: {path} attempts to escape {base_dir}"
            raise PathTraversalError(
                message=msg,
                path=str(path),
                base_dir=str(base_dir),
            )

        # Create parent directories if requested
        if create_parents:
            resolved.parent.mkdir(parents=True, exist_ok=True)

        return resolved

    def check_traversal(self, path: Path | str, base_dir: Path | str) -> bool:
        """Check if a path attempts to traverse outside base directory.

        Args:
            path: Path to check (relative paths are treated as relative to base_dir)
            base_dir: Base directory

        Returns:
            True if path is safe (within base_dir), False otherwise
        """
        path_obj = Path(path)
        base_dir = Path(base_dir).resolve()

        # Construct the full path
        if path_obj.is_absolute():
            full_path = path_obj
        else:
            # Join with base directory
            full_path = base_dir / path_obj

        # Normalize the path (resolve .. and . components)
        # Use resolve() but be aware it follows symlinks
        try:
            resolved = full_path.resolve()
        except OSError:
            # If resolve fails, use strict=False to handle non-existent paths
            resolved = full_path.resolve(strict=False)

        # Check if resolved path is within base_dir using relative_to
        try:
            resolved.relative_to(base_dir)
            return True  # Path is within base_dir
        except ValueError:
            return False  # Path escapes base_dir

    def check_overlap(
        self,
        path1: Path | str,
        path2: Path | str,
        require_exact: bool = False,
    ) -> bool:
        """Check if two paths overlap or one is contained in the other.

        Args:
            path1: First path
            path2: Second path
            require_exact: If True, only return True for exact overlap

        Returns:
            True if paths overlap, False otherwise
        """
        path1 = Path(path1).resolve()
        path2 = Path(path2).resolve()

        # Check exact match first
        if path1 == path2:
            return True

        if require_exact:
            return False

        # Check if one is parent of the other
        try:
            path1.relative_to(path2)
            return True  # path1 is inside path2
        except ValueError:
            pass

        try:
            path2.relative_to(path1)
            return True  # path2 is inside path1
        except ValueError:
            pass

        return False

    def verify_writable(self, path: Path | str) -> bool:
        """Verify if a path is writable.

        This checks if:
        1. The path exists and is writable, OR
        2. The parent directory exists and is writable

        Args:
            path: Path to check

        Returns:
            True if writable, False otherwise
        """
        path = Path(path).resolve()

        # If path exists, check if it's writable
        if path.exists():
            return os.access(str(path), os.W_OK)

        # Otherwise, check if parent directory is writable
        if path.parent.exists():
            return os.access(str(path.parent), os.W_OK)

        # Parent doesn't exist
        return False

    def ensure_no_overlap(
        self,
        output_path: Path | str,
        protected_paths: list[Path | str],
    ) -> None:
        """Ensure output path doesn't overlap with protected paths.

        Args:
            output_path: Output path to check
            protected_paths: List of protected paths

        Raises:
            PathOverlapError: If overlap detected
        """
        output_path = Path(output_path).resolve()

        for protected in protected_paths:
            protected = Path(protected).resolve()

            if self.check_overlap(output_path, protected):
                msg = (
                    f"Output path overlaps with protected path: {output_path} overlaps {protected}"
                )
                raise PathOverlapError(
                    message=msg,
                    path1=str(output_path),
                    path2=str(protected),
                )

    def _resolve_path(self, path: Path, base: Path) -> Path:
        """Resolve a path relative to a base directory.

        Args:
            path: Path to resolve
            base: Base directory

        Returns:
            Resolved absolute path
        """
        # If path is absolute, use it directly
        if path.is_absolute():
            return path.resolve()

        # Otherwise, resolve relative to base
        return (base / path).resolve()

    def validate_filename(self, filename: str) -> bool:
        """Validate a filename is safe (no path separators).

        Args:
            filename: Filename to validate

        Returns:
            True if safe, False otherwise

        Raises:
            ValueError: If filename contains path separators or is empty
        """
        if not filename:
            msg = "Filename cannot be empty"
            raise ValueError(msg)

        # Check for path separators
        if "/" in filename or "\\" in filename:
            msg = f"Filename cannot contain path separators: {filename}"
            raise ValueError(msg)

        # Check for drive letters (Windows)
        if len(filename) >= 2 and filename[1] == ":":
            msg = f"Filename cannot contain drive letters: {filename}"
            raise ValueError(msg)

        # Check for suspicious patterns
        suspicious = ["..", "~", "$", "|", ";", "&", "<", ">", "*", "?"]
        if any(s in filename for s in suspicious):
            msg = f"Filename contains suspicious characters: {filename}"
            raise ValueError(msg)

        return True


# Import os for access checks
import os
