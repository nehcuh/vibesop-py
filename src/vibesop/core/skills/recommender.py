"""Smart skill recommendations based on project type and usage patterns.

Recommends skills based on:
1. Project tech stack (primary language -> relevant skills)
2. Collaborative filtering (pack co-installation patterns)
3. Missing skill detection for current project context
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

logger = logging.getLogger(__name__)


@dataclass
class SkillRecommendation:
    """A recommended skill with reason."""

    skill_id: str
    reason: str
    confidence: float = 0.5
    installed: bool = False
    score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "reason": self.reason,
            "confidence": self.confidence,
            "installed": self.installed,
            "score": self.score,
        }


class SkillRecommender:
    """Recommends skills based on project context and usage data."""

    STACK_RECOMMENDATIONS: ClassVar[dict[str, list[tuple[str, str]]]] = {
        "python": [
            ("superpowers/tdd", "Test-driven development for Python projects"),
            ("superpowers/refactor", "Systematic refactoring with safety checks"),
        ],
        "javascript": [
            ("mattpocock/tdd", "Test-driven development with red-green-refactor"),
            ("mattpocock/diagnosing-bugs", "Disciplined diagnosis loop for hard bugs"),
        ],
        "typescript": [
            ("mattpocock/tdd", "Test-driven development with red-green-refactor"),
            ("mattpocock/diagnosing-bugs", "Disciplined diagnosis loop for hard bugs"),
            (
                "mattpocock/improve-codebase-architecture",
                "Architecture improvement with domain language",
            ),
            ("superpowers/refactor", "Systematic refactoring"),
        ],
        "rust": [
            ("superpowers/optimize", "Performance profiling and optimization"),
        ],
        "go": [
            ("superpowers/architect", "System architecture design"),
        ],
        "default": [
            ("mattpocock/diagnosing-bugs", "Disciplined diagnosis loop for hard bugs"),
            ("mattpocock/tdd", "Test-driven development"),
        ],
    }

    _featured_registry: Any = None  # type: FeaturedRegistry | None

    def __init__(self, project_root: Path | None = None) -> None:
        self._project_root = project_root or Path.cwd()

    def _get_featured_registry(self) -> Any:
        """Lazy-load the featured skills registry."""
        if self._featured_registry is None:
            from vibesop.core.skills.featured_registry import FeaturedRegistry

            self._featured_registry = FeaturedRegistry(self._project_root)
        return self._featured_registry

    def recommend_for_project(self) -> list[SkillRecommendation]:
        project_info = self._analyze_project()
        lang = project_info.get("primary_language", "default")
        installed = self._get_installed_skill_ids()

        analytics_recs = self._get_analytics_recommendations(lang, installed)
        if analytics_recs:
            return analytics_recs

        # Use featured registry as primary source, fall back to hardcoded
        try:
            registry = self._get_featured_registry()
            featured = registry.for_stack_or_default(lang, limit=8)
            if featured:
                recs: list[SkillRecommendation] = []
                for fs in featured:
                    if fs.skill_id in installed:
                        continue
                    recs.append(
                        SkillRecommendation(
                            skill_id=fs.skill_id,
                            reason=f"[{lang.title()}] {fs.description[:80]}",
                            confidence=fs.quality_rating,
                            installed=False,
                        )
                    )
                if recs:
                    return recs
        except (ImportError, OSError):
            pass

        # Fallback to hardcoded recommendations (legacy)
        recs = []
        candidates = self.STACK_RECOMMENDATIONS.get(lang, self.STACK_RECOMMENDATIONS["default"])
        for skill_id, reason in candidates:
            recs.append(
                SkillRecommendation(
                    skill_id=skill_id,
                    reason=f"[{lang.title()}] {reason}",
                    confidence=0.85,
                    installed=skill_id in installed,
                )
            )
        return recs

    def _get_analytics_recommendations(
        self, _lang: str, installed: set[str]
    ) -> list[SkillRecommendation] | None:
        """Get data-driven recommendations from AnalyticsStore."""
        try:
            from vibesop.core.analytics import AnalyticsStore

            store = AnalyticsStore(storage_dir=self._project_root / ".vibe")
            popular = store.get_popular_skills(limit=30)
            if not popular:
                return None

            ratings = self._get_skill_ratings()

            recs: list[SkillRecommendation] = []
            for skill_id, use_count, satisfaction in popular:
                if skill_id in installed:
                    continue
                confidence = min(0.95, 0.5 + satisfaction * 0.3 + min(use_count, 10) * 0.02)
                rating_str = ""
                if skill_id in ratings:
                    rating_str = f" ({ratings[skill_id]:.1f}/5)"
                recs.append(
                    SkillRecommendation(
                        skill_id=skill_id,
                        reason=f"Used {use_count}× ({satisfaction:.0%} satisfaction){rating_str}",
                        confidence=confidence,
                        installed=False,
                    )
                )

            recs.sort(key=lambda r: r.confidence, reverse=True)
            return recs[:10] if recs else None
        except (ImportError, OSError):
            return None

    def _get_skill_ratings(self) -> dict[str, float]:
        """Get average ratings from SkillRatingStore."""
        try:
            from vibesop.core.skills.ratings import SkillRatingStore

            store = SkillRatingStore()
            top = store.get_top_rated(limit=100, min_reviews=1)
            return {skill_id: score for skill_id, score, _count in top}
        except (ImportError, OSError):
            return {}

    def recommend_collaborative(self) -> list[SkillRecommendation]:
        installed = self._get_installed_packs()
        recs: list[SkillRecommendation] = []

        has_superpowers = any("superpowers" in p for p in installed)
        has_mattpocock = any("mattpocock" in p for p in installed)

        if has_superpowers and not has_mattpocock:
            recs.append(
                SkillRecommendation(
                    skill_id="mattpocock/diagnosing-bugs",
                    reason="Users with superpowers often also use mattpocock skills for debugging",
                    confidence=0.72,
                )
            )
            recs.append(
                SkillRecommendation(
                    skill_id="mattpocock/tdd",
                    reason="Structured TDD complement to superpowers/tdd",
                    confidence=0.68,
                )
            )

        if has_mattpocock and not has_superpowers:
            recs.append(
                SkillRecommendation(
                    skill_id="superpowers/tdd",
                    reason="Users with mattpocock skills often also use superpowers",
                    confidence=0.75,
                )
            )
            recs.append(
                SkillRecommendation(
                    skill_id="superpowers/refactor",
                    reason="Complementary to mattpocock/diagnosing-bugs",
                    confidence=0.70,
                )
            )

        return recs

    def detect_missing_skills(self) -> list[SkillRecommendation]:
        installed = self._get_installed_skill_ids()
        recs: list[SkillRecommendation] = []

        essential = [
            ("systematic-debugging", "Essential debugging workflow"),
            ("mattpocock/diagnosing-bugs", "Disciplined diagnosis loop for hard bugs"),
            ("mattpocock/tdd", "Test-driven development with red-green-refactor"),
        ]
        for skill_id, reason in essential:
            if skill_id not in installed:
                recs.append(
                    SkillRecommendation(
                        skill_id=skill_id,
                        reason=reason,
                        confidence=0.9,
                    )
                )

        return recs

    def _analyze_project(self) -> dict[str, Any]:
        try:
            from vibesop.core.project_analyzer import ProjectAnalyzer

            analyzer = ProjectAnalyzer(self._project_root)
            result = analyzer.analyze()
            if isinstance(result, dict):
                return result
            # ProjectProfile dataclass — extract relevant fields
            project_type = getattr(result, "project_type", None)
            tech_stack = getattr(result, "tech_stack", [])
            primary = project_type or (tech_stack[0] if tech_stack else None)
            if primary:
                return {"primary_language": primary}
        except (ImportError, RuntimeError, OSError):
            pass
        return self._simple_detect()

    def _simple_detect(self) -> dict[str, str]:
        counts: dict[str, int] = {}
        ext_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".rs": "rust",
            ".go": "go",
            ".java": "java",
        }
        for f in self._project_root.rglob("*"):
            if f.suffix in ext_map and f.is_file():
                lang = ext_map[f.suffix]
                counts[lang] = counts.get(lang, 0) + 1
        if not counts:
            return {"primary_language": "default"}
        best = max(counts, key=lambda k: counts[k])
        return {"primary_language": best}

    def _get_installed_skill_ids(self) -> set[str]:
        try:
            from vibesop.core.skills.loader import SkillLoader

            loader = SkillLoader(project_root=self._project_root)
            skills = loader.discover_all()
            return set(skills.keys())
        except (ImportError, RuntimeError, OSError):
            return set()

    def _get_installed_packs(self) -> set[str]:
        try:
            from vibesop.core.skills.loader import SkillLoader

            loader = SkillLoader(project_root=self._project_root)
            skills = loader.discover_all()
            packs: set[str] = set()
            for skill_id in skills:
                if "/" in skill_id:
                    packs.add(skill_id.split("/")[0])
            return packs
        except (ImportError, RuntimeError, OSError):
            return set()
