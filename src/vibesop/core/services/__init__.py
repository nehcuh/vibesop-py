"""VibeSOP Core Services - Business logic layer shared between CLI and slash commands.

This module provides high-level services that encapsulate common operations,
eliminating duplication between CLI commands and slash command handlers.

Architecture:
    - RoutingService: Unified routing and orchestration
    - InstallService: Skill pack installation and management
    - AnalysisService: Project analysis and profiling
    - EvaluationService: Skill quality evaluation and metrics
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from vibesop.core.matching import RoutingContext
from vibesop.core.routing import UnifiedRouter

if TYPE_CHECKING:
    from vibesop.core.models import RoutingResult

logger = logging.getLogger(__name__)


class RoutingService:
    """Service for routing queries to skills.

    Encapsulates router initialization, query routing, and orchestration.
    Used by both CLI commands and slash command handlers.
    """

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root or Path.cwd()
        self._router: UnifiedRouter | None = None

    @property
    def router(self) -> UnifiedRouter:
        """Lazy-load UnifiedRouter instance."""
        if self._router is None:
            self._router = UnifiedRouter(project_root=self.project_root)
        return self._router

    def route(
        self,
        query: str,
        context: RoutingContext | None = None,
    ) -> RoutingResult:
        """Route a query to the best matching skill.

        Args:
            query: Natural language query
            context: Optional routing context

        Returns:
            RoutingResult with matched skill and metadata
        """
        if context is None:
            context = RoutingContext()
        return self.router.orchestrate(query, context=context)

    def orchestrate(
        self,
        query: str,
        context: RoutingContext | None = None,
    ) -> Any:
        """Orchestrate multi-skill execution for complex queries.

        Args:
            query: Natural language query
            context: Optional routing context

        Returns:
            Orchestration result with execution plan
        """
        if context is None:
            context = RoutingContext()
        return self.router.orchestrate(query, context=context)


class InstallService:
    """Service for skill pack installation.

    Encapsulates pack installation logic with central storage and symlinks.
    """

    def __init__(self) -> None:
        self._installer: Any | None = None

    @property
    def installer(self) -> Any:
        """Lazy-load PackInstaller instance."""
        if self._installer is None:
            from vibesop.installer.pack_installer import PackInstaller

            self._installer = PackInstaller()
        return self._installer

    def install_pack(
        self,
        pack_name: str,
        platforms: list[str] | None = None,
    ) -> tuple[bool, str]:
        """Install a skill pack.

        Args:
            pack_name: Name of the pack or URL
            platforms: Optional list of platforms to create symlinks for

        Returns:
            Tuple of (success, message)
        """
        return self.installer.install_pack(
            pack_name=pack_name,
            platforms=platforms,
        )


class AnalysisService:
    """Service for project analysis.

    Encapsulates project profiling and architecture analysis.
    """

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root or Path.cwd()
        self._analyzer: Any | None = None

    @property
    def analyzer(self) -> Any:
        """Lazy-load ProjectAnalyzer instance."""
        if self._analyzer is None:
            from vibesop.core.project_analyzer import ProjectAnalyzer

            self._analyzer = ProjectAnalyzer(self.project_root)
        return self._analyzer

    def analyze(self, deep: bool = False) -> dict[str, Any]:
        """Analyze project structure and tech stack.

        Args:
            deep: Whether to include detailed metrics

        Returns:
            Dictionary with analysis results
        """
        profile = self.analyzer.analyze()
        result = {
            "project_type": profile.project_type,
            "tech_stack": profile.tech_stack,
        }
        if deep:
            result["file_count"] = getattr(profile, "file_count", None)
            result["code_lines"] = getattr(profile, "code_lines", None)
        return result


class EvaluationService:
    """Service for skill evaluation and quality metrics.

    Encapsulates skill quality assessment and reporting.
    """

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root or Path.cwd()
        self._evaluator: Any | None = None

    @property
    def evaluator(self) -> Any:
        """Lazy-load RoutingEvaluator instance."""
        if self._evaluator is None:
            from vibesop.core.skills.evaluator import RoutingEvaluator

            self._evaluator = RoutingEvaluator(project_root=self.project_root)
        return self._evaluator

    def evaluate_skill(self, skill_id: str) -> dict[str, Any] | None:
        """Evaluate a specific skill.

        Args:
            skill_id: Skill identifier

        Returns:
            Evaluation data dictionary or None
        """
        evaluation = self.evaluator.evaluate_skill(skill_id)
        if evaluation is None:
            return None
        return {
            "skill_id": skill_id,
            "grade": evaluation.grade,
            "quality_score": evaluation.quality_score,
            "total_routes": evaluation.total_routes,
        }

    def evaluate_all(self) -> dict[str, dict[str, Any]]:
        """Evaluate all skills.

        Returns:
            Dictionary mapping skill_id to evaluation data
        """
        all_evals = self.evaluator.evaluate_all_skills()
        result = {}
        for sid, ev in all_evals.items():
            result[sid] = {
                "grade": ev.grade,
                "quality_score": ev.quality_score,
                "total_routes": ev.total_routes,
            }
        return result
