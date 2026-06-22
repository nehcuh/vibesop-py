"""Tests for RouterContextMixin — context enrichment, memory, session, instinct."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from vibesop.core.matching import RoutingContext
from vibesop.core.models import RoutingResult, SkillRoute
from vibesop.core.routing.context_mixin import RouterContextMixin


class _MockHost(RouterContextMixin):
    """Minimal host satisfying _ContextHost protocol."""

    def __init__(self) -> None:
        self._memory_manager: Any = None
        self._session_context: Any = None
        self._instinct_learner: Any = None
        self._project_analyzer: Any = None
        self._config = MagicMock()
        self._config.session_aware = True
        self.project_root = Path("/tmp/test-project")


class TestGetMemoryManager:
    """Test _get_memory_manager lazy initialization."""

    def test_lazy_init(self) -> None:
        """First call creates MemoryManager; subsequent calls reuse."""
        host = _MockHost()
        with patch("vibesop.core.memory.MemoryManager") as MockMM:
            instance = MockMM.return_value
            mm1 = host._get_memory_manager()
            assert mm1 is instance
            assert host._memory_manager is instance
            MockMM.assert_called_once_with(storage_dir=Path("/tmp/test-project/.vibe/memory"))

    def test_reuse_existing(self) -> None:
        """Existing memory manager is returned without recreation."""
        host = _MockHost()
        mock_mm = MagicMock()
        host._memory_manager = mock_mm
        with patch("vibesop.core.memory.MemoryManager") as MockMM:
            mm = host._get_memory_manager()
            assert mm is mock_mm
            MockMM.assert_not_called()


class TestGetSessionContext:
    """Test _get_session_context lazy initialization."""

    def test_lazy_init(self) -> None:
        """First call loads SessionContext; subsequent calls reuse."""
        host = _MockHost()
        with patch("vibesop.core.sessions.SessionContext.load") as mock_load:
            instance = mock_load.return_value
            ctx1 = host._get_session_context()
            assert ctx1 is instance
            assert host._session_context is instance
            mock_load.assert_called_once_with(
                session_id="default",
                project_root=str(host.project_root),
                router=host,
            )

    def test_reuse_existing(self) -> None:
        """Existing session context is returned without reloading."""
        host = _MockHost()
        mock_ctx = MagicMock()
        host._session_context = mock_ctx
        with patch("vibesop.core.sessions.SessionContext.load") as mock_load:
            ctx = host._get_session_context()
            assert ctx is mock_ctx
            mock_load.assert_not_called()


class TestSaveSessionState:
    """Test _save_session_state persistence and reroute logic."""

    def _make_result(self, skill_id: str = "debug") -> RoutingResult:
        return RoutingResult(
            primary=SkillRoute(skill_id=skill_id, confidence=0.9, layer="keyword"),
            alternatives=[],
            routing_path=["keyword"],
            layer_details=[],
            query="test query",
            duration_ms=10.0,
        )

    def test_session_not_aware_returns_early(self) -> None:
        """When session_aware=False, returns immediately."""
        host = _MockHost()
        host._config.session_aware = False
        result = self._make_result()
        host._save_session_state(result, None)
        # No session context should be accessed
        assert host._session_context is None

    def test_no_match_does_not_set_skill(self) -> None:
        """Result without match does not call set_current_skill."""
        host = _MockHost()
        mock_session = MagicMock()
        mock_session._current_skill = None
        host._session_context = mock_session

        result = RoutingResult(
            primary=None,
            alternatives=[],
            routing_path=[],
            layer_details=[],
            query="test",
            duration_ms=10.0,
        )
        host._save_session_state(result, None)
        mock_session.set_current_skill.assert_not_called()
        mock_session.save.assert_called_once()

    def test_same_skill_no_reroute(self) -> None:
        """Same skill as current → no reroute suggestion."""
        host = _MockHost()
        mock_session = MagicMock()
        mock_session._current_skill = "debug"
        host._session_context = mock_session

        result = self._make_result("debug")
        host._save_session_state(result, None)

        mock_session.set_current_skill.assert_called_once_with("debug")
        mock_session.check_reroute_needed.assert_not_called()
        assert "reroute_suggestion" not in result.primary.metadata

    def test_different_skill_with_reroute(self) -> None:
        """Different skill with reroute suggestion → metadata updated."""
        host = _MockHost()
        mock_session = MagicMock()
        mock_session._current_skill = "plan"
        suggestion = MagicMock()
        suggestion.should_reroute = True
        suggestion.recommended_skill = "debug"
        suggestion.confidence = 0.85
        suggestion.reason = "context shift"
        mock_session.check_reroute_needed.return_value = suggestion
        host._session_context = mock_session

        result = self._make_result("debug")
        host._save_session_state(result, None)

        assert result.primary.metadata["reroute_suggestion"]["from_skill"] == "plan"
        assert result.primary.metadata["reroute_suggestion"]["to_skill"] == "debug"

    def test_different_skill_no_reroute_needed(self) -> None:
        """Different skill but reroute not needed → no metadata update."""
        host = _MockHost()
        mock_session = MagicMock()
        mock_session._current_skill = "plan"
        suggestion = MagicMock()
        suggestion.should_reroute = False
        mock_session.check_reroute_needed.return_value = suggestion
        host._session_context = mock_session

        result = self._make_result("debug")
        host._save_session_state(result, None)

        assert "reroute_suggestion" not in result.primary.metadata

    def test_exception_handling(self) -> None:
        """Exception during save is caught and logged."""
        host = _MockHost()
        mock_session = MagicMock()
        mock_session.set_current_skill.side_effect = OSError("disk full")
        host._session_context = mock_session

        result = self._make_result("debug")
        # Should not raise
        host._save_session_state(result, None)


class TestGetInstinctLearner:
    """Test _get_instinct_learner lazy initialization."""

    def test_lazy_init(self) -> None:
        """First call creates InstinctLearner; subsequent calls reuse."""
        host = _MockHost()
        with patch("vibesop.core.instinct.InstinctLearner") as MockIL:
            instance = MockIL.return_value
            learner1 = host._get_instinct_learner()
            assert learner1 is instance
            assert host._instinct_learner is instance
            MockIL.assert_called_once_with(
                storage_path=Path("/tmp/test-project/.vibe/instincts.jsonl")
            )

    def test_reuse_existing(self) -> None:
        """Existing instinct learner is returned without recreation."""
        host = _MockHost()
        mock_il = MagicMock()
        host._instinct_learner = mock_il
        with patch("vibesop.core.instinct.InstinctLearner") as MockIL:
            learner = host._get_instinct_learner()
            assert learner is mock_il
            MockIL.assert_not_called()


class TestEnrichContext:
    """Test _enrich_context with memory, session, and project analysis."""

    def test_none_context_creates_new(self) -> None:
        """None input creates fresh RoutingContext."""
        host = _MockHost()
        with patch("vibesop.core.memory.MemoryManager") as MockMM:
            mock_mm = MockMM.return_value
            mock_mm.get_active_conversation_id.return_value = None
            with patch("vibesop.core.project_analyzer.ProjectAnalyzer") as MockPA:
                mock_pa = MockPA.return_value
                mock_profile = MagicMock()
                mock_profile.project_type = None
                mock_pa.analyze.return_value = mock_profile
                result = host._enrich_context(None, "test query")

        assert isinstance(result, RoutingContext)

    def test_sets_conversation_id_from_memory(self) -> None:
        """conversation_id set from memory manager's active conversation."""
        host = _MockHost()
        ctx = RoutingContext()
        with patch("vibesop.core.memory.MemoryManager") as MockMM:
            mock_mm = MockMM.return_value
            mock_mm.get_active_conversation_id.return_value = "conv-123"
            mock_mm.get_recent_queries.return_value = []
            with patch("vibesop.core.project_analyzer.ProjectAnalyzer") as MockPA:
                mock_pa = MockPA.return_value
                mock_profile = MagicMock()
                mock_profile.project_type = None
                mock_pa.analyze.return_value = mock_profile
                result = host._enrich_context(ctx, "test")

        assert result.conversation_id == "conv-123"

    def test_loads_recent_queries(self) -> None:
        """recent_queries loaded from memory when conversation_id exists."""
        host = _MockHost()
        ctx = RoutingContext()
        ctx.conversation_id = "conv-456"
        with patch("vibesop.core.memory.MemoryManager") as MockMM:
            mock_mm = MockMM.return_value
            mock_mm.get_recent_queries.return_value = ["q1", "q2"]
            with patch("vibesop.core.project_analyzer.ProjectAnalyzer") as MockPA:
                mock_pa = MockPA.return_value
                mock_profile = MagicMock()
                mock_profile.project_type = None
                mock_pa.analyze.return_value = mock_profile
                result = host._enrich_context(ctx, "test")

        assert result.recent_queries == ["q1", "q2"]

    def test_skips_recent_queries_when_already_set(self) -> None:
        """If recent_queries already populated, memory not queried."""
        host = _MockHost()
        ctx = RoutingContext()
        ctx.conversation_id = "conv-456"
        ctx.recent_queries = ["existing"]
        with patch("vibesop.core.memory.MemoryManager") as MockMM:
            mock_mm = MockMM.return_value
            with patch("vibesop.core.project_analyzer.ProjectAnalyzer") as MockPA:
                mock_pa = MockPA.return_value
                mock_profile = MagicMock()
                mock_profile.project_type = None
                mock_pa.analyze.return_value = mock_profile
                result = host._enrich_context(ctx, "test")

        assert result.recent_queries == ["existing"]
        mock_mm.get_recent_queries.assert_not_called()

    def test_session_aware_loads_current_skill(self) -> None:
        """Session-aware routing loads current_skill from session."""
        host = _MockHost()
        host._config.session_aware = True
        ctx = RoutingContext()
        with patch("vibesop.core.memory.MemoryManager") as MockMM:
            mock_mm = MockMM.return_value
            mock_mm.get_active_conversation_id.return_value = None
            with patch("vibesop.core.sessions.SessionContext.load") as mock_load:
                mock_session = mock_load.return_value
                mock_session._current_skill = "plan"
                mock_session.get_habit_boost.return_value = {}
                with patch("vibesop.core.project_analyzer.ProjectAnalyzer") as MockPA:
                    mock_pa = MockPA.return_value
                    mock_profile = MagicMock()
                    mock_profile.project_type = None
                    mock_pa.analyze.return_value = mock_profile
                    result = host._enrich_context(ctx, "test")

        assert result.current_skill == "plan"

    def test_session_aware_loads_habit_boosts(self) -> None:
        """Session-aware routing loads habit_boosts when query provided."""
        host = _MockHost()
        host._config.session_aware = True
        ctx = RoutingContext()
        with patch("vibesop.core.memory.MemoryManager") as MockMM:
            mock_mm = MockMM.return_value
            mock_mm.get_active_conversation_id.return_value = None
            with patch("vibesop.core.sessions.SessionContext.load") as mock_load:
                mock_session = mock_load.return_value
                mock_session._current_skill = None
                mock_session.get_habit_boost.return_value = {"plan": 0.1}
                with patch("vibesop.core.project_analyzer.ProjectAnalyzer") as MockPA:
                    mock_pa = MockPA.return_value
                    mock_profile = MagicMock()
                    mock_profile.project_type = None
                    mock_pa.analyze.return_value = mock_profile
                    result = host._enrich_context(ctx, "test query")

        assert result.habit_boosts == {"plan": 0.1}

    def test_session_not_aware_skips_session(self) -> None:
        """When session_aware=False, session context is not loaded."""
        host = _MockHost()
        host._config.session_aware = False
        ctx = RoutingContext()
        with patch("vibesop.core.memory.MemoryManager") as MockMM:
            mock_mm = MockMM.return_value
            mock_mm.get_active_conversation_id.return_value = None
            with patch("vibesop.core.sessions.SessionContext.load") as mock_load:
                with patch("vibesop.core.project_analyzer.ProjectAnalyzer") as MockPA:
                    mock_pa = MockPA.return_value
                    mock_profile = MagicMock()
                    mock_profile.project_type = None
                    mock_pa.analyze.return_value = mock_profile
                    host._enrich_context(ctx, "test")

        mock_load.assert_not_called()

    def test_project_analyzer_sets_project_type(self) -> None:
        """ProjectAnalyzer profile with project_type sets context fields."""
        host = _MockHost()
        ctx = RoutingContext()
        with patch("vibesop.core.memory.MemoryManager") as MockMM:
            mock_mm = MockMM.return_value
            mock_mm.get_active_conversation_id.return_value = None
            with patch("vibesop.core.project_analyzer.ProjectAnalyzer") as MockPA:
                mock_pa = MockPA.return_value
                mock_profile = MagicMock()
                mock_profile.project_type = "python"
                mock_profile.tech_stack = ["django", "pytest"]
                mock_pa.analyze.return_value = mock_profile
                result = host._enrich_context(ctx, "test")

        assert result.project_type == "python"
        assert result.recent_files == ["django", "pytest"]

    def test_skips_analyzer_when_project_type_set(self) -> None:
        """If project_type already set, analyzer is not invoked."""
        host = _MockHost()
        ctx = RoutingContext()
        ctx.project_type = "rust"
        with patch("vibesop.core.memory.MemoryManager") as MockMM:
            mock_mm = MockMM.return_value
            mock_mm.get_active_conversation_id.return_value = None
            with patch("vibesop.core.project_analyzer.ProjectAnalyzer") as MockPA:
                result = host._enrich_context(ctx, "test")

        MockPA.assert_not_called()
        assert result.project_type == "rust"

    def test_reuses_existing_project_analyzer(self) -> None:
        """Existing ProjectAnalyzer instance is reused."""
        host = _MockHost()
        mock_pa = MagicMock()
        mock_profile = MagicMock()
        mock_profile.project_type = None
        mock_pa.analyze.return_value = mock_profile
        host._project_analyzer = mock_pa
        ctx = RoutingContext()

        with patch("vibesop.core.memory.MemoryManager") as MockMM:
            mock_mm = MockMM.return_value
            mock_mm.get_active_conversation_id.return_value = None
            with patch("vibesop.core.project_analyzer.ProjectAnalyzer") as MockPA:
                host._enrich_context(ctx, "test")

        MockPA.assert_not_called()
        mock_pa.analyze.assert_called_once()
