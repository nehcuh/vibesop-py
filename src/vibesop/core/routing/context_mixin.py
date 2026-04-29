"""Router context enrichment and session management mixin.

Extracted from UnifiedRouter to reduce class size and separate concerns.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast

from vibesop.core.matching import RoutingContext
from vibesop.core.models import RoutingResult

if TYPE_CHECKING:
    from vibesop.core.instinct import InstinctLearner
    from vibesop.core.memory import MemoryManager
    from vibesop.core.sessions import SessionContext


logger = logging.getLogger(__name__)


class _ContextHost(Protocol):
    """Protocol defining the interface expected by RouterContextMixin."""

    _memory_manager: MemoryManager | None
    _session_context: SessionContext | None
    _instinct_learner: InstinctLearner | None
    _project_analyzer: Any | None
    _config: Any
    project_root: Path


class RouterContextMixin:
    """Mixin providing context enrichment, memory, session, and instinct methods.

    Intended for use with UnifiedRouter. Expects the following attributes
    on the host class:
        - _memory_manager: MemoryManager | None
        - _session_context: SessionContext | None
        - _instinct_learner: InstinctLearner | None
        - _project_analyzer: ProjectAnalyzer | None
        - _config: RoutingConfig
        - project_root: Path
    """

    def _get_memory_manager(self) -> MemoryManager:
        host = cast("_ContextHost", self)
        if host._memory_manager is None:
            from vibesop.core.memory import MemoryManager

            host._memory_manager = MemoryManager(
                storage_dir=host.project_root / ".vibe" / "memory"
            )
        return host._memory_manager

    def _get_session_context(self):
        """Lazy-load session context for multi-turn state persistence."""
        host = cast("_ContextHost", self)
        if host._session_context is None:
            from vibesop.core.sessions import SessionContext

            host._session_context = SessionContext.load(
                session_id="default",  # resolved internally via _resolve_session_id
                project_root=str(host.project_root),
                router=self,
            )
        return host._session_context

    def _save_session_state(
        self, result: RoutingResult, _context: RoutingContext | None
    ) -> None:
        """Persist session state after routing."""
        host = cast("_ContextHost", self)
        if not host._config.session_aware:
            return

        try:
            session = self._get_session_context()
            if result.has_match and result.primary is not None:
                session.set_current_skill(result.primary.skill_id)
                session.record_route_decision(result.query, result.primary.skill_id)
            # Note: fallback/no-match does NOT erase current_skill — preserves context
            session.save()
        except (OSError, ValueError, RuntimeError) as e:
            logger.debug("Failed to save session state: %s", e)

    def _get_instinct_learner(self) -> InstinctLearner:
        host = cast("_ContextHost", self)
        if host._instinct_learner is None:
            from vibesop.core.instinct import InstinctLearner

            host._instinct_learner = InstinctLearner(
                storage_path=host.project_root / ".vibe" / "instincts.jsonl"
            )
        return host._instinct_learner

    def _enrich_context(
        self, context: RoutingContext | None, query: str = ""
    ) -> RoutingContext:
        """Enrich routing context with memory, session state, recent conversation history, and project context."""
        if context is None:
            context = RoutingContext()

        # If no conversation_id set, try to use active conversation from memory
        if not context.conversation_id:
            active_id = self._get_memory_manager().get_active_conversation_id()
            if active_id:
                context.conversation_id = active_id

        # Load recent queries from memory if not already provided
        if context.conversation_id and not context.recent_queries:
            context.recent_queries = self._get_memory_manager().get_recent_queries(
                context.conversation_id, limit=3
            )

        # Load session state for multi-turn awareness
        host = cast("_ContextHost", self)
        if host._config.session_aware:
            session = self._get_session_context()
            if session:
                if not context.current_skill and session._current_skill:
                    context.current_skill = session._current_skill
                # Load habit boosts for learned patterns
                if not context.habit_boosts and query:
                    context.habit_boosts = session.get_habit_boost(query)

        # Detect project type and tech stack for context-aware routing
        if not context.project_type:
            if host._project_analyzer is None:
                from vibesop.core.project_analyzer import ProjectAnalyzer

                host._project_analyzer = ProjectAnalyzer(host.project_root)
            analyzer = host._project_analyzer
            profile = analyzer.analyze()
            if profile.project_type:
                context.project_type = profile.project_type
                context.recent_files = profile.tech_stack  # Reuse field for tech stack

        return context
