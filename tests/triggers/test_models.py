"""Tests for trigger pattern models."""

import pytest
from pydantic import ValidationError

from vibesop.triggers.models import (
    TriggerPattern,
    PatternMatch,
    PatternCategory,
)


class TestPatternCategory:
    """Test PatternCategory enum."""

    def test_all_categories_exist(self):
        """Test all expected categories exist."""
        assert PatternCategory.SECURITY == "security"
        assert PatternCategory.CONFIG == "config"
        assert PatternCategory.DEV == "dev"
        assert PatternCategory.DOCS == "docs"
        assert PatternCategory.PROJECT == "project"

    def test_category_to_string(self):
        """Test category converts to string correctly."""
        assert str(PatternCategory.SECURITY) == "security"
        assert str(PatternCategory.CONFIG) == "config"


class TestTriggerPattern:
    """Test TriggerPattern model validation."""

    def test_minimal_valid_pattern(self):
        """Test creating pattern with minimal required fields."""
        pattern = TriggerPattern(
            pattern_id="test/minimal",
            name="Minimal Pattern",
            description="A minimal test pattern",
            category=PatternCategory.DEV,
            keywords=["test"],
            skill_id="/test"
        )

        assert pattern.pattern_id == "test/minimal"
        assert pattern.name == "Minimal Pattern"
        assert pattern.keywords == ["test"]
        assert pattern.skill_id == "/test"
        assert pattern.priority == 50  # default
        assert pattern.confidence_threshold == 0.6  # default

    def test_complete_pattern(self, sample_security_pattern):
        """Test creating pattern with all fields."""
        pattern = sample_security_pattern

        assert pattern.pattern_id == "security/scan"
        assert pattern.name == "Security Scan"
        assert pattern.category == PatternCategory.SECURITY
        assert len(pattern.keywords) == 5
        assert len(pattern.regex_patterns) == 3
        assert pattern.skill_id == "/security/scan"
        assert pattern.workflow_id == "security-review"
        assert pattern.priority == 100
        assert pattern.confidence_threshold == 0.6
        assert len(pattern.examples) == 3

    def test_pattern_id_format_validation(self):
        """Test pattern_id must contain '/' separator."""
        with pytest.raises(ValidationError, match="must contain '/'"):
            TriggerPattern(
                pattern_id="invalid",
                name="Invalid",
                description="Invalid pattern ID",
                category=PatternCategory.DEV,
                skill_id="/test"
            )

    def test_pattern_id_multiple_slashes(self):
        """Test pattern_id with multiple slashes is rejected."""
        with pytest.raises(ValidationError, match="must be.*category/name.*format"):
            TriggerPattern(
                pattern_id="test/multiple/invalid",
                name="Invalid",
                description="Invalid pattern ID",
                category=PatternCategory.DEV,
                skill_id="/test"
            )

    def test_keywords_normalization(self):
        """Test keywords are normalized and deduplicated."""
        pattern = TriggerPattern(
            pattern_id="test/keywords",
            name="Keywords Test",
            description="Test keyword normalization",
            category=PatternCategory.DEV,
            keywords=["Test", "test", " TEST ", "Another"],
            skill_id="/test"
        )

        # Should be normalized to lowercase, stripped, and deduplicated
        assert pattern.keywords == ["test", "another"]

    def test_keywords_empty_string_rejected(self):
        """Test empty strings in keywords are rejected."""
        with pytest.raises(ValidationError, match="Keywords cannot be empty"):
            TriggerPattern(
                pattern_id="test/empty",
                name="Empty Keyword",
                description="Test empty keyword rejection",
                category=PatternCategory.DEV,
                keywords=["valid", "", "also valid"],
                skill_id="/test"
            )

    def test_priority_range_validation(self):
        """Test priority must be between 1 and 100."""
        # Too low
        with pytest.raises(ValidationError, match="greater than or equal to 1"):
            TriggerPattern(
                pattern_id="test/priority",
                name="Priority Test",
                description="Test priority validation",
                category=PatternCategory.DEV,
                priority=0,
                skill_id="/test"
            )

        # Too high
        with pytest.raises(ValidationError, match="less than or equal to 100"):
            TriggerPattern(
                pattern_id="test/priority",
                name="Priority Test",
                description="Test priority validation",
                category=PatternCategory.DEV,
                priority=101,
                skill_id="/test"
            )

    def test_confidence_threshold_range(self):
        """Test confidence_threshold must be between 0.0 and 1.0."""
        # Negative
        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            TriggerPattern(
                pattern_id="test/confidence",
                name="Confidence Test",
                description="Test confidence validation",
                category=PatternCategory.DEV,
                confidence_threshold=-0.1,
                skill_id="/test"
            )

        # Greater than 1
        with pytest.raises(ValidationError, match="less than or equal to 1"):
            TriggerPattern(
                pattern_id="test/confidence",
                name="Confidence Test",
                description="Test confidence validation",
                category=PatternCategory.DEV,
                confidence_threshold=1.1,
                skill_id="/test"
            )

    def test_matches_threshold(self):
        """Test matches_threshold method."""
        pattern = TriggerPattern(
            pattern_id="test/threshold",
            name="Threshold Test",
            description="Test threshold checking",
            category=PatternCategory.DEV,
            confidence_threshold=0.7,
            skill_id="/test"
        )

        assert pattern.matches_threshold(0.8) is True
        assert pattern.matches_threshold(0.7) is True
        assert pattern.matches_threshold(0.6) is False
        assert pattern.matches_threshold(0.0) is False

    def test_optional_fields_default_to_none_or_empty(self):
        """Test optional fields have correct defaults."""
        pattern = TriggerPattern(
            pattern_id="test/optional",
            name="Optional Fields",
            description="Test optional field defaults",
            category=PatternCategory.DEV,
            skill_id="/test"
        )

        assert pattern.workflow_id is None
        assert pattern.keywords == []
        assert pattern.regex_patterns == []
        assert pattern.examples == []
        assert pattern.metadata == {}


class TestPatternMatch:
    """Test PatternMatch model."""

    def test_minimal_match(self):
        """Test creating match with minimal fields."""
        match = PatternMatch(
            pattern_id="test/pattern",
            confidence=0.85
        )

        assert match.pattern_id == "test/pattern"
        assert match.confidence == 0.85
        assert match.metadata == {}
        assert match.matched_keywords == []
        assert match.matched_regex == []
        assert match.semantic_score is None

    def test_complete_match(self):
        """Test creating match with all fields."""
        match = PatternMatch(
            pattern_id="security/scan",
            confidence=0.95,
            metadata={"category": "security", "strategy": "keyword+regex"},
            matched_keywords=["扫描", "安全"],
            matched_regex=[r"扫描.*安全"],
            semantic_score=0.85
        )

        assert match.pattern_id == "security/scan"
        assert match.confidence == 0.95
        assert match.metadata["category"] == "security"
        assert "扫描" in match.matched_keywords
        assert r"扫描.*安全" in match.matched_regex
        assert match.semantic_score == 0.85

    def test_confidence_range_validation(self):
        """Test confidence must be between 0.0 and 1.0."""
        # Negative
        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            PatternMatch(
                pattern_id="test/pattern",
                confidence=-0.1
            )

        # Greater than 1
        with pytest.raises(ValidationError, match="less than or equal to 1"):
            PatternMatch(
                pattern_id="test/pattern",
                confidence=1.5
            )

    def test_semantic_score_range(self):
        """Test semantic_score must be between 0.0 and 1.0."""
        # Greater than 1
        with pytest.raises(ValidationError, match="less than or equal to 1"):
            PatternMatch(
                pattern_id="test/pattern",
                confidence=0.8,
                semantic_score=1.5
            )

    def test_meets_threshold(self):
        """Test meets_threshold method."""
        match = PatternMatch(
            pattern_id="test/pattern",
            confidence=0.75
        )

        assert match.meets_threshold(0.7) is True
        assert match.meets_threshold(0.75) is True
        assert match.meets_threshold(0.8) is False


class TestPatternCategories:
    """Test patterns in different categories."""

    def test_security_category(self, sample_security_pattern):
        """Test security pattern has correct category."""
        assert sample_security_pattern.category == PatternCategory.SECURITY

    def test_config_category(self, sample_config_pattern):
        """Test config pattern has correct category."""
        assert sample_config_pattern.category == PatternCategory.CONFIG

    def test_dev_category(self, sample_dev_pattern):
        """Test dev pattern has correct category."""
        assert sample_dev_pattern.category == PatternCategory.DEV
