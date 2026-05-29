"""Conformance tests: SKILL.md specification compliance.

Verifies that SkillSpec captures all 29 frontmatter fields, validates
required fields, handles type mapping correctly, and supports v1/v2
migration with warnings instead of errors.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from vibesop.spec.models import (
    LLMConfigSpec,
    SkillLifecycle,
    SkillSpec,
    SkillType,
    SourceConfigSpec,
)
from vibesop.spec.validator import SpecValidator


class TestRequiredFields:
    """Required fields (id, name, description) must be present."""

    def test_minimal_valid_spec(self):
        spec = SkillSpec(
            id="test/minimal",
            name="Minimal Skill",
            description="A minimal skill",
        )
        assert spec.id == "test/minimal"
        assert spec.name == "Minimal Skill"
        assert spec.description == "A minimal skill"

    def test_missing_id_raises_error(self):
        with pytest.raises(ValueError, match="id"):
            SkillSpec(name="No ID", description="Missing id field")  # type: ignore[call-arg]

    def test_missing_name_raises_error(self):
        with pytest.raises(ValueError, match="name"):
            SkillSpec(id="test/no-name", description="Missing name field")  # type: ignore[call-arg]

    def test_empty_id_raises_error(self):
        with pytest.raises(ValueError, match="id"):
            SkillSpec(id="", name="Empty ID", description="Empty id")

    def test_default_values_applied(self):
        spec = SkillSpec(id="test/defaults", name="Defaults", description="Testing defaults")
        assert spec.version == "1.0.0"
        assert spec.namespace == "builtin"
        assert spec.skill_type == SkillType.PROMPT
        assert spec.lifecycle == SkillLifecycle.ACTIVE
        assert spec.enabled is True
        assert spec.priority == 50
        assert spec.confidence == 0.5
        assert spec.tags == []
        assert spec.keywords == []
        assert spec.triggers == []
        assert spec.capabilities == []


class TestAll29Fields:
    """Verify all 29 SKILL.md frontmatter fields are captured by SkillSpec."""

    def test_all_fields_present_in_model(self):
        """SkillSpec must have 29 fields matching the canonical spec."""
        fields = list(SkillSpec.model_fields.keys())
        # The 29 canonical fields
        expected = {
            "id", "name", "description", "version",
            "author", "namespace",
            "skill_type", "intent",
            "trigger_when", "triggers", "routing_patterns", "priority",
            "tags", "keywords", "category",
            "capabilities", "algorithms",
            "commands", "user_invocable", "allowed_tools",
            "mode",
            "lifecycle", "scope", "enabled", "deprecation_reason",
            "dependencies", "env_vars",
            "llm_config", "source_config",
            "confidence", "auto_configured", "metadata",
        }
        missing = expected - set(fields)
        assert not missing, f"Missing fields: {missing}"

    def test_full_spec_construction(self):
        """Construct SkillSpec with every field populated."""
        spec = SkillSpec(
            id="test/full",
            name="Full Skill",
            description="A skill with all fields",
            version="2.0.0",
            author="Test Author",
            namespace="project",
            type="workflow",
            intent="Test intent for routing",
            trigger_when="on code push",
            triggers=["trigger1", "trigger2"],
            routing_patterns=["pattern/.*"],
            priority=80,
            tags=["testing", "ci"],
            keywords=["test", "full"],
            category="testing",
            capabilities=["analysis", "review"],
            algorithms=["pattern-match"],
            commands=["test-cmd"],
            user_invocable=True,
            allowed_tools=["Read", "Write"],
            mode="observe-only",
            lifecycle=SkillLifecycle.DRAFT,
            scope="project",
            enabled=True,
            deprecation_reason=None,
            dependencies=["pytest"],
            env_vars=["TEST_API_KEY"],
            llm_config=LLMConfigSpec(provider="anthropic", model="claude-4"),
            source_config=SourceConfigSpec(type="github", repository="example/repo"),
            confidence=0.9,
            auto_configured=True,
            metadata={"custom_key": "custom_value"},
        )
        # Verify all fields round-trip correctly
        assert spec.skill_type == SkillType.WORKFLOW
        assert spec.priority == 80
        assert spec.tags == ["testing", "ci"]
        assert spec.keywords == ["test", "full"]
        assert spec.routing_patterns == ["pattern/.*"]
        assert spec.user_invocable is True
        assert spec.allowed_tools == ["Read", "Write"]
        assert spec.llm_config.provider == "anthropic"
        assert spec.source_config.type == "github"
        assert spec.confidence == 0.9


class TestTypeMapping:
    """Verify skill_type = 'type' frontmatter alias works correctly."""

    def test_standard_type_recognized(self):
        """SkillType.STANDARD exists — fixes bug where 6 core skills silently
        fell back to PROMPT."""
        spec = SkillSpec(
            id="test/standard",
            name="Standard Type",
            description="Uses standard type",
            type="standard",
        )
        assert spec.skill_type == SkillType.STANDARD
        assert spec.skill_type != SkillType.PROMPT

    def test_workflow_type_via_alias(self):
        spec = SkillSpec(
            id="test/workflow",
            name="Workflow Type",
            description="Uses workflow type",
            type="workflow",
        )
        assert spec.skill_type == SkillType.WORKFLOW

    def test_command_type_via_alias(self):
        spec = SkillSpec(
            id="test/command",
            name="Command Type",
            description="Uses command type",
            type="command",
        )
        assert spec.skill_type == SkillType.COMMAND

    def test_hybrid_type_via_alias(self):
        spec = SkillSpec(
            id="test/hybrid",
            name="Hybrid Type",
            description="Uses hybrid type",
            type="hybrid",
        )
        assert spec.skill_type == SkillType.HYBRID

    def test_populate_by_name_allows_python_field_name(self):
        """populate_by_name=True ensures both skill_type= and type= work."""
        spec = SkillSpec(
            id="test/direct",
            name="Direct Name",
            description="Using skill_type kwarg",
            skill_type=SkillType.WORKFLOW,
        )
        assert spec.skill_type == SkillType.WORKFLOW

    def test_invalid_type_raises_error(self):
        with pytest.raises(ValueError):
            SkillSpec(
                id="test/invalid",
                name="Invalid Type",
                description="Invalid type value",
                type="nonexistent-type",
            )


class TestV1V2Migration:
    """v1/v2 files with missing fields produce warnings, not errors."""

    def test_v1_minimal_frontmatter_still_valid(self):
        """v1 frontmatter with version field is valid."""
        validator = SpecValidator()
        content = """---
id: test/v1-min
name: V1 Skill
description: Minimal v1 format
version: "1.0.0"
---
# V1 Skill
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False
        ) as f:
            f.write(content)
            f.flush()
            result = validator.validate_file(Path(f.name))

        assert result.valid
        Path(f.name).unlink(missing_ok=True)

    def test_missing_version_is_error(self):
        """Missing required 'version' field is a hard error."""
        validator = SpecValidator()
        content = """---
id: test/no-version
name: No Version
description: Missing version field
---
# No Version
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False
        ) as f:
            f.write(content)
            f.flush()
            result = validator.validate_file(Path(f.name))

        assert not result.valid
        assert any("version" in e.message.lower() for e in result.errors)
        Path(f.name).unlink(missing_ok=True)

    def test_v1_missing_new_fields_produces_warnings(self):
        """v1 files missing v3-only fields produce warnings, not errors."""
        validator = SpecValidator()
        content = """---
id: test/v1-old
name: V1 Old Skill
description: Pre-v3 format skill
version: "1.0.0"
type: prompt
---
# Old Skill
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False
        ) as f:
            f.write(content)
            f.flush()
            result = validator.validate_file(Path(f.name))

        # v1 files with required fields should be valid
        # Missing v3-only fields get defaults, not errors
        error_count = len(result.errors)
        assert error_count == 0, (
            f"v1 files should not produce hard errors, got: "
            f"{[e.message for e in result.errors]}"
        )
        Path(f.name).unlink(missing_ok=True)

    def test_v3_frontmatter_all_fields_valid(self):
        """v3 frontmatter with all fields should be fully valid."""
        validator = SpecValidator()
        content = """---
id: test/v3-full
name: V3 Full
description: Complete v3 format
version: "2.0.0"
author: Test Author
namespace: project
type: workflow
intent: Test intent
trigger_when: on push
triggers:
  - trigger1
routing_patterns:
  - "pattern/.*"
priority: 75
tags:
  - ci
keywords:
  - test
category: testing
capabilities:
  - analysis
commands:
  - test-cmd
user_invocable: true
allowed_tools:
  - Read
mode: observe-only
lifecycle: active
scope: project
dependencies:
  - pytest
env_vars:
  - TEST_KEY
---
# V3 Full Skill
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False
        ) as f:
            f.write(content)
            f.flush()
            result = validator.validate_file(Path(f.name))

        assert result.valid
        Path(f.name).unlink(missing_ok=True)


class TestKeywordsTagsSeparation:
    """keywords and tags are separated fields (previously merged by parser)."""

    def test_tags_and_keywords_independent(self):
        spec = SkillSpec(
            id="test/separation",
            name="Separation Test",
            description="Testing keywords vs tags split",
            tags=["development", "testing"],
            keywords=["code-review", "analysis"],
        )
        assert spec.tags == ["development", "testing"]
        assert spec.keywords == ["code-review", "analysis"]
        assert spec.tags != spec.keywords

    def test_keywords_defaults_empty(self):
        spec = SkillSpec(
            id="test/no-keywords",
            name="No Keywords",
            description="No keywords specified",
            tags=["ci"],
        )
        assert spec.keywords == []
        assert spec.tags == ["ci"]


class TestLifecycleStates:
    """SkillLifecycle enum covers all states."""

    def test_all_lifecycle_values(self):
        assert SkillLifecycle.DRAFT.value == "draft"
        assert SkillLifecycle.ACTIVE.value == "active"
        assert SkillLifecycle.DEPRECATED.value == "deprecated"
        assert SkillLifecycle.ARCHIVED.value == "archived"

    def test_lifecycle_in_spec(self):
        spec = SkillSpec(
            id="test/lifecycle",
            name="Lifecycle Test",
            description="Testing lifecycle field",
            lifecycle="deprecated",
        )
        assert spec.lifecycle == SkillLifecycle.DEPRECATED


class TestNestedConfigs:
    """LLMConfigSpec and SourceConfigSpec capture sub-object fields."""

    def test_llm_config_all_fields(self):
        config = LLMConfigSpec(
            provider="anthropic",
            model="claude-opus-4-20250514",
            temperature=0.7,
            api_key="ANTHROPIC_API_KEY",
            api_base="https://api.anthropic.com",
            parameters={"max_tokens": 4096},
            fallback="openai",
        )
        spec = SkillSpec(
            id="test/llm",
            name="LLM Config Test",
            description="Testing LLM config",
            llm_config=config,
        )
        assert spec.llm_config.provider == "anthropic"
        assert spec.llm_config.model == "claude-opus-4-20250514"
        assert spec.llm_config.temperature == 0.7
        assert spec.llm_config.fallback == "openai"
        assert spec.llm_config.parameters == {"max_tokens": 4096}

    def test_source_config_all_fields(self):
        config = SourceConfigSpec(
            type="github",
            repository="example/repo",
            checksum="abc123",
            ref="main",
        )
        spec = SkillSpec(
            id="test/source",
            name="Source Config Test",
            description="Testing source config",
            source_config=config,
        )
        assert spec.source_config.type == "github"
        assert spec.source_config.repository == "example/repo"
        assert spec.source_config.checksum == "abc123"
        assert spec.source_config.ref == "main"
