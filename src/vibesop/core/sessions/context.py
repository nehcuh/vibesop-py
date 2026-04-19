"""Session context tracking for intelligent re-routing.

This module monitors conversation progression and detects when
the user's intent may have shifted, triggering intelligent re-routing.

Usage:
    >>> from vibesop.core.sessions import SessionContext
    >>>
    >>> context = SessionContext()
    >>> context.record_tool_use("read", skill="systematic-debugging")
    >>> context.record_tool_use("bash", skill="systematic-debugging")
    >>>
    >>> # Later in conversation
    >>> suggestion = context.check_reroute_needed("design new architecture")
    >>> if suggestion.should_reroute:
    ...     print(f"Consider switching to: {suggestion.recommended_skill}")
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from vibesop.core.routing import UnifiedRouter

logger = logging.getLogger(__name__)


class ContextChange(Enum):
    """Types of context changes detected."""

    NONE = "none"  # No significant change
    MODERATE = "moderate"  # Some shift, worth considering
    SIGNIFICANT = "significant"  # Strong signal to re-route


@dataclass
class RoutingSuggestion:
    """Suggestion for re-routing.

    Attributes:
        should_reroute: Whether re-routing is recommended
        recommended_skill: Suggested skill ID
        confidence: Confidence in this suggestion (0.0-1.0)
        reason: Human-readable explanation
        current_skill: The skill currently being used
    """

    should_reroute: bool
    recommended_skill: str | None = None
    confidence: float = 0.0
    reason: str = ""
    current_skill: str | None = None


@dataclass
class ToolUseEvent:
    """Record of a tool use event.

    Attributes:
        tool_name: Name of the tool used
        timestamp: When the tool was used
        skill: Skill being used at the time
        context: Additional context about the usage
    """

    tool_name: str
    timestamp: float
    skill: str | None = None
    context: dict[str, Any] = field(default_factory=dict)


class SessionContext:
    """Tracks session context for intelligent re-routing.

    This monitors:
    - Tool usage patterns over time
    - Skill transitions
    - Topic/phase changes in the conversation

    When significant changes are detected, it suggests re-routing
    to more appropriate skills.
    """

    def __init__(
        self,
        project_root: str = ".",
        router: UnifiedRouter | None = None,
        reroute_threshold: float = 0.7,
        tool_use_window: int = 10,
        reroute_cooldown: float = 30.0,
    ):
        """Initialize session context tracker.

        Args:
            project_root: Path to project root
            router: Optional external UnifiedRouter instance (for dependency injection)
            reroute_threshold: Confidence threshold for re-routing suggestions
            tool_use_window: Number of recent tool uses to analyze
            reroute_cooldown: Seconds between re-routing checks
        """
        from pathlib import Path

        self.project_root = Path(project_root).resolve()
        # Use injected router or create new one (dependency injection)
        self._router = router or UnifiedRouter(project_root=self.project_root)
        self._reroute_threshold = reroute_threshold
        self._tool_use_window = tool_use_window
        self._reroute_cooldown = reroute_cooldown

        # Thread-safe storage
        self._lock = threading.Lock()
        self._tool_history: list[ToolUseEvent] = []
        self._current_skill: str | None = None
        self._session_start_time = time.time()
        self._last_reroute_check = 0.0

    def record_tool_use(
        self,
        tool_name: str,
        skill: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Record a tool use event.

        Args:
            tool_name: Name of the tool (e.g., "read", "bash", "edit")
            skill: Skill being used (if known)
            context: Additional context (files touched, commands run, etc.)
        """
        with self._lock:
            event = ToolUseEvent(
                tool_name=tool_name,
                timestamp=time.time(),
                skill=skill or self._current_skill,
                context=context or {},
            )
            self._tool_history.append(event)

            # Update current skill if provided
            if skill:
                self._current_skill = skill

            # Keep only recent history
            if len(self._tool_history) > self._tool_use_window * 2:
                self._tool_history = self._tool_history[-self._tool_use_window :]

            logger.debug(f"Recorded tool use: {tool_name} (skill: {skill})")

    def set_current_skill(self, skill_id: str) -> None:
        """Set the currently active skill.

        Args:
            skill_id: Skill identifier (e.g., "systematic-debugging")
        """
        with self._lock:
            self._current_skill = skill_id
            logger.debug(f"Current skill set to: {skill_id}")

    def check_reroute_needed(self, user_message: str) -> RoutingSuggestion:
        """Check if re-routing is suggested based on conversation context.

        This analyzes:
        1. Recent tool usage patterns
        2. The new user message
        3. Current skill being used
        4. Topic/phase changes

        Args:
            user_message: The latest user message

        Returns:
            RoutingSuggestion with recommendation
        """
        with self._lock:
            # Avoid excessive re-routing checks
            now = time.time()
            if now - self._last_reroute_check < self._reroute_cooldown:
                return RoutingSuggestion(should_reroute=False, reason="Cooldown active")

            self._last_reroute_check = now

            # Get recent tool usage
            recent_tools = self._get_recent_tools(min_events=3)

            # Detect context change
            context_change = self._detect_context_change(user_message, recent_tools)

            if context_change == ContextChange.NONE:
                return RoutingSuggestion(
                    should_reroute=False,
                    reason="No significant context change detected",
                    current_skill=self._current_skill,
                )

            # Route the new message
            routing_result = self._router.route(user_message)

            if not routing_result.has_match:
                return RoutingSuggestion(
                    should_reroute=False,
                    reason="No matching skill found for new message",
                    current_skill=self._current_skill,
                )

            new_skill = routing_result.primary.skill_id
            confidence = routing_result.primary.confidence

            # Check if different from current skill
            if new_skill == self._current_skill:
                return RoutingSuggestion(
                    should_reroute=False,
                    reason=f"Same skill recommended: {new_skill}",
                    current_skill=self._current_skill,
                )

            # Check if confidence is high enough
            if confidence < self._reroute_threshold:
                return RoutingSuggestion(
                    should_reroute=False,
                    reason=f"Low confidence ({confidence:.0%}) for {new_skill}",
                    current_skill=self._current_skill,
                )

            # Generate reason based on context change type
            reason = self._generate_reason(
                context_change, self._current_skill, new_skill, recent_tools
            )

            return RoutingSuggestion(
                should_reroute=True,
                recommended_skill=new_skill,
                confidence=confidence,
                reason=reason,
                current_skill=self._current_skill,
            )

    def _get_recent_tools(self, min_events: int = 3) -> list[ToolUseEvent]:
        """Get recent tool use events.

        Args:
            min_events: Minimum number of events to return

        Returns:
            List of recent tool use events
        """
        return self._tool_history[-min_events:] if len(self._tool_history) >= min_events else self._tool_history.copy()

    def _detect_context_change(
        self, user_message: str, recent_tools: list[ToolUseEvent]
    ) -> ContextChange:
        """Detect if context has changed significantly.

        Args:
            user_message: The new user message
            recent_tools: Recent tool usage events

        Returns:
            ContextChange level
        """
        if not recent_tools:
            return ContextChange.MODERATE  # New session, worth checking

        # Analyze tool usage patterns
        tool_patterns = self._analyze_tool_patterns(recent_tools)

        # Check for phase transition signals
        phase_keywords = {
            "planning": ["plan", "design", "architecture", "approach"],
            "implementation": ["implement", "code", "write", "add", "fix"],
            "review": ["review", "check", "verify", "validate"],
            "testing": ["test", "debug", "error", "failing"],
            "brainstorming": ["brainstorm", "ideas", "explore", "consider"],
        }

        message_lower = user_message.lower()
        detected_phase = None
        for phase, keywords in phase_keywords.items():
            if any(keyword in message_lower for keyword in keywords):
                detected_phase = phase
                break

        if not detected_phase:
            return ContextChange.NONE

        # Check if current phase matches detected phase
        current_phase = self._infer_phase_from_tools(tool_patterns)

        if current_phase != detected_phase:
            return ContextChange.SIGNIFICANT

        # Check for mixed signals (moderate change)
        if self._has_mixed_signals(recent_tools, user_message):
            return ContextChange.MODERATE

        return ContextChange.NONE

    def _analyze_tool_patterns(self, tools: list[ToolUseEvent]) -> dict[str, int]:
        """Analyze tool usage patterns.

        Args:
            tools: List of tool use events

        Returns:
            Dictionary mapping tool names to usage counts
        """
        patterns: dict[str, int] = {}
        for tool in tools:
            patterns[tool.tool_name] = patterns.get(tool.tool_name, 0) + 1
        return patterns

    def _infer_phase_from_tools(self, tool_patterns: dict[str, int]) -> str | None:
        """Infer current phase from tool usage.

        Args:
            tool_patterns: Tool usage patterns

        Returns:
            Inferred phase or None
        """
        if not tool_patterns:
            return None

        # Map tools to phases
        phase_indicators = {
            "planning": ["read"],
            "implementation": ["edit", "write"],
            "review": ["read"],
            "testing": ["bash", "run"],
        }

        # Score each phase based on tool usage
        phase_scores: dict[str, float] = {}
        total_tools = sum(tool_patterns.values())

        for phase, indicators in phase_indicators.items():
            score = sum(tool_patterns.get(tool, 0) for tool in indicators) / total_tools
            phase_scores[phase] = score

        # Return highest-scoring phase
        if phase_scores:
            return max(phase_scores, key=phase_scores.get)

        return None

    def _has_mixed_signals(self, tools: list[ToolUseEvent], message: str) -> bool:
        """Check if there are mixed signals in the conversation.

        Args:
            tools: Recent tool usage
            message: User message

        Returns:
            True if mixed signals detected
        """
        # Check for transition phrases
        transition_phrases = [
            "now let's",
            "next we should",
            "after that",
            "moving on to",
            "switch to",
        ]

        message_lower = message.lower()
        return any(phrase in message_lower for phrase in transition_phrases)

    def _generate_reason(
        self,
        context_change: ContextChange,
        current_skill: str | None,
        new_skill: str,
        recent_tools: list[ToolUseEvent],
    ) -> str:
        """Generate human-readable reason for re-routing suggestion.

        Args:
            context_change: Type of context change
            current_skill: Current skill
            new_skill: Recommended new skill
            recent_tools: Recent tool usage

        Returns:
            Human-readable explanation
        """
        if context_change == ContextChange.SIGNIFICANT:
            return f"Context shift detected: {current_skill} → {new_skill}. " f"Recent tool usage suggests a phase change."

        elif context_change == ContextChange.MODERATE:
            return (
                f"Possible context shift from {current_skill} to {new_skill}. "
                f"Consider switching if the task focus has changed."
            )

        return f"Suggesting switch from {current_skill} to {new_skill} based on conversation context."

    def get_session_summary(self) -> dict[str, Any]:
        """Get summary of current session.

        Returns:
            Dictionary with session statistics
        """
        with self._lock:
            duration = time.time() - self._session_start_time

            return {
                "duration_seconds": duration,
                "current_skill": self._current_skill,
                "tool_use_count": len(self._tool_history),
                "tool_breakdown": self._analyze_tool_patterns(self._tool_history),
                "recent_tools": [
                    {"tool": t.tool_name, "skill": t.skill, "time": t.timestamp}
                    for t in self._tool_history[-5:]
                ],
            }


__all__ = [
    "ContextChange",
    "RoutingSuggestion",
    "SessionContext",
]
