"""Critic evaluation of plan."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CriticEvaluation:
    """Critic evaluation of a plan."""

    principle_consistent: bool = True
    tasks_simulated: list[dict[str, Any]] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    @property
    def passes(self) -> bool:
        return self.principle_consistent and not self.violations

    def to_dict(self) -> dict[str, Any]:
        return {
            "principle_consistent": self.principle_consistent,
            "passes": self.passes,
            "violations": self.violations,
            "suggestions": self.suggestions,
            "tasks_simulated": self.tasks_simulated,
        }
