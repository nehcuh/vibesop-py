"""Type protocols for routing subsystems.

Provides duck-typing interfaces for mixin attributes,
reducing the need for `type: ignore[attr-defined]` comments.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from pathlib import Path

    from vibesop.core.routing.triage_service import TriageService


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
    project_root: Path

    def _record_layer(self, layer: Any) -> None: ...
    def _get_cached_candidates(self) -> list[dict[str, Any]]: ...
    def _get_skill_source(self, skill_id: str, namespace: str) -> str: ...
