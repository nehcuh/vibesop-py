"""Mathematical ambiguity scoring for deep-interview."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DimensionScore:
    score: float
    evidence: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


@dataclass
class AmbiguityResult:
    intent: DimensionScore
    outcome: DimensionScore
    scope: DimensionScore
    constraints: DimensionScore
    success: DimensionScore

    @property
    def ambiguity(self) -> float:
        return 1.0 - (
            self.intent.score * 0.30
            + self.outcome.score * 0.25
            + self.scope.score * 0.20
            + self.constraints.score * 0.15
            + self.success.score * 0.10
        )

    @property
    def clarity(self) -> float:
        return 1.0 - self.ambiguity

    def weakest_dimension(self) -> str:
        scores = {
            "intent": self.intent.score,
            "outcome": self.outcome.score,
            "scope": self.scope.score,
            "constraints": self.constraints.score,
            "success": self.success.score,
        }
        return min(scores, key=scores.get)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ambiguity": round(self.ambiguity, 4),
            "clarity": round(self.clarity, 4),
            "intent": {
                "score": self.intent.score,
                "evidence": self.intent.evidence,
                "missing": self.intent.missing,
            },
            "outcome": {
                "score": self.outcome.score,
                "evidence": self.outcome.evidence,
                "missing": self.outcome.missing,
            },
            "scope": {
                "score": self.scope.score,
                "evidence": self.scope.evidence,
                "missing": self.scope.missing,
            },
            "constraints": {
                "score": self.constraints.score,
                "evidence": self.constraints.evidence,
                "missing": self.constraints.missing,
            },
            "success": {
                "score": self.success.score,
                "evidence": self.success.evidence,
                "missing": self.success.missing,
            },
            "weakest": self.weakest_dimension(),
        }


WEIGHTS = {
    "intent": 0.30,
    "outcome": 0.25,
    "scope": 0.20,
    "constraints": 0.15,
    "success": 0.10,
}


def compute_ambiguity(
    intent: DimensionScore,
    outcome: DimensionScore,
    scope: DimensionScore,
    constraints: DimensionScore,
    success: DimensionScore,
) -> AmbiguityResult:
    return AmbiguityResult(
        intent=intent,
        outcome=outcome,
        scope=scope,
        constraints=constraints,
        success=success,
    )
