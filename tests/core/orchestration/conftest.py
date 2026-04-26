"""Shared fixtures for orchestration tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from vibesop.core.routing import UnifiedRouter


@pytest.fixture
def router(tmp_path: Path) -> UnifiedRouter:
    """Create a router with a temp project root for isolated testing."""
    (tmp_path / ".vibe").mkdir(exist_ok=True)
    return UnifiedRouter(project_root=tmp_path)
