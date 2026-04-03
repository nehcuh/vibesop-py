"""Instinct management system.

This module provides adaptive decision-making capabilities
based on learned patterns and heuristics.
"""

import json
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from collections import defaultdict


class ActionType(Enum):
    """Types of actions that can be recommended.

    Attributes:
        USE_SKILL: Use a specific skill
        ROUTE_TO_LLM: Route to LLM for processing
        SKIP_STEP: Skip the current step
        ASK_USER: Ask user for input
    """
    USE_SKILL = "use_skill"
    ROUTE_TO_LLM = "route_to_llm"
    SKIP_STEP = "skip_step"
    ASK_USER = "ask_user"


class ConfidenceLevel(Enum):
    """Confidence levels for decisions.

    Attributes:
        VERY_LOW: Very low confidence
        LOW: Low confidence
        MEDIUM: Medium confidence
        HIGH: High confidence
        VERY_HIGH: Very high confidence
    """
    VERY_LOW = "very_low"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


@dataclass
class DecisionContext:
    """Context for making a decision.

    Attributes:
        situation_type: Type of situation
        user_goal: User's goal
        recent_history: Recent actions taken
        success_rate: Historical success rate (0-1)
        time_pressure: Time pressure (0-1)
        complexity: Complexity of task (0-1)
    """
    situation_type: str
    user_goal: str
    recent_history: List[str]
    success_rate: float
    time_pressure: float
    complexity: float


@dataclass
class Decision:
    """A decision made by the instinct manager.

    Attributes:
        decision_id: Unique decision identifier
        action_type: Recommended action type
        target: Target (skill name, etc.)
        confidence: Confidence level
        reason: Reason for this decision
        context: Decision context
        outcome: Outcome of the decision
        timestamp: When the decision was made
    """
    decision_id: str
    action_type: ActionType
    target: Optional[str]
    confidence: ConfidenceLevel
    reason: str
    context: DecisionContext
    outcome: Optional[str]
    timestamp: str


@dataclass
class Pattern:
    """A learned pattern for decision-making.

    Attributes:
        pattern_id: Unique pattern identifier
        situation_type: Type of situation
        user_goal: User goal
        action_type: Recommended action
        target: Target for the action
        success_count: Number of successes
        failure_count: Number of failures
        confidence: Confidence in this pattern
        created_at: Creation timestamp
        last_used: Last time this pattern was used
    """
    pattern_id: str
    situation_type: str
    user_goal: str
    action_type: str
    target: Optional[str]
    success_count: int
    failure_count: int
    confidence: float
    created_at: str
    last_used: Optional[str]


class InstinctManager:
    """Manage instinct-based decision-making.

    Provides adaptive decision-making based on learned patterns
    and heuristics for handling different situations.

    Example:
        >>> manager = InstinctManager()
        >>> context = DecisionContext(...)
        >>> decision = manager.decide(context)
        >>> manager.record_outcome(decision, success=True, outcome="Worked")
    """

    def __init__(self, storage_dir: Optional[Path] = None) -> None:
        """Initialize the instinct manager.

        Args:
            storage_dir: Directory for pattern storage
        """
        self._storage_dir = storage_dir or Path.cwd() / ".vibe" / "instincts"
        self._storage_dir.mkdir(parents=True, exist_ok=True)

        self._patterns: Dict[str, Pattern] = {}
        self._decisions: List[Decision] = []

        # Load existing patterns
        self._load_patterns()

    def decide(
        self,
        context: DecisionContext,
        available_actions: Optional[List[Dict[str, Any]]] = None,
    ) -> Decision:
        """Make a decision based on context.

        Args:
            context: Decision context
            available_actions: Available actions to choose from

        Returns:
            Decision object
        """
        decision_id = str(uuid.uuid4())

        # Try to find matching pattern
        pattern = self._find_matching_pattern(context)

        if pattern and pattern.confidence > 0.5:
            # Use pattern-based decision
            action_type = ActionType(pattern.action_type)
            confidence = self._get_confidence_from_score(pattern.confidence)
            reason = f"Based on learned pattern (confidence: {pattern.confidence:.2f})"

            # Update last used
            pattern.last_used = datetime.now().isoformat()
            self._save_pattern(pattern)
        else:
            # Use heuristic decision
            action_type, confidence, reason = self._heuristic_decide(context)

        decision = Decision(
            decision_id=decision_id,
            action_type=action_type,
            target=pattern.target if pattern else None,
            confidence=confidence,
            reason=reason,
            context=context,
            outcome=None,
            timestamp=datetime.now().isoformat(),
        )

        self._decisions.append(decision)
        return decision

    def record_outcome(
        self,
        decision: Decision,
        success: bool,
        outcome: Optional[str] = None,
    ) -> None:
        """Record the outcome of a decision.

        Args:
            decision: The decision that was made
            success: Whether the decision was successful
            outcome: Optional outcome description
        """
        decision.outcome = outcome or ("Success" if success else "Failure")

        # Find and update pattern
        pattern = self._find_matching_pattern(decision.context)
        if pattern:
            if success:
                pattern.success_count += 1
            else:
                pattern.failure_count += 1

            # Recalculate confidence
            total = pattern.success_count + pattern.failure_count
            if total > 0:
                pattern.confidence = pattern.success_count / total

            self._save_pattern(pattern)

        # Save decision history
        self._save_decision_history()

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about decisions and patterns.

        Returns:
            Statistics dictionary
        """
        total_decisions = len(self._decisions)
        successful = sum(1 for d in self._decisions if d.outcome and "Success" in d.outcome)

        overall_success_rate = successful / total_decisions if total_decisions > 0 else 0.0

        return {
            "total_patterns": len(self._patterns),
            "total_decisions": total_decisions,
            "overall_success_rate": overall_success_rate,
            "decisions_by_action": self._count_by_action(),
        }

    def learn_from_history(
        self,
        history: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Learn patterns from historical data.

        Args:
            history: List of historical decision records

        Returns:
            Result dictionary
        """
        result = {
            "success": True,
            "patterns_created": 0,
            "patterns_updated": 0,
            "errors": [],
        }

        # Group by situation
        situations = defaultdict(list)
        for record in history:
            if "context" in record and "action_type" in record:
                key = (
                    record["context"].get("situation_type", ""),
                    record["context"].get("user_goal", ""),
                    record.get("action_type", ""),
                    record.get("target", ""),
                )
                situations[key].append(record)

        # Create or update patterns
        for key, records in situations.items():
            situation_type, user_goal, action_type, target = key

            successes = sum(1 for r in records if r.get("success", False))
            failures = len(records) - successes
            confidence = successes / len(records) if records else 0

            # Only create patterns for reasonably successful actions
            if confidence >= 0.6 and len(records) >= 3:
                pattern_id = f"{situation_type}_{user_goal}_{action_type}"
                pattern_id = pattern_id.replace(" ", "_").lower()

                if pattern_id in self._patterns:
                    # Update existing
                    pattern = self._patterns[pattern_id]
                    pattern.success_count = successes
                    pattern.failure_count = failures
                    pattern.confidence = confidence
                    result["patterns_updated"] += 1
                else:
                    # Create new
                    pattern = Pattern(
                        pattern_id=pattern_id,
                        situation_type=situation_type,
                        user_goal=user_goal,
                        action_type=action_type,
                        target=target,
                        success_count=successes,
                        failure_count=failures,
                        confidence=confidence,
                        created_at=datetime.now().isoformat(),
                        last_used=None,
                    )
                    self._patterns[pattern_id] = pattern
                    result["patterns_created"] += 1

                self._save_pattern(pattern)

        return result

    def _find_matching_pattern(self, context: DecisionContext) -> Optional[Pattern]:
        """Find a pattern matching the context.

        Args:
            context: Decision context

        Returns:
            Matching pattern or None
        """
        matches = []

        for pattern in self._patterns.values():
            # Check situation type match
            if pattern.situation_type.lower() in context.situation_type.lower():
                matches.append(pattern)
                continue

            # Check user goal match
            if pattern.user_goal.lower() in context.user_goal.lower():
                matches.append(pattern)

        # Return best match (highest confidence)
        if matches:
            return max(matches, key=lambda p: p.confidence)

        return None

    def _heuristic_decide(
        self,
        context: DecisionContext,
    ) -> tuple[ActionType, ConfidenceLevel, str]:
        """Make heuristic-based decision.

        Args:
            context: Decision context

        Returns:
            Tuple of (action_type, confidence, reason)
        """
        # High time pressure -> skip optional steps
        if context.time_pressure > 0.8:
            return (
                ActionType.SKIP_STEP,
                ConfidenceLevel.HIGH,
                "High time pressure - skipping optional step",
            )

        # High complexity -> ask user
        if context.complexity > 0.8:
            return (
                ActionType.ASK_USER,
                ConfidenceLevel.MEDIUM,
                "High complexity - requesting user guidance",
            )

        # Good success rate -> use LLM
        if context.success_rate > 0.7:
            return (
                ActionType.ROUTE_TO_LLM,
                ConfidenceLevel.MEDIUM,
                "Good historical success rate - using LLM",
            )

        # Low success rate -> ask user
        if context.success_rate < 0.4:
            return (
                ActionType.ASK_USER,
                ConfidenceLevel.HIGH,
                "Low success rate - requesting user input",
            )

        # Default
        return (
            ActionType.ROUTE_TO_LLM,
            ConfidenceLevel.LOW,
            "No specific pattern - default to LLM",
        )

    def _get_confidence_from_score(self, score: float) -> ConfidenceLevel:
        """Convert confidence score to ConfidenceLevel.

        Args:
            score: Confidence score (0-1)

        Returns:
            ConfidenceLevel enum
        """
        if score >= 0.9:
            return ConfidenceLevel.VERY_HIGH
        elif score >= 0.7:
            return ConfidenceLevel.HIGH
        elif score >= 0.5:
            return ConfidenceLevel.MEDIUM
        elif score >= 0.3:
            return ConfidenceLevel.LOW
        else:
            return ConfidenceLevel.VERY_LOW

    def _count_by_action(self) -> Dict[str, int]:
        """Count decisions by action type.

        Returns:
            Dictionary of action counts
        """
        counts = defaultdict(int)
        for decision in self._decisions:
            counts[decision.action_type.value] += 1
        return dict(counts)

    def _save_pattern(self, pattern: Pattern) -> None:
        """Save pattern to storage.

        Args:
            pattern: Pattern to save
        """
        pattern_file = self._storage_dir / f"{pattern.pattern_id}.json"

        data = {
            "pattern_id": pattern.pattern_id,
            "situation_type": pattern.situation_type,
            "user_goal": pattern.user_goal,
            "action_type": pattern.action_type,
            "target": pattern.target,
            "success_count": pattern.success_count,
            "failure_count": pattern.failure_count,
            "confidence": pattern.confidence,
            "created_at": pattern.created_at,
            "last_used": pattern.last_used,
        }

        with open(pattern_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _load_patterns(self) -> None:
        """Load patterns from storage."""
        if not self._storage_dir.exists():
            return

        for pattern_file in self._storage_dir.glob("*.json"):
            try:
                with open(pattern_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                pattern = Pattern(
                    pattern_id=data["pattern_id"],
                    situation_type=data["situation_type"],
                    user_goal=data["user_goal"],
                    action_type=data["action_type"],
                    target=data.get("target"),
                    success_count=data["success_count"],
                    failure_count=data["failure_count"],
                    confidence=data["confidence"],
                    created_at=data["created_at"],
                    last_used=data.get("last_used"),
                )

                # Prune low-confidence patterns
                if pattern.confidence >= 0.3:
                    self._patterns[pattern.pattern_id] = pattern

            except Exception:
                # Skip invalid pattern files
                continue

    def _save_decision_history(self) -> None:
        """Save decision history to storage."""
        history_file = self._storage_dir / "decisions.json"

        data = [
            {
                "decision_id": d.decision_id,
                "action_type": d.action_type.value,
                "target": d.target,
                "confidence": d.confidence.value,
                "reason": d.reason,
                "context": {
                    "situation_type": d.context.situation_type,
                    "user_goal": d.context.user_goal,
                    "recent_history": d.context.recent_history,
                    "success_rate": d.context.success_rate,
                    "time_pressure": d.context.time_pressure,
                    "complexity": d.context.complexity,
                },
                "outcome": d.outcome,
                "timestamp": d.timestamp,
            }
            for d in self._decisions
        ]

        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
