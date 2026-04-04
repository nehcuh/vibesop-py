"""Fixtures and configuration for E2E tests."""

import tempfile
from pathlib import Path
from typing import Generator

import pytest


@pytest.fixture
def temp_project_dir() -> Generator[Path, None, None]:
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        yield project_dir


@pytest.fixture
def sample_manifest() -> dict[str, object]:
    return {
        "metadata": {
            "project_name": "test-project",
            "description": "A test project",
            "version": "1.0.0",
            "author": "Test Author",
            "license": "MIT",
        },
        "skills": [],
        "policies": {
            "security": {
                "enable_scanning": True,
                "threat_level": "high",
            },
            "routing": {
                "semantic_threshold": 0.7,
                "enable_fuzzy": True,
            },
        },
    }


@pytest.fixture
def sample_config_dir(temp_project_dir: Path) -> Path:
    """Create sample configuration directory.

    Args:
        temp_project_dir: Temporary project directory

    Returns:
        Path to configuration directory
    """
    config_dir = temp_project_dir / ".vibe"
    config_dir.mkdir(exist_ok=True)
    return config_dir
