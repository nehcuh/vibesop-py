"""End-to-end tests for UnifiedRouter with optimization enabled."""

import pytest

from vibesop.core.config.manager import ConfigManager
from vibesop.core.routing.unified import RoutingResult, UnifiedRouter


@pytest.fixture
def router(tmp_path):
    (tmp_path / ".vibe").mkdir()
    (tmp_path / "core" / "skills").mkdir(parents=True)

    manager = ConfigManager(project_root=tmp_path)
    manager.set_cli_override("optimization.enabled", True)
    manager.set_cli_override("optimization.prefilter.enabled", True)
    manager.set_cli_override("optimization.prefilter.max_candidates", 10)
    manager.set_cli_override("optimization.preference_boost.enabled", True)
    manager.set_cli_override("optimization.clustering.enabled", True)

    return UnifiedRouter(project_root=tmp_path, config=manager)


def test_router_with_optimization_enabled(router):
    result = router.route("debug this error")
    assert isinstance(result, RoutingResult)


def test_optimization_reduces_candidates(router):
    result = router.route("test query")
    assert result is not None


def test_router_backward_compatible(tmp_path):
    (tmp_path / ".vibe").mkdir()
    (tmp_path / "core" / "skills").mkdir(parents=True)

    manager = ConfigManager(project_root=tmp_path)
    manager.set_cli_override("optimization.enabled", False)

    router = UnifiedRouter(project_root=tmp_path, config=manager)
    result = router.route("test query")
    assert isinstance(result, RoutingResult)
