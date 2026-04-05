"""Skill activation for automatic trigger response.

This module provides automatic skill and workflow activation
based on detected user intent from keyword patterns.
"""

import logging
from typing import Optional, Dict, Any
from pathlib import Path

from vibesop.triggers.models import TriggerPattern, PatternMatch
from vibesop.core.skills.manager import SkillManager
from vibesop.core.routing.engine import SkillRouter, RoutingRequest
from vibesop.workflow import WorkflowManager

logger = logging.getLogger(__name__)


class _NullRouter:
    """Fallback router that returns None for all requests."""

    def route(self, *args: Any, **kwargs: Any) -> None:
        return None


class SkillActivator:
    """Activate skills and workflows based on pattern matches.

    Bridges the gap between keyword detection and skill/workflow execution.
    Provides automatic activation with fallback and error handling.

    Attributes:
        skill_manager: SkillManager instance for skill execution
        router: SkillRouter for semantic skill routing
        workflow_manager: WorkflowManager for workflow execution
        project_root: Project root path

    Example:
        >>> from vibesop.triggers import SkillActivator, KeywordDetector, DEFAULT_PATTERNS
        >>> detector = KeywordDetector(patterns=DEFAULT_PATTERNS)
        >>> activator = SkillActivator(project_root=".")
        >>> match = detector.detect_best("scan for security issues")
        >>> result = activator.activate(match, input_data={"target": "./src"})
    """

    def __init__(
        self,
        project_root: Path = Path("."),
        skill_manager: Optional[SkillManager] = None,
        router: Optional[SkillRouter] = None,
        workflow_manager: Optional[WorkflowManager] = None,
    ):
        """Initialize skill activator.

        Args:
            project_root: Project root directory
            skill_manager: Optional SkillManager instance (created if None)
            router: Optional SkillRouter instance (created if None)
            workflow_manager: Optional WorkflowManager instance (created if None)
        """
        self.project_root = Path(project_root).resolve()

        self.skill_manager = skill_manager or SkillManager(self.project_root)

        if router is not None:
            self.router = router
        else:
            try:
                self.router = SkillRouter(self.project_root)
            except Exception:
                logger.warning("Router initialization failed, using null router")
                self.router = _NullRouter()

        self.workflow_manager = workflow_manager or WorkflowManager(project_root=self.project_root)

    async def activate(
        self,
        match: PatternMatch,
        input_data: Optional[Dict[str, Any]] = None,
        pattern: Optional[TriggerPattern] = None,
    ) -> Dict[str, Any]:
        """Activate skill or workflow based on pattern match.

        Args:
            match: Pattern match from KeywordDetector
            input_data: Input data for skill/workflow execution
            pattern: Optional TriggerPattern for additional context

        Returns:
            Execution result dict with keys:
                - success: bool
                - action: "skill" | "workflow" | "none"
                - result: Execution result or None
                - error: Error message if failed

        Example:
            >>> match = detector.detect_best("scan security")
            >>> result = await activator.activate(match)
            >>> print(result["action"])  # "skill" or "workflow"
        """
        if not match:
            return {
                "success": False,
                "action": "none",
                "result": None,
                "error": "No pattern match provided",
            }

        input_data = input_data or {}

        # Try to find the pattern
        if pattern is None:
            # Pattern not provided, extract from match
            # We'll need to look it up by pattern_id
            from vibesop.triggers import DEFAULT_PATTERNS

            pattern = next((p for p in DEFAULT_PATTERNS if p.pattern_id == match.pattern_id), None)

        if not pattern:
            return {
                "success": False,
                "action": "none",
                "result": None,
                "error": f"Pattern not found: {match.pattern_id}",
            }

        # Priority: Workflow > Skill
        # 1. Try workflow if specified
        if pattern.workflow_id:
            return await self._activate_workflow(pattern, match, input_data)

        # 2. Try skill activation
        return await self._activate_skill(pattern, match, input_data)

    async def _activate_workflow(
        self, pattern: TriggerPattern, match: PatternMatch, input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Activate workflow based on pattern.

        Args:
            pattern: Trigger pattern with workflow_id
            match: Pattern match
            input_data: Input data for workflow

        Returns:
            Execution result dict
        """
        try:
            # Execute workflow
            result = await self.workflow_manager.execute_workflow(
                pattern.workflow_id or "",
                input_data,
            )

            return {
                "success": result.success,
                "action": "workflow",
                "result": result,
                "pattern_id": pattern.pattern_id,
                "workflow_id": pattern.workflow_id,
            }

        except Exception as e:
            return {
                "success": False,
                "action": "workflow",
                "result": None,
                "error": str(e),
                "pattern_id": pattern.pattern_id,
                "workflow_id": pattern.workflow_id,
            }

    async def _activate_skill(
        self, pattern: TriggerPattern, match: PatternMatch, input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Activate skill based on pattern.

        Args:
            pattern: Trigger pattern with skill_id
            match: Pattern match
            input_data: Input data for skill

        Returns:
            Execution result dict
        """
        try:
            skill_id = pattern.skill_id

            # Format query from pattern and match
            query = self._format_query(pattern, match, input_data)

            # Execute skill via SkillManager
            result = await self.skill_manager.execute_skill(
                skill_id, query=query, context=input_data
            )

            return {
                "success": True,
                "action": "skill",
                "result": result,
                "pattern_id": pattern.pattern_id,
                "skill_id": skill_id,
            }

        except Exception as e:
            # Try fallback via router
            return await self._fallback_to_router(pattern, match, input_data, str(e))

    async def _fallback_to_router(
        self, pattern: TriggerPattern, match: PatternMatch, input_data: Dict[str, Any], error: str
    ) -> Dict[str, Any]:
        """Fallback to semantic routing if direct skill activation fails.

        Args:
            pattern: Trigger pattern
            match: Pattern match
            input_data: Input data
            error: Original error message

        Returns:
            Execution result dict
        """
        try:
            # Create routing request
            query = self._format_query(pattern, match, input_data)
            request = RoutingRequest(query=query, context=input_data)

            # Route to best skill
            route = self.router.route(request)

            if not route or not route.primary or not hasattr(route, "primary"):
                return {
                    "success": False,
                    "action": "none",
                    "result": None,
                    "error": f"Skill activation failed and no route found: {error}",
                    "pattern_id": pattern.pattern_id,
                }

            # Execute routed skill
            result = await self.skill_manager.execute_skill(
                route.primary.skill_id, query=query, context=input_data
            )

            return {
                "success": True,
                "action": "skill",
                "result": result,
                "pattern_id": pattern.pattern_id,
                "skill_id": route.primary.skill_id,
                "routed": True,
            }

        except Exception:
            return {
                "success": False,
                "action": "none",
                "result": None,
                "error": f"Skill activation and routing both failed: {error}",
                "pattern_id": pattern.pattern_id,
            }

    def _format_query(
        self, pattern: TriggerPattern, match: PatternMatch, input_data: Dict[str, Any]
    ) -> str:
        """Format query for skill execution.

        Args:
            pattern: Trigger pattern
            match: Pattern match
            input_data: Input data

        Returns:
            Formatted query string
        """
        # Start with pattern description
        query = pattern.description

        # Add matched keywords for context
        if match.matched_keywords:
            keywords_str = ", ".join(match.matched_keywords[:3])  # First 3
            query += f" (keywords: {keywords_str})"

        # Add input data if relevant
        if input_data:
            # Add key inputs to query
            inputs: list[str] = []
            for key, value in list(input_data.items())[:3]:  # First 3
                if isinstance(value, str) and len(value) < 50:
                    inputs.append(f"{key}={value}")

            if inputs:
                query += f" | {', '.join(inputs)}"

        return query


# Convenience function for quick activation


async def auto_activate(
    query: str,
    project_root: Path = Path("."),
    min_confidence: float = 0.6,
    input_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Convenience function for automatic detection and activation.

    Detects intent from query and automatically activates the appropriate
    skill or workflow.

    Args:
        query: User input query
        project_root: Project root directory
        min_confidence: Minimum confidence threshold
        input_data: Optional input data for execution

    Returns:
        Execution result dict

    Example:
        >>> result = await auto_activate("scan for security issues")
        >>> print(result["action"])  # "skill" or "workflow"
        >>> print(result["success"])  # True or False
    """
    from vibesop.triggers import KeywordDetector, DEFAULT_PATTERNS

    # Detect intent
    detector = KeywordDetector(patterns=DEFAULT_PATTERNS)
    match = detector.detect_best(query, min_confidence=min_confidence)

    if not match:
        return {
            "success": False,
            "action": "none",
            "result": None,
            "error": f"No intent detected above confidence threshold {min_confidence}",
        }

    # Activate skill/workflow
    activator = SkillActivator(project_root=project_root)
    return await activator.activate(match, input_data=input_data)
