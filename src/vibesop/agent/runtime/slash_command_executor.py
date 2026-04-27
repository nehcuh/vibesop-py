"""Slash command executor — bridges IntentInterceptor decisions to handler execution.

When IntentInterceptor detects a `/vibe-*` prefix and returns
`InterceptionMode.SLASH_COMMAND`, this module executes the actual command
via SlashCommandHandler and returns a structured result suitable for
platform adapters to present to users.

Example:
    >>> from vibesop.agent.runtime import IntentInterceptor, SlashCommandExecutor
    >>> interceptor = IntentInterceptor()
    >>> decision = interceptor.should_intercept("/vibe-help")
    >>> executor = SlashCommandExecutor()
    >>> result = executor.execute(decision)
    >>> result.success
    True
    >>> "vibe-route" in result.message
    True
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vibesop.agent.runtime.intent_interceptor import (
    InterceptionDecision,
    InterceptionMode,
)
from vibesop.core.skills.slash_commands import SlashCommandHandler


@dataclass
class SlashCommandResult:
    """Result of executing a slash command.

    Attributes:
        success: Whether the command executed successfully
        message: Human-readable output message
        command: The command that was executed (e.g., "/vibe-help")
        structured: Optional structured data for platform adapters
    """

    success: bool
    message: str
    command: str = ""
    structured: dict[str, Any] | None = None


class SlashCommandExecutor:
    """Executes slash commands from interception decisions.

    Integrates with the Agent Runtime layer to provide a clean API
    for platform adapters:

        decision = interceptor.should_intercept(user_query)
        if decision.mode == InterceptionMode.SLASH_COMMAND:
            result = executor.execute(decision)
            # Present result.message to user

    The executor automatically creates a SlashCommandHandler with
    the current working directory as project root.
    """

    def __init__(self, project_root: Path | None = None) -> None:
        """Initialize the executor.

        Args:
            project_root: Project root for command context. Defaults to cwd.
        """
        self._handler = SlashCommandHandler(project_root=project_root or Path.cwd())

    def execute(self, decision: InterceptionDecision) -> SlashCommandResult:
        """Execute a slash command from an interception decision.

        Args:
            decision: InterceptionDecision with mode SLASH_COMMAND

        Returns:
            SlashCommandResult with execution outcome

        Raises:
            ValueError: If decision mode is not SLASH_COMMAND
        """
        if decision.mode != InterceptionMode.SLASH_COMMAND:
            raise ValueError(f"Expected mode SLASH_COMMAND, got {decision.mode}")

        return self.execute_query(decision.query)

    def execute_query(self, query: str) -> SlashCommandResult:
        """Execute a slash command directly from a query string.

        Args:
            query: User input starting with /vibe-

        Returns:
            SlashCommandResult with execution outcome
        """
        import shlex

        stripped = query.strip()
        success, message = self._handler.execute(stripped)

        # Extract command name and args using shlex for consistency
        try:
            parts = shlex.split(stripped)
        except ValueError:
            parts = stripped.split()
        command = parts[0] if parts else ""

        return SlashCommandResult(
            success=success,
            message=message,
            command=command,
            structured={
                "command": command,
                "args": parts[1:] if len(parts) > 1 else [],
                "raw_output": message,
            },
        )

    def is_slash_command(self, query: str) -> bool:
        """Check if a query is a VibeSOP slash command.

        This is a convenience method that mirrors IntentInterceptor
        logic for platforms that need a quick check.

        Args:
            query: User input to check

        Returns:
            True if query starts with /vibe-
        """
        return query.strip().startswith("/vibe-")


__all__ = [
    "SlashCommandExecutor",
    "SlashCommandResult",
]
