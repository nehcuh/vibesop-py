"""Interview stage management for deep-interview workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class InterviewStage(str, Enum):
    PREFLIGHT = "preflight"
    CONTEXT_SNAPSHOT = "context_snapshot"
    TYPE_DETECTION = "type_detection"
    INTERVIEW = "interview"
    CHALLENGE = "challenge"
    CRYSTALLIZE = "crystallize"
    HANDOFF = "handoff"


@dataclass
class InterviewQuestion:
    dimension: str
    question: str
    round_number: int
    follow_up: bool = False
    challenge_mode: str | None = None


@dataclass
class InterviewAnswer:
    question: InterviewQuestion
    answer: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class InterviewState:
    stage: InterviewStage = InterviewStage.PREFLIGHT
    profile: str = "standard"
    threshold: float = 0.2
    current_ambiguity: float = 1.0
    round_number: int = 0
    max_rounds: int = 12
    questions: list[InterviewQuestion] = field(default_factory=list)
    answers: list[InterviewAnswer] = field(default_factory=list)
    task_description: str = ""
    project_type: str = "unknown"

    @property
    def is_complete(self) -> bool:
        return self.current_ambiguity <= self.threshold or self.round_number >= self.max_rounds

    @property
    def needs_challenge(self) -> bool:
        return self.round_number >= 2 and self.current_ambiguity > self.threshold

    def next_challenge_mode(self) -> str:
        if self.round_number >= 5:
            return "ontologist"
        if self.round_number >= 4:
            return "simplifier"
        return "contrarian"

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage.value,
            "profile": self.profile,
            "threshold": self.threshold,
            "current_ambiguity": round(self.current_ambiguity, 4),
            "round_number": self.round_number,
            "max_rounds": self.max_rounds,
            "task_description": self.task_description,
            "project_type": self.project_type,
            "question_count": len(self.questions),
            "answer_count": len(self.answers),
            "is_complete": self.is_complete,
        }
