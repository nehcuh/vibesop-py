"""Security-related exceptions for VibeSOP."""


class SecurityError(Exception):
    """Base exception for security-related errors.

    Raised when a security violation is detected during scanning
    or validation operations.
    """

    def __init__(self, message: str, details: dict[str, str] | None = None) -> None:
        """Initialize the security error.

        Args:
            message: Error message describing the security issue
            details: Additional details about the error
        """
        super().__init__(message)
        self.details = details or {}

    def __str__(self) -> str:
        """Return string representation."""
        if self.details:
            details_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
            return f"{super().__str__()} ({details_str})"
        return super().__str__()


class PathTraversalError(SecurityError):
    """Raised when path traversal attack is detected.

    This occurs when a path attempts to access directories outside
    the allowed base directory (e.g., ../../../etc/passwd).
    """

    def __init__(
        self,
        message: str,
        path: str,
        base_dir: str,
    ) -> None:
        """Initialize the path traversal error.

        Args:
            message: Error message
            path: The suspicious path
            base_dir: The base directory that was violated
        """
        details = {"path": path, "base_dir": base_dir}
        super().__init__(message, details)
        self.path = path
        self.base_dir = base_dir


class UnsafeContentError(SecurityError):
    """Raised when unsafe content is detected during scanning.

    This occurs when content contains patterns that indicate
    prompt injection, role hijacking, or other security threats.
    """

    def __init__(
        self,
        message: str,
        threat_count: int = 0,
        risk_level: str = "UNKNOWN",
    ) -> None:
        """Initialize the unsafe content error.

        Args:
            message: Error message
            threat_count: Number of threats detected
            risk_level: Risk level (CRITICAL, HIGH, MEDIUM, LOW)
        """
        details = {"threat_count": str(threat_count), "risk_level": risk_level}
        super().__init__(message, details)
        self.threat_count = threat_count
        self.risk_level = risk_level


class PathOverlapError(SecurityError):
    """Raised when path overlap is detected.

    This occurs when output paths would overlap with input paths
    or other protected directories.
    """

    def __init__(
        self,
        message: str,
        path1: str,
        path2: str,
    ) -> None:
        """Initialize the path overlap error.

        Args:
            message: Error message
            path1: First path
            path2: Second overlapping path
        """
        details = {"path1": path1, "path2": path2}
        super().__init__(message, details)
        self.path1 = path1
        self.path2 = path2
