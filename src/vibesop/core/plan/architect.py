"""Architect review — steelman antithesis."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ArchitectReview:
    """Architect review of a plan."""

    antithesis: str = ""
    risks: list[str] = field(default_factory=list)
    trade_offs: list[str] = field(default_factory=list)
    hidden_costs: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "antithesis": self.antithesis,
            "risks": self.risks,
            "trade_offs": self.trade_offs,
            "hidden_costs": self.hidden_costs,
            "recommendations": self.recommendations,
        }
