"""Tests for enhanced workflow parser."""

from __future__ import annotations

import pytest

from vibesop.core.skills.workflow import (
    StepType,
    Workflow,
    parse_workflow_from_markdown,
)


class TestEnhancedParser:
    """Test enhanced markdown parser."""

    def test_parse_with_frontmatter(self) -> None:
        """Test parsing SKILL.md with YAML frontmatter."""
        markdown = """---
name: Test Skill
description: A test skill for parsing
version: 1.0.0
---

# Test Skill

This is a test skill.

## Steps

1. First step
   Do something first

2. Second step
   Do something second
"""

        workflow = parse_workflow_from_markdown(markdown, "test-skill")

        assert workflow.skill_id == "test-skill"
        assert workflow.name == "Test Skill"
        assert "A test skill for parsing" in workflow.description
        assert len(workflow.steps) == 2
        assert workflow.metadata.get("version") == "1.0.0"

    def test_parse_numbered_steps(self) -> None:
        """Test parsing numbered steps (1., 2., etc.)."""
        markdown = """# Test

## Steps

1. Initialize
   Set up the environment

2. Execute
   Run the main logic

3. Cleanup
   Clean up resources
"""

        workflow = parse_workflow_from_markdown(markdown, "test")

        assert len(workflow.steps) == 3
        assert workflow.steps[0].description == "Initialize"
        assert workflow.steps[1].description == "Execute"
        assert workflow.steps[2].description == "Cleanup"

    def test_parse_bullet_steps(self) -> None:
        """Test parsing bullet steps (- or *)."""
        markdown = """# Test

## Steps

- Prepare
  Get ready

- Act
  Do the work

- Verify
  Check results
"""

        workflow = parse_workflow_from_markdown(markdown, "test")

        # Bullet points should be parsed as independent steps
        assert len(workflow.steps) >= 3
        # Check that we have the main steps
        descriptions = [step.description for step in workflow.steps]
        assert "Prepare" in descriptions
        assert "Act" in descriptions
        assert "Verify" in descriptions

    def test_parse_mixed_steps(self) -> None:
        """Test parsing mixed numbered and bullet steps."""
        markdown = """# Test

## Steps

1. First step
- Second step
2. Third step
- Fourth step
"""

        workflow = parse_workflow_from_markdown(markdown, "test")

        # Mixed format: bullets after numbered steps become sub-steps
        # Independent bullets become separate steps
        assert len(workflow.steps) >= 2
        # First step should be "First step"
        assert workflow.steps[0].description == "First step"

    def test_parse_step_content(self) -> None:
        """Test parsing step content (indented lines)."""
        markdown = """# Test

## Steps

1. Complex step
   This is a detailed instruction
   that spans multiple lines
   and should be captured
"""

        workflow = parse_workflow_from_markdown(markdown, "test")

        assert len(workflow.steps) == 1
        assert "detailed instruction" in workflow.steps[0].instruction
        assert "spans multiple lines" in workflow.steps[0].instruction

    def test_detect_verification_step(self) -> None:
        """Test detection of verification steps."""
        markdown = """# Test

## Steps

1. Verify the output
   Check that everything is correct
"""

        workflow = parse_workflow_from_markdown(markdown, "test")

        assert len(workflow.steps) == 1
        assert workflow.steps[0].type == StepType.VERIFICATION

    def test_detect_tool_call_step(self) -> None:
        """Test detection of tool call steps."""
        markdown = """# Test

## Steps

1. Call the read tool
   Execute read_file command
"""

        workflow = parse_workflow_from_markdown(markdown, "test")

        assert len(workflow.steps) == 1
        assert workflow.steps[0].type == StepType.TOOL_CALL

    def test_detect_conditional_step(self) -> None:
        """Test detection of conditional steps."""
        markdown = """# Test

## Steps

1. If condition is met
   Proceed with action
"""

        workflow = parse_workflow_from_markdown(markdown, "test")

        assert len(workflow.steps) == 1
        assert workflow.steps[0].type == StepType.CONDITIONAL

    def test_detect_loop_step(self) -> None:
        """Test detection of loop steps."""
        markdown = """# Test

## Steps

1. Repeat for each item
   Process all items
"""

        workflow = parse_workflow_from_markdown(markdown, "test")

        assert len(workflow.steps) == 1
        assert workflow.steps[0].type == StepType.LOOP

    def test_parse_without_steps(self) -> None:
        """Test parsing without explicit steps section."""
        markdown = """# Test Skill

This skill does something useful.
It has multiple lines of description.
"""

        workflow = parse_workflow_from_markdown(markdown, "test")

        assert len(workflow.steps) == 1
        assert workflow.steps[0].type == StepType.INSTRUCTION
        assert "does something useful" in workflow.steps[0].instruction

    def test_parse_empty_content(self) -> None:
        """Test parsing empty or minimal content."""
        markdown = "# Test\n"

        workflow = parse_workflow_from_markdown(markdown, "test")

        assert len(workflow.steps) == 1
        assert workflow.steps[0].description == "test"

    def test_parse_real_world_skill(self) -> None:
        """Test parsing a real-world skill format."""
        markdown = """---
id: systematic-debugging
name: Systematic Debugging
description: Find root cause before attempting fixes
---

# Systematic Debugging

Find root cause before attempting fixes. Prevents jumping to solutions without proper diagnosis.

## Process

1. Gather information
   - Read error messages
   - Check logs
   - Reproduce the issue

2. Identify patterns
   Look for common patterns in the errors

3. Form hypotheses
   Create testable hypotheses about the root cause

4. Test hypotheses
   Verify each hypothesis with tests

5. Fix root cause
   Address the actual root cause, not symptoms
"""

        workflow = parse_workflow_from_markdown(markdown, "systematic-debugging")

        assert workflow.skill_id == "systematic-debugging"
        assert workflow.name == "Systematic Debugging"
        assert "Find root cause" in workflow.description
        assert len(workflow.steps) == 5
        assert workflow.steps[0].description == "Gather information"
        assert workflow.steps[4].description == "Fix root cause"

    def test_parse_gstack_style(self) -> None:
        """Test parsing gstack-style skill format."""
        markdown = """---
name: Code Review
namespace: gstack
---

# Code Review

Pre-landing PR review. Analyze diff against base branch.

## Review Process

1. Read the diff
   Understand what changed

2. Check for SQL safety
   Verify database queries

3. Check for trust boundary violations
   Ensure proper validation

4. Review conditional side effects
   Check for unexpected behavior
"""

        workflow = parse_workflow_from_markdown(markdown, "gstack/review")

        assert workflow.name == "Code Review"
        assert workflow.metadata.get("namespace") == "gstack"
        assert len(workflow.steps) == 4

    def test_parse_superpowers_style(self) -> None:
        """Test parsing superpowers-style skill format."""
        markdown = """---
name: TDD Workflow
namespace: superpowers
---

# Test-Driven Development

Follow red-green-refactor cycle.

## Steps

1. Red: Write a failing test
   Write a test that fails

2. Green: Make it pass
   Write minimal code to pass

3. Refactor: Improve
   Clean up the code
"""

        workflow = parse_workflow_from_markdown(markdown, "superpowers/tdd")

        assert workflow.name == "TDD Workflow"
        assert len(workflow.steps) == 3

    def test_multiline_description(self) -> None:
        """Test parsing multi-line description."""
        markdown = """# Test

This is a detailed description
that spans multiple lines
and should be captured properly.

## Steps

1. Do something
"""

        workflow = parse_workflow_from_markdown(markdown, "test")

        assert "detailed description" in workflow.description
        assert "spans multiple lines" in workflow.description

    def test_preserve_metadata(self) -> None:
        """Test that frontmatter metadata is preserved."""
        markdown = """---
name: Test
version: 2.0.0
author: Test Author
tags: [test, example]
---

# Test Skill

## Steps

1. Test step
"""

        workflow = parse_workflow_from_markdown(markdown, "test")

        assert workflow.metadata.get("version") == "2.0.0"
        assert workflow.metadata.get("author") == "Test Author"
        assert workflow.metadata.get("tags") == ["test", "example"]
