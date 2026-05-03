"""Tests for skill base classes."""

from pathlib import Path

import pytest

from vibesop.core.skills.base import (
    SkillContext,
    SkillDefinition,
    SkillMetadata,
    SkillResult,
    SkillType,
)


class TestSkillType:
    """Test SkillType enum."""

    def test_values(self):
        assert SkillType.PROMPT.value == "prompt"
        assert SkillType.WORKFLOW.value == "workflow"
        assert SkillType.COMMAND.value == "command"
        assert SkillType.HYBRID.value == "hybrid"


class TestSkillMetadata:
    """Test SkillMetadata dataclass."""

    def test_creation(self):
        meta = SkillMetadata(
            id="test/skill",
            name="Test",
            description="Desc",
            intent="testing",
        )
        assert meta.id == "test/skill"
        assert meta.namespace == "builtin"
        assert meta.version == "1.0.0"
        assert meta.tags == []
        assert meta.triggers == []
        assert meta.algorithms == []
        assert meta.capabilities == []

    def test_creation_with_lists(self):
        meta = SkillMetadata(
            id="test",
            name="Test",
            description="D",
            intent="t",
            tags=["a", "b"],
            triggers=["t1"],
            algorithms=["algo1"],
            capabilities=["cap1"],
        )
        assert meta.tags == ["a", "b"]
        assert meta.triggers == ["t1"]

    def test_skill_type_default(self):
        meta = SkillMetadata(id="t", name="T", description="D", intent="I")
        assert meta.skill_type == SkillType.PROMPT


class TestSkillContext:
    """Test SkillContext dataclass."""

    def test_creation(self):
        ctx = SkillContext(query="test", working_dir=Path("/tmp"))
        assert ctx.query == "test"
        assert ctx.working_dir == Path("/tmp")
        assert ctx.env == {}
        assert ctx.metadata == {}

    def test_creation_with_env(self):
        ctx = SkillContext(
            query="test", working_dir=Path("/tmp"), env={"KEY": "VAL"}, metadata={"k": "v"}
        )
        assert ctx.env == {"KEY": "VAL"}
        assert ctx.metadata == {"k": "v"}


class TestSkillResult:
    """Test SkillResult dataclass."""

    def test_creation(self):
        result = SkillResult(success=True, output="done")
        assert result.success is True
        assert result.output == "done"
        assert result.error is None
        assert result.metadata == {}

    def test_creation_with_error(self):
        result = SkillResult(success=False, output="", error="failed")
        assert result.success is False
        assert result.error == "failed"


class TestSkillDefinition:
    """Test SkillDefinition dataclass."""

    def test_creation(self):
        meta = SkillMetadata(id="t", name="T", description="D", intent="I")
        definition = SkillDefinition(metadata=meta)
        assert definition.metadata.id == "t"
        assert definition.source == "builtin"
        assert definition.source_file is None
