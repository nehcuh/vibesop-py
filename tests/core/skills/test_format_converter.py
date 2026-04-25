"""Tests for SKILL.md format converters."""

from pathlib import Path

from vibesop.core.skills import (
    FormatConverterRegistry,
    GstackConverter,
    SuperpowersConverter,
)


class TestGstackConverter:
    """Test gstack format converter."""

    def test_can_convert_gstack_format(self):
        """Test detecting gstack format."""
        converter = GstackConverter()

        content = """# gstack/review

> Pre-landing PR review. Analyzes diff.

**Skill ID**: `gstack/review`
**Namespace**: builtin
**Version**: 1.0.0
"""
        assert converter.can_convert(content) is True

    def test_cannot_convert_standard_format(self):
        """Test rejecting standard YAML format."""
        converter = GstackConverter()

        content = """---
id: builtin/test
name: test
---
"""
        assert converter.can_convert(content) is False

    def test_convert_gstack_to_standard(self):
        """Test converting gstack format."""
        converter = GstackConverter()

        content = """# gstack/review

> Pre-landing PR review. Analyzes diff for SQL safety.

**Skill ID**: `gstack/review`
**Namespace**: builtin
**Version**: 1.0.0
"""

        converted, metadata = converter.convert(
            content, Path("/fake/path/review/SKILL.md")
        )

        # Check metadata
        assert metadata["id"] == "gstack/review"
        assert metadata["name"] == "review"
        assert metadata["namespace"] == "gstack"
        assert metadata["intent"] == "code-review"
        assert metadata["version"] == "1.0.0"
        assert metadata["type"] == "prompt"

        # Check converted content has YAML front matter
        assert converted.startswith("---")
        assert "id: gstack/review" in converted
        assert "intent: code-review" in converted


class TestSuperpowersConverter:
    """Test superpowers format converter."""

    def test_can_convert_superpowers_format(self):
        """Test detecting superpowers format."""
        converter = SuperpowersConverter()

        content = """---
name: brainstorming
description: "Brainstorm ideas"
---
"""
        assert converter.can_convert(content) is True

    def test_cannot_convert_complete_format(self):
        """Test rejecting complete YAML format."""
        converter = SuperpowersConverter()

        content = """---
id: superpowers/test
name: test
intent: testing
---
"""
        assert converter.can_convert(content) is False

    def test_convert_superpowers_to_standard(self):
        """Test converting superpowers format."""
        converter = SuperpowersConverter()

        content = """---
name: brainstorming
description: "You MUST use this before any creative work"
---
"""

        converted, metadata = converter.convert(
            content, Path("/fake/path/brainstorming/SKILL.md")
        )

        # Check metadata
        assert metadata["id"] == "superpowers/brainstorming"
        assert metadata["name"] == "brainstorming"
        assert metadata["namespace"] == "superpowers"
        assert metadata["intent"] == "brainstorming"
        assert metadata["type"] == "prompt"

        # Check converted content
        assert converted.startswith("---")
        assert "id: superpowers/brainstorming" in converted
        assert "intent: brainstorming" in converted


class TestFormatConverterRegistry:
    """Test format converter registry."""

    def test_registry_can_convert_gstack(self):
        """Test registry detects gstack format."""
        registry = FormatConverterRegistry()

        content = """# gstack/review
**Skill ID**: `gstack/review`
"""
        assert registry.can_convert(content) is True

    def test_registry_can_convert_superpowers(self):
        """Test registry detects superpowers format."""
        registry = FormatConverterRegistry()

        content = """---
name: brainstorming
description: "test"
---
"""
        assert registry.can_convert(content) is True

    def test_registry_cannot_convert_complete(self):
        """Test registry rejects complete format."""
        registry = FormatConverterRegistry()

        content = """---
id: builtin/test
name: test
intent: testing
---
"""
        assert registry.can_convert(content) is False

    def test_registry_auto_selects_converter(self):
        """Test registry automatically selects correct converter."""
        registry = FormatConverterRegistry()

        # Test gstack
        gstack_content = """# gstack/review
**Skill ID**: `gstack/review`
"""
        result = registry.convert(gstack_content, Path("/fake/review/SKILL.md"))
        assert result is not None
        _, metadata = result
        assert metadata["namespace"] == "gstack"

        # Test superpowers
        superpowers_content = """---
name: brainstorming
description: "test"
---
"""
        result = registry.convert(
            superpowers_content, Path("/fake/brainstorming/SKILL.md")
        )
        assert result is not None
        _, metadata = result
        assert metadata["namespace"] == "superpowers"
