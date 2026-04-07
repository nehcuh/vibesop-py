"""Skill execution utility for CLI commands.

This module provides skill execution functionality isolated from
the core routing engine. It exists only for CLI convenience.

⚠️ POSITIONING: VibeSOP is a ROUTING ENGINE, not an execution engine.
This module is NOT part of VibeSOP's core functionality.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from vibesop.core.skills.base import SkillContext, SkillResult
from vibesop.core.skills.loader import SkillLoader

logger = logging.getLogger(__name__)


async def execute_skill(
    skill_id: str,
    query: str,
    working_dir: str | Path,
    **metadata: Any,
) -> SkillResult:
    """Execute a skill by ID.

    ⚠️ This is a CLI convenience function, NOT part of VibeSOP's core.
    For routing (discovery), use UnifiedRouter instead.

    Args:
        skill_id: Skill identifier
        query: User's query/request
        working_dir: Working directory for execution
        **metadata: Additional metadata

    Returns:
        Skill execution result
    """
    work_path = Path(working_dir).resolve()

    context = SkillContext(
        query=query,
        working_dir=work_path,
        metadata=metadata,
    )

    # Load the skill
    loader = SkillLoader(project_root=work_path)
    skill = loader.instantiate(skill_id)

    if not skill:
        return SkillResult(
            success=False,
            output="",
            error=f"Skill not found: {skill_id}",
        )

    if not skill.validate_context(context):
        return SkillResult(
            success=False,
            output="",
            error="Invalid context for skill execution",
        )

    # Execute the skill
    result = await skill.execute(context)

    # Auto-record successful skill executions for preference learning
    if result.success:
        _auto_record_selection(skill_id, query, work_path)

    return result


def _auto_record_selection(
    skill_id: str,
    query: str,
    project_root: Path,
) -> None:
    """Automatically record skill selection for preference learning.

    This method is called after every successful skill execution to
    build a preference history that improves routing accuracy over time.

    Args:
        skill_id: The skill that was executed
        query: The original query that triggered the skill
        project_root: Project root directory for preference storage
    """
    try:
        from vibesop.core.preference import PreferenceLearner

        preference_path = project_root / ".vibe" / "preferences.json"
        learner = PreferenceLearner(
            storage_path=preference_path,
            decay_days=30,
            min_samples=3,
        )

        learner.record_selection(skill_id, query, was_helpful=True)

    except Exception as e:
        # Silently fail - auto-recording should never break skill execution
        logger.debug(f"Failed to record preference for {skill_id}: {e}")
