"""Pre-execution gate for ralplan."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ExecutionGate:
    """Pre-execution gate decision."""

    passed: bool
    plan_name: str
    plan_path: str
    review_iterations: int
    architect_approved: bool
    critic_passed: bool
    user_approved: bool
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    notes: str = ""

    @property
    def is_ready(self) -> bool:
        return self.passed and self.architect_approved and self.critic_passed and self.user_approved

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "plan_name": self.plan_name,
            "plan_path": self.plan_path,
            "review_iterations": self.review_iterations,
            "architect_approved": self.architect_approved,
            "critic_passed": self.critic_passed,
            "user_approved": self.user_approved,
            "timestamp": self.timestamp,
            "notes": self.notes,
            "is_ready": self.is_ready,
        }
