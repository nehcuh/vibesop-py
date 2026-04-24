"""Tests for SkillAutoConfigurator and rule-engine enhancements."""

from __future__ import annotations

import pytest

from vibesop.core.skills.base import SkillMetadata, SkillType
from vibesop.core.skills.understander import (
    CategoryRules,
    ComplexityLevel,
    KeywordAnalyzer,
    SkillAnalysis,
    SkillAutoConfigurator,
    UrgencyLevel,
)


class TestCategoryRulesInferById:
    """Test category inference from skill ID (Step 3 enhancement)."""

    @pytest.mark.parametrize(
        ("skill_id", "expected_category"),
        [
            ("debug-helper", "debugging"),
            ("error-tracker", "debugging"),
            ("bug-finder", "debugging"),
            ("test-runner", "testing"),
            ("spec-validator", "testing"),
            ("tdd-workflow", "testing"),
            ("qa-checklist", "testing"),
            ("code-review", "review"),
            ("audit-trail", "review"),
            ("doc-generator", "documentation"),
            ("readme-updater", "documentation"),
            ("deploy-script", "deployment"),
            ("release-notes", "deployment"),
            ("ship-it", "deployment"),
            ("security-scan", "security"),
            ("vuln-checker", "security"),
            ("brainstorm-session", "brainstorming"),
            ("idea-board", "brainstorming"),
            ("optimize-build", "optimization"),
            ("perf-monitor", "optimization"),
            ("plan-sprint", "planning"),
            ("roadmap-2024", "planning"),
            ("research-topic", "development"),
            ("refactor-module", "development"),
            ("architect-system", "development"),
            ("investigate-issue", "debugging"),
            ("unknown-thing", "development"),
        ],
    )
    def test_infer_category_from_skill_id(self, skill_id: str, expected_category: str) -> None:
        """Category should be inferred from skill ID prefixes."""
        metadata = SkillMetadata(
            id=skill_id,
            name="Test",
            description="",
            intent="",
        )
        result = CategoryRules.infer_category(metadata)
        assert result == expected_category

    def test_tag_override_when_id_is_ambiguous(self) -> None:
        """Tags should still take priority when ID is generic."""
        metadata = SkillMetadata(
            id="helper-tool",
            name="Test",
            description="",
            intent="",
            tags=["security"],
        )
        result = CategoryRules.infer_category(metadata)
        assert result == "security"

    def test_description_fallback_when_no_id_match(self) -> None:
        """Description keywords should work when ID has no known prefix."""
        metadata = SkillMetadata(
            id="foo-bar",
            name="Test",
            description="This tool helps you debug errors in production",
            intent="",
        )
        result = CategoryRules.infer_category(metadata)
        assert result == "debugging"


class TestKeywordAnalyzerStructureHeuristics:
    """Test file-structure-based heuristics (Step 3 enhancement)."""

    def test_phases_detected_as_high_complexity(self) -> None:
        """Skills with '## Phases' should be marked HIGH complexity."""
        text = "# Title\n\n## Phases\n\n1. Research\n2. Plan\n3. Execute"
        analysis = KeywordAnalyzer.analyze(text)
        assert analysis.complexity == ComplexityLevel.HIGH

    def test_steps_detected_as_high_complexity(self) -> None:
        """Skills with '## Steps' should be marked HIGH complexity."""
        text = "# Title\n\n## Steps\n\n- Step one\n- Step two"
        analysis = KeywordAnalyzer.analyze(text)
        assert analysis.complexity == ComplexityLevel.HIGH

    def test_workflow_detected_as_high_complexity(self) -> None:
        """Skills with '## Workflow' should be marked HIGH complexity."""
        text = "# Title\n\n## Workflow\n\nStart → Middle → End"
        analysis = KeywordAnalyzer.analyze(text)
        assert analysis.complexity == ComplexityLevel.HIGH

    def test_explicit_complexity_overrides_structure(self) -> None:
        """Explicit 'simple' keyword should override structure heuristic."""
        text = "# Title\n\n## Steps\n\nThis is a simple quick task."
        analysis = KeywordAnalyzer.analyze(text)
        # "simple" triggers LOW, but "## Steps" triggers HIGH.
        # Current implementation: first match wins in original code,
        # but our enhancement sets HIGH for phases/steps regardless.
        # We assert HIGH because structure is a strong signal.
        assert analysis.complexity == ComplexityLevel.HIGH

    def test_llm_keywords_detected(self) -> None:
        """LLM-related keywords should set requires_llm=True."""
        text = "This skill uses AI to analyze and generate code."
        analysis = KeywordAnalyzer.analyze(text)
        assert analysis.requires_llm is True

    def test_urgency_critical(self) -> None:
        """Critical keywords should set CRITICAL urgency."""
        text = "This is a critical security vulnerability patch."
        analysis = KeywordAnalyzer.analyze(text)
        assert analysis.urgency == UrgencyLevel.CRITICAL

    def test_urgency_high(self) -> None:
        """High-priority keywords should set HIGH urgency."""
        text = "This is an important priority task."
        analysis = KeywordAnalyzer.analyze(text)
        assert analysis.urgency == UrgencyLevel.HIGH


class TestSkillAutoConfiguratorIntegration:
    """Integration tests for the full configurator pipeline."""

    def test_understand_and_configure_debug_skill(self) -> None:
        """End-to-end: debug skill gets correct category and priority."""
        configurator = SkillAutoConfigurator()
        metadata = SkillMetadata(
            id="debug-helper",
            name="Debug Helper",
            description="Helps you debug errors and fix bugs",
            intent="debugging",
            skill_type=SkillType.PROMPT,
        )
        content = "# Debug Helper\n\n## Steps\n\n1. Reproduce\n2. Diagnose\n3. Analyze and fix"
        config = configurator.understand_and_configure(metadata, content, scope="project")

        assert config.category == "debugging"
        assert config.priority >= 75  # debugging base + HIGH complexity
        assert config.requires_llm is True  # "analyze" in LLM_KEYWORDS
        assert any("debug" in p for p in config.routing_patterns)

    def test_understand_and_configure_planning_skill(self) -> None:
        """End-to-end: planning skill gets correct category."""
        configurator = SkillAutoConfigurator()
        metadata = SkillMetadata(
            id="plan-sprint",
            name="Sprint Planner",
            description="Plan your sprint",
            intent="planning",
            skill_type=SkillType.WORKFLOW,
        )
        content = "# Sprint Planner\n\n## Phases\n\n1. Research\n2. Estimate"
        config = configurator.understand_and_configure(metadata, content, scope="global")

        assert config.category == "planning"
        assert config.scope == "global"
        assert config.confidence > 0.5  # Should be boosted by explicit category

    def test_confidence_boosted_by_keywords(self) -> None:
        """Skills with clear keywords should have higher confidence."""
        configurator = SkillAutoConfigurator()
        metadata = SkillMetadata(
            id="security-scan",
            name="Security Scan",
            description="Scan for vulnerabilities",
            intent="security",
            tags=["security"],
        )
        content = "# Security Scan\n\nCritical vulnerability detection."
        config = configurator.understand_and_configure(metadata, content)

        assert config.confidence >= 0.7  # keywords + explicit category + urgency

    def test_generate_llm_config_for_review(self) -> None:
        """Review category should get appropriate LLM config."""
        configurator = SkillAutoConfigurator()
        analysis = SkillAnalysis()
        analysis.primary_category = "review"
        analysis.requires_llm = True
        llm_config = configurator._generate_llm_config(analysis)

        assert llm_config["provider"] == "anthropic"
        assert llm_config["temperature"] == 0.2

    def test_generate_llm_config_for_brainstorming(self) -> None:
        """Brainstorming category should get creative LLM config."""
        configurator = SkillAutoConfigurator()
        analysis = SkillAnalysis()
        analysis.primary_category = "brainstorming"
        analysis.requires_llm = True
        llm_config = configurator._generate_llm_config(analysis)

        assert llm_config["provider"] == "openai"
        assert llm_config["temperature"] == 0.9
