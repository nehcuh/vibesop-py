# pyright: ignore[reportCallIssue]
"""Session context tracking for intelligent re-routing."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
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
    """Suggestion for re-routing."""

    should_reroute: bool
    recommended_skill: str | None = None
    confidence: float = 0.0
    reason: str = ""
    current_skill: str | None = None


@dataclass
class ToolUseEvent:
    """Record of a tool use event."""

    tool_name: str
    timestamp: float
    skill: str | None = None
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class RouteDecision:
    """Record of a routing decision for habit learning."""

    query_pattern: str
    selected_skill: str
    timestamp: float


class SessionContext:
    """Tracks session context for intelligent re-routing."""

    def __init__(
        self,
        project_root: str = ".",
        router: UnifiedRouter | None = None,
        reroute_threshold: float = 0.7,
        tool_use_window: int = 10,
        reroute_cooldown: float = 5.0,
        session_id: str = "default",
    ):
        self.project_root = Path(project_root).resolve()
        # Use injected router or create new one (dependency injection)
        self._router = router or UnifiedRouter(project_root=self.project_root)
        self._reroute_threshold = reroute_threshold
        self._tool_use_window = tool_use_window
        self._reroute_cooldown = reroute_cooldown
        self.session_id = self._resolve_session_id(session_id)

        # Thread-safe storage
        self._lock = threading.RLock()
        self._tool_history: list[ToolUseEvent] = []
        self._current_skill: str | None = None
        self._session_start_time = time.time()
        self._last_reroute_check = 0.0
        self._route_history: list[RouteDecision] = []
        self._habit_patterns: dict[str, str] = {}

    def _resolve_session_id(self, session_id: str) -> str:
        if session_id != "default":
            return session_id

        env_id = os.environ.get("VIBESOP_SESSION_ID")
        if env_id:
            return env_id

        # Derive from project path hash for per-project isolation
        path_hash = hashlib.sha256(str(self.project_root).encode("utf-8")).hexdigest()[:12]
        return f"project-{path_hash}"

    def record_tool_use(
        self,
        tool_name: str,
        skill: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
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
        with self._lock:
            self._current_skill = skill_id
            logger.debug(f"Current skill set to: {skill_id}")

    def check_reroute_needed(self, user_message: str) -> RoutingSuggestion:
        """Check if re-routing is suggested based on conversation context."""
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
            routing_result = self._router._single_skill_route(user_message)  # pyright: ignore[reportPrivateUsage]

            if not routing_result.has_match:
                return RoutingSuggestion(
                    should_reroute=False,
                    reason="No matching skill found for new message",
                    current_skill=self._current_skill,
                )

            primary = routing_result.primary
            if primary is None:
                return RoutingSuggestion(
                    should_reroute=False,
                    reason="No primary match available",
                    current_skill=self._current_skill,
                )

            new_skill = primary.skill_id
            confidence = primary.confidence

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
        return (
            self._tool_history[-min_events:]
            if len(self._tool_history) >= min_events
            else self._tool_history.copy()
        )

    def _detect_context_change(
        self, user_message: str, recent_tools: list[ToolUseEvent]
    ) -> ContextChange:
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
        patterns: dict[str, int] = {}
        for tool in tools:
            patterns[tool.tool_name] = patterns.get(tool.tool_name, 0) + 1
        return patterns

    def _infer_phase_from_tools(self, tool_patterns: dict[str, int]) -> str | None:
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
            return max(phase_scores, key=lambda k: phase_scores[k])

        return None

    def _has_mixed_signals(self, _tools: list[ToolUseEvent], message: str) -> bool:
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
        _recent_tools: list[ToolUseEvent],
    ) -> str:
        if context_change == ContextChange.SIGNIFICANT:
            return (
                f"Context shift detected: {current_skill} → {new_skill}. "
                f"Recent tool usage suggests a phase change."
            )

        elif context_change == ContextChange.MODERATE:
            return (
                f"Possible context shift from {current_skill} to {new_skill}. "
                f"Consider switching if the task focus has changed."
            )

        return (
            f"Suggesting switch from {current_skill} to {new_skill} based on conversation context."
        )

    def record_route_decision(self, query: str, selected_skill: str) -> None:
        with self._lock:
            self._route_history.append(
                RouteDecision(
                    query_pattern=self._extract_pattern(query),
                    selected_skill=selected_skill,
                    timestamp=time.time(),
                )
            )
            self._update_habit_patterns()

    def get_habit_boost(self, query: str) -> dict[str, float]:
        with self._lock:
            query_pattern = self._extract_pattern(query)
            skill = self._habit_patterns.get(query_pattern)
            if skill:
                return {skill: 0.12}
            return {}

    def _extract_pattern(self, query: str) -> str:
        query_lower = query.lower()
        # Simple keyword extraction: remove common stop words
        stop_words = {
            "帮我",
            "请",
            "一下",
            "这个",
            "那个",
            "的",
            "了",
            "在",
            "是",
            "help",
            "me",
            "please",
            "the",
            "a",
            "an",
            "this",
            "that",
            "with",
            "for",
            "to",
            "my",
            "can",
            "you",
            "i",
            "need",
        }
        words = []
        for word in query_lower.split():
            # Chinese: check 2-char segments
            if any(ord(c) > 127 for c in word):
                for i in range(len(word) - 1):
                    seg = word[i : i + 2]
                    if seg not in stop_words and len(seg) >= 2:
                        words.append(seg)
            elif word not in stop_words and len(word) >= 2:
                words.append(word)

        # Deduplicate and sort for canonical form
        unique = sorted(set(words))
        return " ".join(unique) if unique else query_lower[:20]

    def _update_habit_patterns(self) -> None:
        """Extract recurring query→skill patterns from route history."""
        from collections import Counter

        patterns: Counter[tuple[str, str]] = Counter()
        for rd in self._route_history[-50:]:
            patterns[(rd.query_pattern, rd.selected_skill)] += 1

        # Keep only patterns that occurred 3+ times
        self._habit_patterns = {
            pattern: skill for (pattern, skill), count in patterns.items() if count >= 3
        }

    def get_session_summary(self) -> dict[str, Any]:
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

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "session_id": self.session_id,
                "current_skill": self._current_skill,
                "session_start_time": self._session_start_time,
                "last_reroute_check": self._last_reroute_check,
                "last_activity": time.time(),
                "tool_history": [
                    {
                        "tool_name": t.tool_name,
                        "timestamp": t.timestamp,
                        "skill": t.skill,
                        "context": t.context,
                    }
                    for t in self._tool_history
                ],
                "route_history": [
                    {
                        "query_pattern": r.query_pattern,
                        "selected_skill": r.selected_skill,
                        "timestamp": r.timestamp,
                    }
                    for r in self._route_history[-50:]
                ],
                "habit_patterns": self._habit_patterns,
            }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        project_root: str = ".",
        router: UnifiedRouter | None = None,
    ) -> SessionContext:
        ctx = cls(
            project_root=project_root,
            router=router,
            session_id=data.get("session_id", "default"),
        )
        ctx._current_skill = data.get("current_skill")
        ctx._session_start_time = data.get("session_start_time", time.time())
        ctx._last_reroute_check = data.get("last_reroute_check", 0.0)
        # last_activity is informational for TTL; not stored as instance state
        ctx._tool_history = [
            ToolUseEvent(
                tool_name=t["tool_name"],
                timestamp=t["timestamp"],
                skill=t.get("skill"),
                context=t.get("context", {}),
            )
            for t in data.get("tool_history", [])
        ]
        ctx._route_history = [
            RouteDecision(
                query_pattern=r["query_pattern"],
                selected_skill=r["selected_skill"],
                timestamp=r["timestamp"],
            )
            for r in data.get("route_history", [])
        ]
        ctx._habit_patterns = data.get("habit_patterns", {})
        return ctx

    def save(self, storage_dir: str | Path | None = None) -> Path:
        if storage_dir is None:
            storage_dir = self.project_root / ".vibe" / "session"
        else:
            storage_dir = Path(storage_dir)

        storage_dir.mkdir(parents=True, exist_ok=True)
        path = storage_dir / f"{self.session_id}.json"

        with path.open("w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

        logger.debug(f"Session saved: {path}")
        return path

    @classmethod
    def load(
        cls,
        session_id: str = "default",
        project_root: str = ".",
        router: UnifiedRouter | None = None,
        storage_dir: str | Path | None = None,
    ) -> SessionContext:
        if storage_dir is None:
            storage_dir = Path(project_root).resolve() / ".vibe" / "session"
        else:
            storage_dir = Path(storage_dir)

        path = storage_dir / f"{session_id}.json"

        if not path.exists():
            logger.debug(f"No saved session found at {path}, creating fresh instance")
            return cls(
                project_root=project_root,
                router=router,
                session_id=session_id,
            )

        with path.open(encoding="utf-8") as f:
            data = json.load(f)

        logger.debug(f"Session loaded: {path}")
        return cls.from_dict(data, project_root=project_root, router=router)


__all__ = [
    "ContextChange",
    "RoutingSuggestion",
    "SessionContext",
]
