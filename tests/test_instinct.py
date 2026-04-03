"""Tests for instinct management system."""

import pytest
import tempfile
from pathlib import Path
import uuid
from datetime import datetime

from vibesop.workflow.instinct import (
    InstinctManager,
    Decision,
    DecisionContext,
    Pattern,
    ActionType,
    ConfidenceLevel,
)


class TestActionType:
    """Test ActionType enum."""

    def test_action_type_values(self) -> None:
        """Test action type enum values."""
        assert ActionType.USE_SKILL.value == "use_skill"
        assert ActionType.ROUTE_TO_LLM.value == "route_to_llm"
        assert ActionType.SKIP_STEP.value == "skip_step"


class TestConfidenceLevel:
    """Test ConfidenceLevel enum."""

    def test_confidence_values(self) -> None:
        """Test confidence level enum values."""
        assert ConfidenceLevel.VERY_LOW.value == "very_low"
        assert ConfidenceLevel.LOW.value == "low"
        assert ConfidenceLevel.MEDIUM.value == "medium"
        assert ConfidenceLevel.HIGH.value == "high"
        assert ConfidenceLevel.VERY_HIGH.value == "very_high"


class TestDecisionContext:
    """Test DecisionContext dataclass."""

    def test_create_context(self) -> None:
        """Test creating a decision context."""
        context = DecisionContext(
            situation_type="code_review",
            user_goal="improve_code_quality",
            recent_history=["used_linter"],
            success_rate=0.8,
            time_pressure=0.5,
            complexity=0.6,
        )

        assert context.situation_type == "code_review"
        assert context.success_rate == 0.8


class TestDecision:
    """Test Decision dataclass."""

    def test_create_decision(self) -> None:
        """Test creating a decision."""
        context = DecisionContext(
            situation_type="test",
            user_goal="test",
            recent_history=[],
            success_rate=0.5,
            time_pressure=0.5,
            complexity=0.5,
        )

        decision = Decision(
            decision_id=str(uuid.uuid4()),
            action_type=ActionType.USE_SKILL,
            target="gstack/review",
            confidence=ConfidenceLevel.HIGH,
            reason="Test decision",
            context=context,
            outcome=None,
            timestamp=datetime.now().isoformat(),
        )

        assert decision.action_type == ActionType.USE_SKILL
        assert decision.target == "gstack/review"


class TestInstinctManager:
    """Test InstinctManager functionality."""

    def test_create_manager(self) -> None:
        """Test creating manager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = InstinctManager(storage_dir=Path(tmpdir))
            assert manager is not None

    def test_decide_heuristic(self) -> None:
        """Test heuristic decision making."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = InstinctManager(storage_dir=Path(tmpdir))

            context = DecisionContext(
                situation_type="general",
                user_goal="complete_task",
                recent_history=[],
                success_rate=0.9,
                time_pressure=0.3,
                complexity=0.4,
            )

            decision = manager.decide(context)

            assert decision is not None
            assert isinstance(decision.action_type, ActionType)
            assert isinstance(decision.confidence, ConfidenceLevel)

    def test_decide_high_time_pressure(self) -> None:
        """Test decision with high time pressure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = InstinctManager(storage_dir=Path(tmpdir))

            context = DecisionContext(
                situation_type="urgent",
                user_goal="quick_fix",
                recent_history=[],
                success_rate=0.7,
                time_pressure=0.9,  # High time pressure
                complexity=0.3,
            )

            decision = manager.decide(context)

            # Should suggest skipping
            assert decision.action_type == ActionType.SKIP_STEP

    def test_decide_high_complexity(self) -> None:
        """Test decision with high complexity."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = InstinctManager(storage_dir=Path(tmpdir))

            context = DecisionContext(
                situation_type="complex",
                user_goal="solve_problem",
                recent_history=[],
                success_rate=0.7,
                time_pressure=0.4,
                complexity=0.9,  # High complexity
            )

            decision = manager.decide(context)

            # Should ask user
            assert decision.action_type == ActionType.ASK_USER

    def test_record_outcome(self) -> None:
        """Test recording decision outcome."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = InstinctManager(storage_dir=Path(tmpdir))

            context = DecisionContext(
                situation_type="test",
                user_goal="test",
                recent_history=[],
                success_rate=0.5,
                time_pressure=0.5,
                complexity=0.5,
            )

            decision = Decision(
                decision_id=str(uuid.uuid4()),
                action_type=ActionType.USE_SKILL,
                target="test_skill",
                confidence=ConfidenceLevel.MEDIUM,
                reason="Test",
                context=context,
                outcome=None,
                timestamp=datetime.now().isoformat(),
            )

            # Record outcome
            manager.record_outcome(decision, success=True, outcome="Worked correctly")

            assert decision.outcome == "Worked correctly"

    def test_statistics(self) -> None:
        """Test getting statistics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = InstinctManager(storage_dir=Path(tmpdir))

            stats = manager.get_statistics()

            assert "total_patterns" in stats
            assert "total_decisions" in stats
            assert "overall_success_rate" in stats

    def test_learn_from_history(self) -> None:
        """Test learning from history."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = InstinctManager(storage_dir=Path(tmpdir))

            # Create mock history
            history = [
                {
                    "context": {
                        "situation_type": "code_review",
                        "user_goal": "improve_quality",
                        "success_rate": 0.8,
                    },
                    "action_type": "use_skill",
                    "target": "gstack/review",
                    "success": True,
                },
                {
                    "context": {
                        "situation_type": "code_review",
                        "user_goal": "improve_quality",
                        "success_rate": 0.8,
                    },
                    "action_type": "use_skill",
                    "target": "gstack/review",
                    "success": True,
                },
                {
                    "context": {
                        "situation_type": "code_review",
                        "user_goal": "improve_quality",
                        "success_rate": 0.8,
                    },
                    "action_type": "use_skill",
                    "target": "gstack/review",
                    "success": True,
                },
            ]

            result = manager.learn_from_history(history)

            assert result["success"]
            assert result["patterns_created"] > 0

    def test_pattern_pruning(self) -> None:
        """Test automatic pattern pruning."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = InstinctManager(storage_dir=Path(tmpdir))

            # Create a pattern with low success rate
            context = DecisionContext(
                situation_type="test",
                user_goal="test",
                recent_history=[],
                success_rate=0.5,
                time_pressure=0.5,
                complexity=0.5,
            )

            decision = Decision(
                decision_id=str(uuid.uuid4()),
                action_type=ActionType.USE_SKILL,
                target="test",
                confidence=ConfidenceLevel.MEDIUM,
                reason="Test",
                context=context,
                outcome=None,
                timestamp=datetime.now().isoformat(),
            )

            # Record many failures
            for _ in range(10):
                manager.record_outcome(decision, success=False)

            # Prune patterns (should remove low-success patterns)
            stats_before = manager.get_statistics()["total_patterns"]

            # Trigger pruning by learning again
            manager.learn_from_history([])

            stats_after = manager.get_statistics()["total_patterns"]

            # Pattern should be pruned
            assert stats_after <= stats_before
