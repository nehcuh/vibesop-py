"""Compatibility shim — re-exports from vibesop.core.skills.evaluator.

This module previously contained the evaluator implementation.
It has been moved to vibesop.core.skills.evaluator to align with
the project structure defined in the skill governance plan.

New code should import from vibesop.core.skills.evaluator directly.
"""

from vibesop.core.skills.evaluator import RoutingEvaluator, SkillEvaluation

__all__ = ["RoutingEvaluator", "SkillEvaluation"]
