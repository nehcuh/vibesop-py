"""Custom matcher plugin system for VibeSOP.

Allows users to register custom matching functions that integrate
seamlessly with the UnifiedRouter's layer-based pipeline.
"""

from __future__ import annotations

import importlib.util
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vibesop.core.matching.base import MatchResult, RoutingContext

logger = logging.getLogger(__name__)

# Simple matcher function signature: (query, candidate) -> float
custom_matcher_func = Callable[[str, dict[str, Any]], float]


@dataclass
class PluginMatcher:
    """A user-defined matcher loaded from a Python file."""

    name: str
    description: str
    source_file: Path
    match_fn: custom_matcher_func
    weight: float = 1.0

    def score(
        self,
        query: str,
        candidate: dict[str, Any],
        _context: RoutingContext | None = None,
    ) -> float:
        """Score a single candidate."""
        try:
            return self.match_fn(query, candidate)
        except Exception as e:
            logger.warning("Custom matcher '%s' failed for %s: %s", self.name, candidate.get("id"), e)
            return 0.0

    def match(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        context: RoutingContext | None = None,
        top_k: int = 10,
    ) -> list[MatchResult]:
        """Match query against all candidates."""
        results: list[MatchResult] = []
        for c in candidates:
            score = self.score(query, c, context)
            if score > 0.0:
                results.append(
                    MatchResult(
                        skill_id=str(c.get("id", "")),
                        confidence=min(score * self.weight, 1.0),
                        score_breakdown={"custom_matcher": score, "weight": self.weight},
                        matcher_type="custom",
                        matched_keywords=[],
                        matched_patterns=[],
                        semantic_score=0.0,
                        metadata={"matcher_name": self.name},
                    )
                )
        results.sort(key=lambda x: x.confidence, reverse=True)
        return results[:top_k]


class MatcherPluginRegistry:
    """Registry for custom matcher plugins.

    Scans `.vibe/matchers/` for Python files containing matcher definitions.
    """

    def __init__(self, project_root: str | Path = ".") -> None:
        self.project_root = Path(project_root).resolve()
        self._matchers_dir = self.project_root / ".vibe" / "matchers"
        self._plugins: dict[str, PluginMatcher] = {}
        self._load_all()

    def _load_all(self) -> None:
        """Scan matchers directory and load all valid plugins."""
        if not self._matchers_dir.exists():
            return

        for file_path in self._matchers_dir.glob("*.py"):
            if file_path.name.startswith("_"):
                continue
            try:
                plugin = self._load_file(file_path)
                if plugin:
                    self._plugins[plugin.name] = plugin
            except Exception as e:
                logger.warning("Failed to load matcher plugin %s: %s", file_path, e)

    def _load_file(self, file_path: Path) -> PluginMatcher | None:
        """Load a single matcher plugin from a Python file.

        Expected file structure:
            NAME = "my_matcher"
            DESCRIPTION = "Matches based on custom logic"
            WEIGHT = 1.0

            def match(query: str, candidate: dict) -> float:
                # Return confidence 0.0-1.0
                return 0.5
        """
        spec = importlib.util.spec_from_file_location(
            file_path.stem, str(file_path)
        )
        if not spec or not spec.loader:
            return None

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        name = getattr(module, "NAME", file_path.stem)
        description = getattr(module, "DESCRIPTION", "")
        weight = getattr(module, "WEIGHT", 1.0)
        match_fn = getattr(module, "match", None)

        if match_fn is None or not callable(match_fn):
            logger.warning("Matcher plugin %s has no 'match' function", file_path)
            return None

        return PluginMatcher(
            name=name,
            description=description,
            source_file=file_path,
            match_fn=match_fn,
            weight=float(weight),
        )

    def list_plugins(self) -> list[PluginMatcher]:
        """Return all loaded plugins."""
        return list(self._plugins.values())

    def get_plugin(self, name: str) -> PluginMatcher | None:
        """Get a plugin by name."""
        return self._plugins.get(name)

    def register(self, file_path: str | Path) -> PluginMatcher | None:
        """Register a new matcher plugin from a file path.

        Copies the file to `.vibe/matchers/` and loads it.
        """
        src = Path(file_path).resolve()
        if not src.exists():
            logger.error("Matcher file not found: %s", src)
            return None

        self._matchers_dir.mkdir(parents=True, exist_ok=True)
        dst = self._matchers_dir / src.name

        # Avoid overwriting with same name
        if dst.exists() and dst.resolve() != src.resolve():
            logger.error("Matcher name conflict: %s already exists", dst.name)
            return None

        import shutil

        if dst.resolve() != src.resolve():
            shutil.copy2(src, dst)

        plugin = self._load_file(dst)
        if plugin:
            self._plugins[plugin.name] = plugin
        return plugin

    def remove(self, name: str) -> bool:
        """Remove a registered plugin by name."""
        plugin = self._plugins.pop(name, None)
        if plugin and plugin.source_file.exists():
            try:
                plugin.source_file.unlink()
                return True
            except OSError as e:
                logger.warning("Failed to remove matcher file %s: %s", plugin.source_file, e)
        return plugin is not None

    def reload(self) -> None:
        """Reload all plugins from disk."""
        self._plugins.clear()
        self._load_all()
