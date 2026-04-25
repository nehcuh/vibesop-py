"""Type protocols for routing subsystems.

Provides duck-typing interfaces for mixin attributes,
reducing the need for `type: ignore[attr-defined]` comments.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path

    from vibesop.core.routing.triage_service import TriageService


class RoutingStatsProvider(Protocol):
    """Protocol for router stats access."""

    _total_routes: int
    _layer_distribution: dict[str, int]
    _stats_lock: Any  # noqa: F821

    def _record_layer(self, layer: Any) -> None: ...  # noqa: F821


class RoutingConfigProvider(Protocol):
    """Protocol for router configuration access."""

    _config: Any  # noqa: F821
    project_root: Path


class RoutingTriageProvider(Protocol):
    """Protocol for triage service access."""

    _triage_service: TriageService
    _config: Any  # noqa: F821


class RoutingCandidateProvider(Protocol):
    """Protocol for candidate loading."""

    def _get_cached_candidates(self) -> list[dict[str, Any]]: ...  # noqa: F821
    def _get_skill_source(self, skill_id: str, namespace: str) -> str: ...


class RoutingCore(RoutingConfigProvider, RoutingCandidateProvider, Protocol):
    """Core routing capabilities needed by layer functions."""

    _triage_service: TriageService
    _config: Any  # noqa: F821
    project_root: Path

    def _record_layer(self, layer: Any) -> None: ...  # noqa: F821
    def _get_cached_candidates(self) -> list[dict[str, Any]]: ...  # noqa: F821
    def _get_skill_source(self, skill_id: str, namespace: str) -> str: ...
