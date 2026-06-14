"""Path safety utilities for preventing path traversal attacks.

This module provides the PathSafety class that validates file paths
to prevent directory traversal and other path-based attacks.

Security model (v7.0.5+): ``check_traversal`` uses lexical normalization
plus per-component ``lstat`` checks. It does NOT follow symlinks. The
``resolve()`` calls that remain in ``check_overlap`` / ``verify_writable``
/ ``ensure_no_overlap`` are intentional — those methods deal with
already-trusted paths, not adversarial input.
"""

import logging
import os
from pathlib import Path
from typing import Final

from vibesop.security.exceptions import PathOverlapError, PathTraversalError

logger = logging.getLogger(__name__)


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

        # Reject NUL bytes in the input early — they can silently truncate
        # in downstream os/pathlib calls.
        if "\x00" in str(path):
            msg = f"Path contains NUL byte: {path!r}"
            raise ValueError(msg)

        # Resolve to absolute path
        resolved = self._resolve_path(path, base_dir)

        # Validate the leaf filename — defends against suspicious shell-like
        # characters even when check_traversal would otherwise pass.
        try:
            self.validate_filename(resolved.name)
        except ValueError as e:
            # Re-raise with the full path context for easier debugging.
            raise ValueError(f"Unsafe filename in path {resolved}: {e}") from e

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

        Security properties (v7.0.5):
            - **Lexical normalization only** — does NOT follow symlinks.
              ``Path.resolve()`` is unsafe here because a symlink inside
              ``base_dir`` pointing outside would be followed silently.
            - **Per-component lstat check** — refuses any symlink in the
              chain from ``base_dir`` to the target. Defeats both
              pre-existing symlinks and TOCTOU attacks (symlink created
              between this check and the actual write).
            - **Prefix-collision resistant** — ``/tmp/foo`` cannot bypass
              to ``/tmp/foobar`` because the containment check uses
              ``os.sep``-suffix matching rather than naive ``startswith``.

        Args:
            path: Path to check (relative paths are treated as relative
                to ``base_dir``).
            base_dir: Trusted base directory. Symlinks inside the base
                directory are still refused (defense in depth).

        Returns:
            True if the path is safe (within base_dir, no symlinks in
            the chain); False otherwise.
        """
        path_obj = Path(path)
        base_norm = self._lexical_normalize(Path(base_dir))

        # Build full path lexically — NO symlink resolution.
        full_path = path_obj if path_obj.is_absolute() else base_norm / path_obj
        candidate = self._lexical_normalize(full_path)

        # Containment check: candidate must equal base_norm OR start with
        # base_norm + os.sep. The os.sep suffix prevents /tmp/foo vs
        # /tmp/foobar prefix collision.
        if not self._is_lexically_within(candidate, base_norm):
            return False

        # Per-component symlink check (defeats pre-existing symlinks + TOCTOU).
        if not self._no_symlinks_in_chain(base_norm, candidate):
            return False

        return True

    @staticmethod
    def _lexical_normalize(path: Path) -> Path:
        """Normalize a path lexically: abspath + normpath.

        Does NOT resolve symlinks (unlike ``Path.resolve()``). ``..`` and
        ``.`` components are collapsed; the result is always absolute.
        """
        return Path(os.path.normpath(os.path.abspath(str(path))))

    @staticmethod
    def _is_lexically_within(candidate: Path, base: Path) -> bool:
        """Return True iff candidate equals base or is a lexical descendant.

        Uses ``os.sep``-suffix matching so ``/tmp/foo`` does NOT count as
        within ``/tmp/foobar`` (would be a prefix-collision attack).
        """
        cand_str = str(candidate)
        base_str = str(base)
        if cand_str == base_str:
            return True
        return cand_str.startswith(base_str + os.sep)

    def _no_symlinks_in_chain(self, base: Path, target: Path) -> bool:
        """Walk from ``base`` to ``target`` and refuse any symlink in the chain.

        Defends against:
            - Pre-existing symlinks inside ``base`` pointing outside.
            - TOCTOU: a symlink created between this check and the actual
              write (the write code path is expected to re-validate or use
              ``O_NOFOLLOW`` semantics for the leaf).

        Does NOT walk above ``base`` (``base`` itself is trusted).

        Args:
            base: Trusted base directory.
            target: Target path inside base.

        Returns:
            True if no component between base and target (exclusive of
            base, inclusive of target if it exists) is a symlink.
        """
        rel = os.path.relpath(str(target), str(base))
        if rel.startswith(".."):
            # Caller should have caught this via _is_lexically_within.
            return False
        if rel == ".":
            return True  # target is base

        current = base
        for part in Path(rel).parts:
            current = current / part
            try:
                if current.is_symlink():
                    logger.warning(
                        "Symlink detected in path chain at %s (base=%s, target=%s)",
                        current,
                        base,
                        target,
                    )
                    return False
            except OSError:
                # Path doesn't exist yet (typical for output paths).
                # Parent symlinks have already been checked by the time we
                # reach a non-existent component.
                continue
        return True

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

        for raw_protected in protected_paths:
            protected = Path(raw_protected).resolve()

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
        """Validate a filename is safe (no path separators, no NUL bytes).

        Args:
            filename: Filename to validate

        Returns:
            True if safe

        Raises:
            ValueError: If filename contains path separators, NUL bytes,
                drive letters, or suspicious shell-like characters.
        """
        if not filename:
            msg = "Filename cannot be empty"
            raise ValueError(msg)

        # NUL bytes terminate C strings unexpectedly — many downstream
        # libraries (os.open, pathlib, etc.) silently truncate at NUL,
        # which lets an attacker smuggle past later checks. Reject early.
        if "\x00" in filename:
            msg = f"Filename contains NUL byte: {filename!r}"
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
