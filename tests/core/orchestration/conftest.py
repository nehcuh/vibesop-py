"""Shared fixtures for orchestration tests."""

from __future__ import annotations

import pytest

from vibesop.core.routing import UnifiedRouter


@pytest.fixture(scope="module")
def router(tmp_path_factory) -> UnifiedRouter:
    """Create a router with a temp project root for isolated testing."""
    tmp_path = tmp_path_factory.mktemp("orchestration")
    (tmp_path / ".vibe").mkdir(exist_ok=True)
    return UnifiedRouter(project_root=tmp_path)
