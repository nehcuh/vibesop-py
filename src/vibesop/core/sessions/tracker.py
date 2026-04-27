# pyright: ignore[reportArgumentType]
"""Platform-agnostic session tracking interface.

This module defines the abstraction layer for session tracking across
different platforms (Claude Code, OpenCode, future platforms).

Each platform implements its own tracking mechanism based on
available extension points.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from vibesop.core.sessions.context import RoutingSuggestion, SessionContext

logger = logging.getLogger(__name__)


class SessionTracker(ABC):
    """Abstract base class for platform-specific session tracking.

    Each platform (Claude Code, OpenCode, etc.) implements this
    interface based on its available extension mechanisms.
    """

    @abstractmethod
    def is_available(self) -> bool:
        """Check if tracking is available on this platform.

        Returns:
            True if tracking can be used
        """
        pass

    @abstractmethod
    def enable(self) -> bool:
        """Enable session tracking on this platform.

        Returns:
            True if successfully enabled
        """
        pass

    @abstractmethod
    def disable(self) -> bool:
        """Disable session tracking on this platform.

        Returns:
            True if successfully disabled
        """
        pass

    @abstractmethod
    def record_tool_use(self, tool_name: str, skill: str | None = None, **_context: Any) -> None:
        """Record a tool use event.

        Args:
            tool_name: Name of the tool being used
            skill: Current skill (if known)
            **context: Additional platform-specific context
        """
        pass

    @abstractmethod
    def check_reroute(self, user_message: str) -> RoutingSuggestion:
        """Check if re-routing should be suggested.

        Args:
            user_message: The latest user message

        Returns:
            RoutingSuggestion with recommendation
        """
        pass

    @abstractmethod
    def get_platform_name(self) -> str:
        """Get platform identifier.

        Returns:
            Platform name (e.g., 'claude-code', 'kimi-cli', 'opencode')
        """
        pass


class GenericSessionTracker(SessionTracker):
    """Generic session tracker that works without platform-specific hooks.

    This tracker provides session tracking functionality through
    manual CLI commands rather than platform hooks.

    Use this for platforms that don't support hooks (like OpenCode)
    or for testing/development.
    """

    def __init__(self, project_root: str | Path = ".", config_dir: str | Path | None = None):
        """Initialize generic session tracker.

        Args:
            project_root: Path to VibeSOP project root
            config_dir: Directory for session state (defaults to ~/.vibe/sessions)
        """
        from pathlib import Path

        self.project_root = Path(project_root).resolve()

        # Use proper standard directory structure
        if config_dir:
            self.config_dir = Path(config_dir).expanduser()
        else:
            self.config_dir = Path.home() / ".vibe" / "sessions"

        self.config_dir.mkdir(parents=True, exist_ok=True)

        # Session context
        self._context = SessionContext(project_root=self.project_root)

        # State file (hash the project root to keep sessions separate per project)
        import hashlib

        project_hash = hashlib.md5(str(self.project_root).encode()).hexdigest()[:8]
        self._state_file = self.config_dir / f"state_{project_hash}.json"

        # Load existing state if available
        self._load_state()

    def is_available(self) -> bool:
        """Check if tracking is available.

        Returns:
            True (generic tracker is always available)
        """
        return True

    def enable(self) -> bool:
        """Enable session tracking.

        For generic tracker, this means creating the config directory.

        Returns:
            True if successfully enabled
        """
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Generic session tracking enabled: {self.config_dir}")
            return True
        except Exception as e:
            logger.error(f"Failed to enable generic tracking: {e}")
            return False

    def disable(self) -> bool:
        """Disable session tracking.

        For generic tracker, this removes state files.

        Returns:
            True if successfully disabled
        """
        try:
            if self._state_file.exists():
                self._state_file.unlink()
            logger.info("Generic session tracking disabled")
            return True
        except Exception as e:
            logger.error(f"Failed to disable generic tracking: {e}")
            return False

    def record_tool_use(self, tool_name: str, skill: str | None = None, **_context: Any) -> None:
        """Record a tool use event.

        Args:
            tool_name: Name of the tool
            skill: Current skill
            **context: Additional context (ignored in generic tracker)
        """
        self._context.record_tool_use(tool_name, skill)
        self._save_state()

    def check_reroute(self, user_message: str) -> RoutingSuggestion:
        """Check if re-routing should be suggested.

        Args:
            user_message: The latest user message

        Returns:
            RoutingSuggestion with recommendation
        """
        return self._context.check_reroute_needed(user_message)

    def get_platform_name(self) -> str:
        """Get platform identifier.

        Returns:
            'generic' (works with any platform)
        """
        return "generic"

    def _load_state(self) -> None:
        """Load session state from file."""
        import json

        if not self._state_file.exists():
            return

        try:
            state = json.loads(self._state_file.read_text())

            # Restore session context
            if "current_skill" in state:
                self._context.set_current_skill(state["current_skill"])

            # Restore tool history (simplified)
            if "tool_history" in state:
                for event in state["tool_history"][-10:]:  # Keep last 10
                    self._context.record_tool_use(
                        event["tool_name"], event.get("skill"), event.get("context", {})
                    )

            logger.debug(f"Loaded session state from {self._state_file}")
        except Exception as e:
            logger.warning(f"Failed to load session state: {e}")

    def _save_state(self) -> None:
        """Save session state to file.

        Uses atomic file writing to prevent corruption on concurrent saves.
        """
        import json
        import tempfile

        try:
            state = {
                "current_skill": self._context._current_skill,
                "tool_history": [
                    {
                        "tool_name": e.tool_name,
                        "skill": e.skill,
                        "timestamp": e.timestamp,
                        "context": e.context,
                    }
                    for e in self._context._tool_history[-10:]
                ],
            }

            # Atomic write pattern
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(dir=self._state_file.parent, prefix=".tmp_state_")
            with open(fd, "w", encoding="utf-8", closefd=False) as f:
                json.dump(state, f, indent=2)

            # Atomic replace
            Path(tmp_path).replace(self._state_file)
        except Exception as e:
            logger.warning(f"Failed to save session state: {e}")


class HookBasedSessionTracker(SessionTracker):
    """Session tracker that uses platform hooks for automatic tracking.

    This is used by platforms that support hooks (like Claude Code).
    """

    def __init__(
        self,
        project_root: str | Path = ".",
        platform: str = "claude-code",
        hooks_dir: str | Path | None = None,
    ):
        """Initialize hook-based session tracker.

        Args:
            project_root: Path to VibeSOP project root
            platform: Platform identifier
            hooks_dir: Directory where hooks are installed
        """
        from pathlib import Path

        self.project_root = Path(project_root).resolve()
        self.platform = platform
        self.hooks_dir = Path(hooks_dir or f"~/.{platform}/hooks").expanduser()

        # Session context (in-memory only for hooks)
        self._context = SessionContext(project_root=self.project_root)

    def is_available(self) -> bool:
        """Check if hooks are available.

        Returns:
            True if hooks directory exists and contains hooks
        """
        return self.hooks_dir.exists() and any(self.hooks_dir.glob("*.sh"))

    def enable(self) -> bool:
        """Enable hook-based tracking.

        This installs the hooks if they don't exist.

        Returns:
            True if hooks are installed/enabled
        """
        # Hooks are installed by vibe build, just check they exist
        return self.is_available()

    def disable(self) -> bool:
        """Disable hook-based tracking.

        Returns:
            True (hooks can be disabled via environment variable)
        """
        # Hooks are disabled via VIBESOP_CONTEXT_TRACKING=false
        return True

    def record_tool_use(self, tool_name: str, skill: str | None = None, **context: Any) -> None:
        """Record a tool use event (called by hooks).

        Args:
            tool_name: Name of the tool
            skill: Current skill
            **context: Additional context
        """
        self._context.record_tool_use(tool_name, skill, context)

    def check_reroute(self, user_message: str) -> RoutingSuggestion:
        """Check if re-routing should be suggested.

        Args:
            user_message: The latest user message

        Returns:
            RoutingSuggestion with recommendation
        """
        return self._context.check_reroute_needed(user_message)

    def get_platform_name(self) -> str:
        """Get platform identifier.

        Returns:
            Platform name
        """
        return self.platform


def get_tracker(
    platform: str = "auto",
    project_root: str | Path = ".",
) -> SessionTracker:
    """Get the appropriate session tracker for a platform.

    Args:
        platform: Platform identifier ('auto', 'claude-code', 'kimi-cli', 'opencode', 'generic')
        project_root: Path to VibeSOP project root

    Returns:
        SessionTracker instance for the platform
    """
    if platform == "auto":
        # Auto-detect platform
        platform = _detect_platform()

    # Use hook-based tracker for Claude Code
    if platform == "claude-code":
        return HookBasedSessionTracker(project_root=project_root, platform="claude-code")

    # Use generic tracker for OpenCode, Kimi CLI and other platforms
    # (they don't support file-based hooks yet)
    return GenericSessionTracker(project_root=project_root)


def _detect_platform() -> str:
    """Auto-detect the current platform.

    Returns:
        Detected platform name
    """
    import os

    # Check for Claude Code
    if "CLAUDE_SESSION_FILE" in os.environ or Path.home().joinpath(".claude").exists():
        return "claude-code"

    # Check for Kimi Code CLI
    if Path.home().joinpath(".kimi").exists():
        return "kimi-cli"

    # Check for OpenCode
    if Path.home().joinpath(".opencode").exists():
        return "opencode"

    # Default to generic
    return "generic"


__all__ = [
    "GenericSessionTracker",
    "HookBasedSessionTracker",
    "SessionTracker",
    "_detect_platform",
    "get_tracker",
]
