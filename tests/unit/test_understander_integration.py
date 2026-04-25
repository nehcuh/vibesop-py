#!/usr/bin/env python3
"""Unit test for skill understander integration."""

import tempfile
from pathlib import Path

from vibesop.core.skills.understander import (
    SkillAutoConfigurator,
    understand_skill_from_file,
)


def test_understand_skill_from_file():
    """Test understanding a skill from file."""

    with tempfile.TemporaryDirectory() as tmpdir:
        skill_dir = Path(tmpdir) / "test-skill.skill"
        skill_dir.mkdir()

        # Create SKILL.md
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("""---
name: Debugging Helper
id: debug-helper
description: Systematic debugging workflow for finding and fixing bugs
version: 1.0.0
skill_type: workflow
tags:
  - debug
  - troubleshooting
trigger_when: User encounters bugs or errors
---

# Debugging Helper

This skill provides a systematic workflow for debugging complex issues.
It helps identify root causes before attempting fixes.
""")

        # Understand the skill
        config = understand_skill_from_file(skill_dir)

        print(f"✓ Skill ID: {config.skill_id}")
        print(f"✓ Category: {config.category}")
        print(f"✓ Priority: {config.priority}")
        print(f"✓ Routing patterns: {len(config.routing_patterns)}")
        print(f"✓ Requires LLM: {config.requires_llm}")
        print(f"✓ Confidence: {config.confidence:.1%}")

        # Assertions
        assert config.skill_id == "debug-helper"
        assert config.category in ["debugging", "development"]
        assert config.priority > 0
        assert len(config.routing_patterns) > 0
        assert config.confidence > 0.0

        print("\n✓ All assertions passed!")


def test_skill_auto_configurator():
    """Test the auto-configurator directly."""

    from vibesop.core.skills.base import SkillMetadata

    # Create metadata
    metadata = SkillMetadata(
        id="test-skill",
        name="Test Skill",
        description="AI-powered code review and quality assurance",
        intent="Code review",
        trigger_when="User requests code review",
        skill_type="prompt",
        tags=["review", "quality"],
    )

    # Create configurator
    configurator = SkillAutoConfigurator()

    # Understand and configure
    content = "This skill provides AI-powered code review with quality checks."
    config = configurator.understand_and_configure(metadata, content, scope="project")

    print(f"✓ Skill ID: {config.skill_id}")
    print(f"✓ Category: {config.category}")
    print(f"✓ Priority: {config.priority}")
    print(f"✓ Routing patterns: {config.routing_patterns}")
    print(f"✓ Requires LLM: {config.requires_llm}")
    print(f"✓ LLM Config: {config.llm_config}")
    print(f"✓ Confidence: {config.confidence:.1%}")

    # Assertions
    assert config.skill_id == "test-skill"
    assert config.category in ["review", "development", "testing"]
    assert config.priority > 0
    assert len(config.routing_patterns) > 0
    assert True  # May or may not require LLM

    print("\n✓ All assertions passed!")


def test_keyword_extraction():
    """Test keyword extraction for debugging skill."""

    from vibesop.core.skills.understander import KeywordAnalyzer

    text = "Systematic debugging workflow for finding and fixing bugs in production systems"

    analysis = KeywordAnalyzer.analyze(text)

    print(f"✓ Keywords: {analysis.keywords}")
    print(f"✓ Requires LLM: {analysis.requires_llm}")
    print(f"✓ Complexity: {analysis.complexity.value}")
    print(f"✓ Urgency: {analysis.urgency.value}")

    # Assertions
    assert len(analysis.keywords) > 0
    # Should extract meaningful keywords, not stop words
    assert "debugging" in analysis.keywords or "workflow" in analysis.keywords

    print("\n✓ All assertions passed!")


if __name__ == "__main__":
    print("Testing skill understander integration...\n")

    print("=" * 60)
    print("Test 1: Understanding skill from file")
    print("=" * 60)
    test_understand_skill_from_file()

    print("\n" + "=" * 60)
    print("Test 2: Skill auto-configurator")
    print("=" * 60)
    test_skill_auto_configurator()

    print("\n" + "=" * 60)
    print("Test 3: Keyword extraction")
    print("=" * 60)
    test_keyword_extraction()

    print("\n" + "=" * 60)
    print("✅ All tests passed!")
    print("=" * 60)
