"""RALPLAN-DR structured deliberation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RalplanDR:
    """RALPLAN-DR deliberation structure.

    Principles: What principles guide this decision?
    Decision Drivers: What factors matter most?
    Viable Options: List of viable approaches (no strawmen)
    """

    principles: list[str] = field(default_factory=list)
    decision_drivers: list[str] = field(default_factory=list)
    viable_options: list[dict[str, Any]] = field(default_factory=list)
    favored_option: str | None = None
    rationale: str = ""

    def add_option(self, name: str, description: str, pros: list[str], cons: list[str]) -> None:
        self.viable_options.append(
            {
                "name": name,
                "description": description,
                "pros": pros,
                "cons": cons,
            }
        )

    def select_favored(self, name: str, rationale: str) -> None:
        if any(o["name"] == name for o in self.viable_options):
            self.favored_option = name
            self.rationale = rationale

    def to_dict(self) -> dict[str, Any]:
        return {
            "principles": self.principles,
            "decision_drivers": self.decision_drivers,
            "viable_options": self.viable_options,
            "favored_option": self.favored_option,
            "rationale": self.rationale,
        }
