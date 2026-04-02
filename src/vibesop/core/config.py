"""Configuration loader for VibeSOP.

Loads and manages YAML configuration files:
- core/registry.yaml - Skill definitions registry
- core/policies/skill-selection.yaml - Routing policies
"""

from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

yaml = YAML()
yaml.preserve_quotes = True


class ConfigLoadError(Exception):
    """Raised when configuration fails to load."""

    pass


class ConfigLoader:
    """Load and manage VibeSOP configuration files.

    Usage:
        loader = ConfigLoader(project_root=".")
        registry = loader.load_registry()
        skills = loader.get_all_skills()
    """

    def __init__(
        self,
        project_root: str | Path = ".",
    ) -> None:
        """Initialize the configuration loader.

        Args:
            project_root: Path to project root directory
        """
        self.project_root = Path(project_root).resolve()
        self._registry_cache: dict[str, Any] | None = None
        self._policy_cache: dict[str, Any] | None = None

    def load_registry(self, force_reload: bool = False) -> dict[str, Any]:
        """Load skill registry from core/registry.yaml.

        Args:
            force_reload: Force reload even if cached

        Returns:
            Dictionary with registry data

        Raises:
            ConfigLoadError: If file not found or invalid
        """
        if self._registry_cache and not force_reload:
            return self._registry_cache

        registry_path = self.project_root / "core" / "registry.yaml"

        if not registry_path.exists():
            msg = f"Registry file not found: {registry_path}"
            raise ConfigLoadError(msg)

        try:
            with registry_path.open("r", encoding="utf-8") as f:
                self._registry_cache = yaml.load(f)

            return self._registry_cache

        except Exception as e:
            msg = f"Failed to load registry: {e}"
            raise ConfigLoadError(msg) from e

    def load_policy(
        self,
        force_reload: bool = False,
    ) -> dict[str, Any]:
        """Load skill selection policy.

        Args:
            force_reload: Force reload even if cached

        Returns:
            Dictionary with policy data

        Raises:
            ConfigLoadError: If file not found or invalid
        """
        if self._policy_cache and not force_reload:
            return self._policy_cache

        policy_path = (
            self.project_root / "core" / "policies" / "skill-selection.yaml"
        )

        if not policy_path.exists():
            # Return default policy if file doesn't exist
            self._policy_cache = self._default_policy()
            return self._policy_cache

        try:
            with policy_path.open("r", encoding="utf-8") as f:
                self._policy_cache = yaml.load(f)

            return self._policy_cache

        except Exception as e:
            msg = f"Failed to load policy: {e}"
            raise ConfigLoadError(msg) from e

    def get_all_skills(self, force_reload: bool = False) -> list[dict[str, Any]]:
        """Get all skills from registry.

        Args:
            force_reload: Force reload even if cached

        Returns:
            List of skill definitions
        """
        registry = self.load_registry(force_reload=force_reload)
        return registry.get("skills", [])

    def get_skill_by_id(
        self,
        skill_id: str,
        force_reload: bool = False,
    ) -> dict[str, Any] | None:
        """Get skill definition by ID.

        Supports both full IDs (gstack/review) and shorthand (/review).

        Args:
            skill_id: Skill identifier
            force_reload: Force reload even if cached

        Returns:
            Skill definition or None if not found
        """
        skills = self.get_all_skills(force_reload=force_reload)

        # Try exact match first
        for skill in skills:
            if skill.get("id") == skill_id:
                return skill

        # Try shorthand match (e.g., /review → gstack/review)
        if skill_id.startswith("/"):
            shorthand = skill_id[1:]  # Remove leading /
            for skill in skills:
                skill_full_id = skill.get("id", "")
                # Match: gstack/review, superpowers/review, etc.
                if skill_full_id.endswith(f"/{shorthand}") or skill_full_id.endswith(
                    f"-{shorthand}"
                ):
                    return skill
        else:
            # Try matching suffix
            for skill in skills:
                skill_full_id = skill.get("id", "")
                if skill_full_id.endswith(f"/{skill_id}") or skill_full_id.endswith(
                    f"-{skill_id}"
                ):
                    return skill

        return None

    def get_skills_by_namespace(
        self,
        namespace: str,
        force_reload: bool = False,
    ) -> list[dict[str, Any]]:
        """Get all skills in a namespace.

        Args:
            namespace: Namespace (builtin, gstack, superpowers, project)
            force_reload: Force reload even if cached

        Returns:
            List of skill definitions in namespace
        """
        skills = self.get_all_skills(force_reload=force_reload)
        return [
            skill
            for skill in skills
            if skill.get("namespace") == namespace
        ]

    def search_skills(
        self,
        query: str,
        force_reload: bool = False,
    ) -> list[dict[str, Any]]:
        """Search skills by keyword in intent or description.

        Args:
            query: Search query
            force_reload: Force reload even if cached

        Returns:
            List of matching skills
        """
        skills = self.get_all_skills(force_reload=force_reload)
        query_lower = query.lower()

        results = []
        for skill in skills:
            intent = skill.get("intent", "").lower()
            # Check if query appears in intent
            if query_lower in intent:
                results.append(skill)

        return results

    def get_builtin_keywords(self) -> list[str]:
        """Get all keywords from builtin skills for semantic matching.

        Returns:
            List of keyword phrases
        """
        skills = self.get_skills_by_namespace("builtin")
        keywords = []

        for skill in skills:
            intent = skill.get("intent", "")
            # Extract key phrases from intent
            keywords.append(intent)
            # Could also extract from skill_id
            keywords.append(skill.get("id", ""))

        return keywords

    def _default_policy(self) -> dict[str, Any]:
        """Return default skill selection policy.

        Used when policy file doesn't exist.
        """
        return {
            "candidate_selection": {
                "max_candidates": 3,
                "auto_select_threshold": 0.15,
                "min_confidence": 0.6,
                "sort_by": "balanced",
            },
            "preference_learning": {
                "enabled": True,
                "dimensions": {
                    "consistency": {"weight": 0.4, "threshold": 0.7, "min_samples": 5},
                    "satisfaction": {"weight": 0.3, "min_samples": 3},
                    "context": {"weight": 0.2},
                    "recency": {"weight": 0.1, "decay_days": 30},
                },
            },
            "parallel_execution": {
                "enabled": True,
                "max_parallel": 2,
                "mode": "auto",
                "conditions": {
                    "max_confidence_diff": 0.10,
                    "min_candidates": 2,
                    "max_candidates": 3,
                },
                "aggregation": {
                    "method": "merged",
                    "timeout": 300,
                },
            },
        }

    def clear_cache(self) -> None:
        """Clear cached configuration."""
        self._registry_cache = None
        self._policy_cache = None
