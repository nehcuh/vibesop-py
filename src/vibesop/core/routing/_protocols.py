"""Type protocols for routing subsystems.

Provides duck-typing interfaces for mixin attributes,
reducing the need for `type: ignore[attr-defined]` comments.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from pathlib import Path

    from vibesop.core.routing.triage_service import TriageService


class LLMFactory(Protocol):
    """Callable that returns an LLM provider."""

    def __call__(self) -> Any: ...


class PromptBuilder(Protocol):
    """Callable that builds an AI triage prompt."""

    def __call__(self, query: str, skills_summary: str, version: str) -> str: ...


class SkillLoaderProtocol(Protocol):
    """Duck-typing interface for skill loading subsystems."""

    def discover_all(self, force_reload: bool = False) -> dict[str, Any]: ...
    def get_skill(self, skill_id: str) -> Any | None: ...


class RoutingStatsProvider(Protocol):
    """Protocol for router stats access."""

    _total_routes: int
    _layer_distribution: dict[str, int]
    _stats_lock: Any

    def _record_layer(self, layer: Any) -> None: ...


class RoutingConfigProvider(Protocol):
    """Protocol for router configuration access."""

    _config: Any
    project_root: Path


class RoutingTriageProvider(Protocol):
    """Protocol for triage service access."""

    _triage_service: TriageService
    _config: Any


class RoutingCandidateProvider(Protocol):
    """Protocol for candidate loading."""

    def _get_cached_candidates(self) -> list[dict[str, Any]]: ...
    def _get_skill_source(self, skill_id: str, namespace: str) -> str: ...


class RoutingCore(RoutingConfigProvider, RoutingCandidateProvider, Protocol):
    """Core routing capabilities needed by layer functions."""

    _triage_service: TriageService
    _config: Any
    _llm: Any
    _cost_tracker: Any
    _scenario_cache: Any
    _index_embedding_model: Any
    _index_layer_cache: Any
    _index_profile_tokens: Any
    _matchers: list[tuple[Any, Any]]
    project_root: Path

    def _record_layer(self, layer: Any) -> None: ...
    def _get_cached_candidates(self) -> list[dict[str, Any]]: ...
    def _get_skill_source(self, skill_id: str, namespace: str) -> str: ...
