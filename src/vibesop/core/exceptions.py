"""VibeSOP core exceptions.

This module defines all custom exceptions used throughout VibeSOP.
Using specific exception types improves error handling and debugging.
"""

from pathlib import Path


class VibeSOPError(Exception):
    """Base exception for all VibeSOP errors."""

    def __init__(self, message: str, *, details: dict[str, str] | None = None) -> None:
        """Initialize the exception.

        Args:
            message: Error message
            details: Additional error details
        """
        super().__init__(message)
        self.details = details or {}
        self.message = message

    def __str__(self) -> str:
        if self.details:
            details_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
            return f"{self.message} ({details_str})"
        return self.message


class RoutingError(VibeSOPError):
    """Base exception for routing-related errors."""

    pass


class SkillNotFoundError(RoutingError):
    """Raised when a requested skill cannot be found."""

    def __init__(self, skill_id: str) -> None:
        """Initialize the exception.

        Args:
            skill_id: The skill ID that was not found
        """
        super().__init__(f"Skill not found: {skill_id}", details={"skill_id": skill_id})
        self.skill_id = skill_id


class NoMatchingSkillError(RoutingError):
    """Raised when no skill matches the query with sufficient confidence."""

    def __init__(self, query: str, max_confidence: float) -> None:
        """Initialize the exception.

        Args:
            query: The query that failed to match
            max_confidence: The highest confidence score achieved
        """
        super().__init__(
            f"No skill matched query with sufficient confidence (max: {max_confidence:.2f})",
            details={"query": query, "max_confidence": str(max_confidence)},
        )
        self.query = query
        self.max_confidence = max_confidence


class MatcherError(RoutingError):
    """Raised when a matcher encounters an error."""

    def __init__(self, matcher_type: str, message: str) -> None:
        """Initialize the exception.

        Args:
            matcher_type: The type of matcher that failed
            message: The error message
        """
        super().__init__(
            f"Matcher error in {matcher_type}: {message}",
            details={"matcher_type": matcher_type},
        )
        self.matcher_type = matcher_type


class ConfigurationError(VibeSOPError):
    """Raised when there is a configuration error."""

    pass


class InvalidConfigError(ConfigurationError):
    """Raised when the configuration is invalid."""

    def __init__(self, key: str, value: str | None, reason: str) -> None:
        """Initialize the exception.

        Args:
            key: The configuration key that is invalid
            value: The invalid value
            reason: Why the value is invalid
        """
        super().__init__(
            f"Invalid configuration for {key}: {reason}",
            details={"key": key, "value": str(value) if value else "", "reason": reason},
        )
        self.key = key
        self.value = value
        self.reason = reason


class SkillLoadError(VibeSOPError):
    """Raised when a skill fails to load."""

    def __init__(self, skill_path: Path, reason: str) -> None:
        """Initialize the exception.

        Args:
            skill_path: Path to the skill that failed to load
            reason: Why the skill failed to load
        """
        super().__init__(
            f"Failed to load skill from {skill_path}: {reason}",
            details={"path": str(skill_path), "reason": reason},
        )
        self.skill_path = skill_path
        self.reason = reason


class SkillParseError(SkillLoadError):
    """Raised when a skill's metadata cannot be parsed."""

    pass


class CacheError(VibeSOPError):
    """Raised when there is a cache-related error."""

    pass


class LLMError(VibeSOPError):
    """Raised when there is an LLM-related error."""

    def __init__(self, provider: str, message: str) -> None:
        """Initialize the exception.

        Args:
            provider: The LLM provider (e.g., "anthropic", "openai")
            message: The error message
        """
        super().__init__(
            f"LLM error ({provider}): {message}",
            details={"provider": provider},
        )
        self.provider = provider


class PermissionError(VibeSOPError):
    """Raised when there is insufficient permission for an operation."""

    def __init__(self, operation: str, resource: str) -> None:
        """Initialize the exception.

        Args:
            operation: The operation that was attempted
            resource: The resource that was accessed
        """
        super().__init__(
            f"Permission denied for {operation} on {resource}",
            details={"operation": operation, "resource": resource},
        )
        self.operation = operation
        self.resource = resource


class PackIntegrityError(VibeSOPError):
    """Raised when a pack's commit/content differs from its install lock (F-02)."""

    def __init__(self, pack_name: str, old: str, new: str) -> None:
        super().__init__(
            f"Pack {pack_name!r} changed since the last install "
            f"(was {old}, now {new}) — possible force-push or tampering. "
            f"Re-run with --upgrade if you've reviewed and accept the change.",
            details={"pack_name": pack_name, "old": old, "new": new},
        )
        self.pack_name = pack_name


class PlanNotFoundError(VibeSOPError):
    """Raised when an execution plan cannot be found."""

    def __init__(self, plan_id: str) -> None:
        super().__init__(f"Execution plan {plan_id!r} not found", details={"plan_id": plan_id})
        self.plan_id = plan_id


class SingleIntentRoutingError(VibeSOPError):
    """Raised when orchestration is requested for a single-intent query."""

    def __init__(self, query: str) -> None:
        super().__init__(
            f"Single-intent query cannot be orchestrated: {query!r}",
            details={"query": query},
        )
        self.query = query


# Export all exceptions
__all__ = [
    "CacheError",
    "ConfigurationError",
    "InvalidConfigError",
    "LLMError",
    "MatcherError",
    "NoMatchingSkillError",
    "PackIntegrityError",
    "PermissionError",
    "PlanNotFoundError",
    "RoutingError",
    "SingleIntentRoutingError",
    "SkillLoadError",
    "SkillNotFoundError",
    "SkillParseError",
    "VibeSOPError",
]
