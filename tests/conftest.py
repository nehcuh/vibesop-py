"""Root conftest with shared fixtures for all tests."""

from pathlib import Path
from typing import Any, Generator
from unittest.mock import AsyncMock, Mock, patch

import pytest

from vibesop.core.models import SkillDefinition


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def mock_llm_response() -> dict[str, object]:
    return {
        "skill_id": "/review",
        "confidence": 0.95,
        "reasoning": "Query matches code review pattern",
    }


@pytest.fixture
def mock_llm_client(mock_llm_response: dict[str, object]) -> Generator[Mock, None, None]:
    with patch("vibesop.llm.anthropic.AnthropicClient") as mock_cls:
        mock_instance = Mock()
        mock_instance.query.return_value = mock_llm_response
        mock_cls.return_value = mock_instance
        yield mock_cls


@pytest.fixture
def sample_skill() -> SkillDefinition:
    return SkillDefinition(
        id="/test",
        name="Test Skill",
        description="A test skill for unit testing",
        trigger_when="test, testing, unit test",
    )


@pytest.fixture
def sample_skills(sample_skill: SkillDefinition) -> list[SkillDefinition]:
    return [
        sample_skill,
        SkillDefinition(
            id="/review",
            name="Code Review",
            description="Review code for issues",
            trigger_when="review, audit, check",
        ),
        SkillDefinition(
            id="/debug",
            name="Debug",
            description="Debug issues in code",
            trigger_when="debug, fix bug, troubleshoot",
        ),
    ]


@pytest.fixture
def mock_skill_loader(sample_skills: list[SkillDefinition]) -> Generator[Mock, None, None]:
    with patch("vibesop.core.skills.loader.SkillLoader") as mock_cls:
        mock_instance = Mock()
        mock_instance.load_skills.return_value = sample_skills
        mock_cls.return_value = mock_instance
        yield mock_cls


@pytest.fixture
def vibe_config_dir(tmp_path: Path) -> Path:
    """Create a temporary .vibe config directory."""
    config_dir = tmp_path / ".vibe"
    config_dir.mkdir()
    return config_dir


@pytest.fixture
def skills_dir(tmp_path: Path) -> Path:
    """Create a temporary skills directory."""
    skills_dir = tmp_path / ".vibe" / "skills"
    skills_dir.mkdir(parents=True)
    return skills_dir
