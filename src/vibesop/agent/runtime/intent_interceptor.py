"""Intent interceptor — decides whether to trigger VibeSOP routing for a message.

This module provides platform-agnostic logic to determine when a user
message should be routed through VibeSOP's skill matching pipeline.

Platform integrations call `should_intercept()` at message boundaries:
- Claude Code: UserPromptSubmit hook
- OpenCode: chat.message plugin hook
- Kimi CLI: System prompt self-instruction (AI decides)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class InterceptionMode(StrEnum):
    """How to handle the intercepted message."""

    NONE = "none"           # Don't route, let agent handle normally
    SINGLE = "single"       # Route to single best skill
    ORCHESTRATE = "orchestrate"  # Detect multi-intent and build execution plan
    SLASH_COMMAND = "slash_command"  # Execute built-in slash command directly


@dataclass
class InterceptionContext:
    """Context for interception decisions.

    Attributes:
        session_id: Unique session identifier
        current_skill: Skill currently active (if known)
        message_history: Recent messages in conversation
        platform: Platform type (claude-code, opencode, kimi-cli)
    """

    session_id: str = "default"
    current_skill: str | None = None
    message_history: list[dict[str, Any]] = field(default_factory=list)
    platform: str = "unknown"


@dataclass
class InterceptionDecision:
    """Result of interception analysis.

    Attributes:
        should_route: Whether to trigger VibeSOP routing
        mode: Routing mode (none/single/orchestrate)
        reason: Human-readable explanation
        query: Normalized query to route (may differ from original)
    """

    should_route: bool
    mode: InterceptionMode = InterceptionMode.NONE
    reason: str = ""
    query: str = ""


class IntentInterceptor:
    """Intercepts user messages and decides whether to trigger skill routing.

    Uses a conservative heuristic to avoid over-intercepting:
    - Short messages (< 10 chars) are fast-pathed
    - Meta-queries about VibeSOP itself are skipped
    - Explicit skill overrides are fast-pathed to single routing
    - Everything else defaults to orchestrate (multi-intent detection)

    Example:
        >>> interceptor = IntentInterceptor()
        >>> decision = interceptor.should_intercept("review my code")
        >>> decision.should_route
        True
        >>> decision.mode
        <InterceptionMode.ORCHESTRATE: 'orchestrate'>
    """

    # Minimum query length to consider routing
    MIN_QUERY_LENGTH: int = 10

    # Maximum query length for fast-path single routing
    MAX_SHORT_QUERY: int = 50

    # Patterns that indicate meta-queries about VibeSOP itself
    META_PATTERNS: list[str] = [
        r"vibe\s+(route|skill|config|build|install)",
        r"为什么.*(?:路由|技能|skill|route)",
        r"(?:技能|skill).*(?:怎么|如何|为什么|工作)",
        r"routing.*(?:work|how|why)",
        r"what\s+(?:is|does)\s+vibesop",
        r"explain\s+(?:the\s+)?routing",
    ]

    # Patterns that indicate explicit skill selection
    EXPLICIT_SKILL_PATTERNS: list[str] = [
        r"^/(\w+)",           # /review, /debug, etc.
        r"use\s+(?:skill\s+)?([\w/-]+)",
        r"调用\s*(?:技能\s+)?([\w/-]+)",
        r"(?:用|使用)\s*([\w/-]+)\s*(?:技能|skill)?",
    ]

    # Patterns that strongly suggest multi-intent
    MULTI_INTENT_PATTERNS: list[str] = [
        r"(?:and\s+then|then\s+also|and\s+also|in\s+addition)",
        r"(?:然后|接着|之后|另外|还有|以及|并|并且|同时)",
        r"(?:first|second|third|firstly|secondly|thirdly)",
        r"(?:第一步|第二步|第三步|先|再|最后)",
    ]

    def should_intercept(
        self,
        query: str,
        context: InterceptionContext | None = None,
    ) -> InterceptionDecision:
        """Decide whether to intercept and route this message.

        Args:
            query: The user's message/query
            context: Optional session context

        Returns:
            InterceptionDecision with routing recommendation
        """
        original_query = query.strip()

        # 0. Check for VibeSOP slash commands → direct execution
        if original_query.startswith("/vibe-"):
            return InterceptionDecision(
                should_route=True,
                mode=InterceptionMode.SLASH_COMMAND,
                reason=f"VibeSOP slash command detected: {original_query.split()[0]}",
                query=original_query,
            )

        # 1. Empty or too short → skip
        if len(original_query) < self.MIN_QUERY_LENGTH:
            return InterceptionDecision(
                should_route=False,
                reason=f"Query too short ({len(original_query)} < {self.MIN_QUERY_LENGTH})",
            )

        # 2. Meta-query about VibeSOP itself → skip
        if self._is_meta_query(original_query):
            return InterceptionDecision(
                should_route=False,
                reason="Meta-query about VibeSOP system",
            )

        # 3. Check for explicit skill override → fast-path single routing
        explicit_skill = self._extract_explicit_skill(original_query)
        if explicit_skill:
            return InterceptionDecision(
                should_route=True,
                mode=InterceptionMode.SINGLE,
                reason=f"Explicit skill override: {explicit_skill}",
                query=original_query,
            )

        # 4. Short, focused query → single routing (conservative)
        if len(original_query) <= self.MAX_SHORT_QUERY:
            if not self._has_multi_intent_markers(original_query):
                return InterceptionDecision(
                    should_route=True,
                    mode=InterceptionMode.SINGLE,
                    reason="Short focused query, likely single intent",
                    query=original_query,
                )

        # 5. Default: orchestrate (let multi-intent detector decide)
        return InterceptionDecision(
            should_route=True,
            mode=InterceptionMode.ORCHESTRATE,
            reason="Default: check for multi-intent via orchestration",
            query=original_query,
        )

    def _is_meta_query(self, query: str) -> bool:
        """Check if query is about VibeSOP itself."""
        query_lower = query.lower()
        for pattern in self.META_PATTERNS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                return True
        return False

    def _extract_explicit_skill(self, query: str) -> str | None:
        """Extract explicitly mentioned skill ID from query."""
        for pattern in self.EXPLICIT_SKILL_PATTERNS:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                # Return the captured group (skill identifier)
                skill = match.group(1).lower().strip()
                return skill
        return None

    def _has_multi_intent_markers(self, query: str) -> bool:
        """Check if query contains multi-intent conjunctions."""
        query_lower = query.lower()
        for pattern in self.MULTI_INTENT_PATTERNS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                return True
        return False


__all__ = [
    "IntentInterceptor",
    "InterceptionContext",
    "InterceptionDecision",
    "InterceptionMode",
]
