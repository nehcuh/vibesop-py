"""Fixtures and configuration for E2E tests."""

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest


@pytest.fixture
def project_root() -> Path:
    """Return the actual project root directory.

    This allows tests to access project skills and configuration
    while still providing isolation for test-specific state.
    """
    # Get the project root (parent of src directory)
    return Path(__file__).parent.parent.parent


@pytest.fixture
def temp_project_dir() -> Generator[Path, None, None]:
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        yield project_dir


@pytest.fixture(autouse=True)
def clean_preferences(project_root: Path) -> Generator[None, None, None]:
    """Clean preferences.json before each test to prevent state pollution.

    This fixture runs automatically for all tests in this directory.
    It removes the preferences file to ensure tests start with a clean state.
    """
    pref_file = project_root / ".vibe" / "preferences.json"
    # Remove preferences file if it exists
    if pref_file.exists():
        pref_file.unlink()
    yield
    # Clean up after test
    if pref_file.exists():
        pref_file.unlink()


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
