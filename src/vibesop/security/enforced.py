# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportMissingTypeArgument=false, reportUnknownParameterType=false
"""Enforced security scanning for external inputs.

This module provides decorators and wrappers that enforce
security scanning on all external inputs.

This is a critical security measure - all external content
MUST be scanned before being used in the system.
"""

from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Any, TypeVar

from vibesop.security.exceptions import SecurityError
from vibesop.security.scanner import SecurityScanner

T = TypeVar("T")


class SecurityEnforcementError(SecurityError):
    """Raised when security enforcement fails."""

    pass


def require_safe_scan(
    scanner: SecurityScanner | None = None,
    on_unsafe: str = "raise",  # "raise", "return_none", "return_default"
) -> Callable:
    """Decorator that enforces security scanning on function results.

    Args:
        scanner: SecurityScanner instance (creates new if None)
        on_unsafe: What to do when scan fails:
                   - "raise": Raise SecurityEnforcementError (default)
                   - "return_none": Return None
                   - "return_default": Return default value from function

    Example:
        >>> @require_safe_scan()
        ... def load_config(path: Path) -> dict:
        ...     return json.loads(path.read_text())

        >>> # This will scan the config before returning
        >>> config = load_config(Path("config.json"))
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            result = func(*args, **kwargs)

            # Scan based on result type
            _scanner = scanner or SecurityScanner()

            if isinstance(result, str):
                scan_result = _scanner.scan(result)
                if not scan_result.safe:
                    if on_unsafe == "raise":
                        raise SecurityEnforcementError(
                            f"Unsafe content detected in {func.__name__}: {scan_result.threats}"
                        )
                    elif on_unsafe == "return_none":
                        return None  # type: ignore
                    elif on_unsafe == "return_default":
                        # Return default if function has one, else None
                        return getattr(func, "__default__", None)  # type: ignore

            elif isinstance(result, Path):
                scan_result = _scanner.scan_file(result)
                if not scan_result.safe:
                    if on_unsafe == "raise":
                        raise SecurityEnforcementError(
                            f"Unsafe file detected in {func.__name__}: {scan_result.threats}"
                        )
                    elif on_unsafe == "return_none":
                        return None  # type: ignore
                    elif on_unsafe == "return_default":
                        return getattr(func, "__default__", None)  # type: ignore

            elif isinstance(result, dict) and "content" in result:
                # Scan dict content field
                content = str(result.get("content", ""))
                scan_result = _scanner.scan(content)
                if not scan_result.safe:
                    if on_unsafe == "raise":
                        raise SecurityEnforcementError(
                            f"Unsafe content in dict from {func.__name__}: {scan_result.threats}"
                        )
                    elif on_unsafe == "return_none":
                        return None  # type: ignore

            return result

        return wrapper

    return decorator


def scan_file_before_load(
    scanner: SecurityScanner | None = None,
) -> Callable:
    """Decorator that scans a file path before loading.

    The decorated function should accept a Path as first argument.

    Args:
        scanner: SecurityScanner instance (creates new if None)

    Example:
        >>> @scan_file_before_load()
        ... def load_skill(path: Path) -> SkillDefinition:
        ...     return SkillDefinition.from_file(path)
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            # Get first argument (should be path)
            if args and isinstance(args[0], (Path, str)):
                path = Path(args[0])

                _scanner = scanner or SecurityScanner()
                scan_result = _scanner.scan_file(path)

                if not scan_result.safe:
                    raise SecurityEnforcementError(
                        f"Cannot load unsafe file {path}: {scan_result.threats}"
                    )

            return func(*args, **kwargs)

        return wrapper

    return decorator


def scan_string_input(
    arg_index: int = 0,
    scanner: SecurityScanner | None = None,
) -> Callable:
    """Decorator that scans a string argument before function execution.

    Args:
        arg_index: Index of string argument to scan (default: 0)
        scanner: SecurityScanner instance (creates new if None)

    Example:
        >>> @scan_string_input(arg_index=0)
        ... def process_prompt(prompt: str) -> str:
        ...     return f"Processed: {prompt}"
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            if len(args) > arg_index and isinstance(args[arg_index], str):
                content = args[arg_index]

                _scanner = scanner or SecurityScanner()
                scan_result = _scanner.scan(content)

                if not scan_result.safe:
                    raise SecurityEnforcementError(
                        f"Cannot process unsafe content: {scan_result.threats}"
                    )

            return func(*args, **kwargs)

        return wrapper

    return decorator


class SafeLoader:
    """Safe loader wrapper for external content.

    Provides methods to load external content with mandatory
    security scanning.

    Example:
        >>> loader = SafeLoader()
        >>> content = loader.load_text_file(path)
        >>> # Content is guaranteed to be scanned
    """

    def __init__(self, scanner: SecurityScanner | None = None) -> None:
        """Initialize the safe loader.

        Args:
            scanner: SecurityScanner instance (creates new if None)
        """
        self._scanner = scanner or SecurityScanner()

    def load_text_file(
        self,
        path: Path | str,
        encoding: str = "utf-8",
    ) -> str:
        """Load text file with mandatory security scan.

        Args:
            path: File path to load
            encoding: File encoding (default: utf-8)

        Returns:
            File content as string

        Raises:
            SecurityEnforcementError: If file content is unsafe
        """
        path = Path(path)

        # Scan file
        scan_result = self._scanner.scan_file(path)
        if not scan_result.safe:
            raise SecurityEnforcementError(f"Cannot load unsafe file {path}: {scan_result.threats}")

        return path.read_text(encoding=encoding)

    def load_json_file(
        self,
        path: Path | str,
        encoding: str = "utf-8",
    ) -> dict:
        """Load JSON file with mandatory security scan.

        Args:
            path: File path to load
            encoding: File encoding (default: utf-8)

        Returns:
            Parsed JSON as dict

        Raises:
            SecurityEnforcementError: If file content is unsafe
        """
        import json

        content = self.load_text_file(path, encoding)
        return json.loads(content)

    def check_string(self, content: str) -> str:
        """Check string content and return if safe.

        Args:
            content: String content to check

        Returns:
            The same content if safe

        Raises:
            SecurityEnforcementError: If content is unsafe
        """
        scan_result = self._scanner.scan(content)
        if not scan_result.safe:
            raise SecurityEnforcementError(f"Content is unsafe: {scan_result.threats}")
        return content

    def check_file_path(self, path: Path | str) -> Path:
        """Check file path and return if safe.

        Args:
            path: File path to check

        Returns:
            The same path if file is safe

        Raises:
            SecurityEnforcementError: If file content is unsafe
        """
        path = Path(path)
        scan_result = self._scanner.scan_file(path)
        if not scan_result.safe:
            raise SecurityEnforcementError(f"File {path} is unsafe: {scan_result.threats}")
        return path


# Default safe loader instance
_default_loader = SafeLoader()


def load_text_file_safe(path: Path | str, encoding: str = "utf-8") -> str:
    """Convenience function for safe text file loading.

    Args:
        path: File path to load
        encoding: File encoding (default: utf-8)

    Returns:
        File content as string

    Raises:
        SecurityEnforcementError: If file content is unsafe
    """
    return _default_loader.load_text_file(path, encoding)


def load_json_file_safe(path: Path | str, encoding: str = "utf-8") -> dict:
    """Convenience function for safe JSON file loading.

    Args:
        path: File path to load
        encoding: File encoding (default: utf-8)

    Returns:
        Parsed JSON as dict

    Raises:
        SecurityEnforcementError: If file content is unsafe
    """
    return _default_loader.load_json_file(path, encoding)
