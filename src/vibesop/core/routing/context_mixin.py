# pyright: ignore[reportUnnecessaryComparison, reportPrivateUsage]
"""Router context mixin - memory, session, and instinct integration.

Provides context-aware routing capabilities through memory management,
session state persistence, and instinct learning.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from vibesop.core.instinct import InstinctLearner
from vibesop.core.matching import RoutingContext
from vibesop.core.memory import MemoryManager

if TYPE_CHECKING:
    from vibesop.core.models import RoutingResult
    pass

logger = logging.getLogger(__name__)


class RouterContextMixin:
    """Mixin for router context management (memory, session, instinct)."""

    def _get_memory_manager(self) -> MemoryManager:
        if self._memory_manager is None:  # pyright: ignore[reportUnnecessaryComparison]
            self._memory_manager = MemoryManager(
                storage_dir=self.project_root / ".vibe" / "memory"
            )
        return self._memory_manager

    def _get_session_context(self):
        """Lazy-load session context for multi-turn state persistence."""
        if self._session_context is None:
            from vibesop.core.sessions import SessionContext

            self._session_context = SessionContext.load(
                session_id="default",  # resolved internally via _resolve_session_id
                project_root=str(self.project_root),
                router=self,
            )
        return self._session_context

    def _save_session_state(self, result: RoutingResult, _context: RoutingContext | None) -> None:
        """Persist session state after routing."""
        if not self._config.session_aware:
            return

        try:
            session = self._get_session_context()
            if result.has_match and result.primary is not None:
                session.set_current_skill(result.primary.skill_id)
                session.record_route_decision(result.query, result.primary.skill_id)
            # Note: fallback/no-match does NOT erase current_skill — preserves context
            session.save()
        except (OSError, ValueError, RuntimeError) as e:
            logger.debug(f"Failed to save session state: {e}")

    def _get_instinct_learner(self) -> InstinctLearner:
        if self._instinct_learner is None:
            self._instinct_learner = InstinctLearner(
                storage_path=self.project_root / ".vibe" / "instincts.jsonl"
            )
        return self._instinct_learner

    def _enrich_context(self, context: RoutingContext | None, query: str = "") -> RoutingContext:
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
        if self._config.session_aware:
            session = self._get_session_context()
            if session:
                if not context.current_skill and session._current_skill:
                    context.current_skill = session._current_skill
                # Load habit boosts for learned patterns
                if not context.habit_boosts and query:
                    context.habit_boosts = session.get_habit_boost(query)

        # Detect project type and tech stack for context-aware routing
        if not context.project_type:
            from vibesop.core.project_analyzer import ProjectAnalyzer

            analyzer = ProjectAnalyzer(self.project_root)
            profile = analyzer.analyze()
            if profile.project_type:
                context.project_type = profile.project_type
                context.recent_files = profile.tech_stack  # Reuse field for tech stack

        return context
