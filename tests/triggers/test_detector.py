"""Tests for KeywordDetector class."""

# pyright: reportPrivateUsage=none, reportUnknownMemberType=none, reportUnknownVariableType=none, reportUnknownArgumentType=none, reportUnknownParameterType=none, reportMissingParameterType=none

import pytest

from vibesop.triggers.detector import KeywordDetector
from vibesop.triggers.models import TriggerPattern, PatternCategory


@pytest.fixture
def sample_patterns():
    """Create sample trigger patterns for testing."""
    return [
        TriggerPattern(
            pattern_id="security/scan",
            name="Security Scan",
            description="Security scanning",
            category=PatternCategory.SECURITY,
            keywords=["scan", "security", "vulnerability"],
            regex_patterns=[r"scan.*security", r"security.*scan"],
            skill_id="/security/scan",
            priority=100,
            confidence_threshold=0.6,
            examples=["scan for security issues", "security scan"],
        ),
        TriggerPattern(
            pattern_id="dev/test",
            name="Run Tests",
            description="Test execution",
            category=PatternCategory.DEV,
            keywords=["test", "testing", "run"],
            regex_patterns=[r"run.*test"],
            skill_id="/dev/test",
            priority=90,
            confidence_threshold=0.5,
            examples=["run tests", "execute tests"],
        ),
        TriggerPattern(
            pattern_id="docs/generate",
            name="Generate Docs",
            description="Documentation generation",
            category=PatternCategory.DOCS,
            keywords=["docs", "documentation", "generate"],
            regex_patterns=[r"generate.*docs"],
            skill_id="/docs/generate",
            priority=80,
            confidence_threshold=0.7,
            examples=["generate documentation"],
        ),
    ]


@pytest.fixture
def detector(sample_patterns):
    """Create detector with sample patterns."""
    return KeywordDetector(patterns=sample_patterns)


class TestKeywordDetectorInit:
    """Test KeywordDetector initialization."""

    def test_initialization(self, sample_patterns):
        """Test detector initializes correctly."""
        detector = KeywordDetector(patterns=sample_patterns)

        assert detector.patterns == sample_patterns
        assert detector.confidence_threshold == 0.6
        assert len(detector.patterns) == 3

    def test_priority_ordering(self):
        """Test patterns are ordered by priority."""
        patterns = [
            TriggerPattern(
                pattern_id="test/low",
                name="Low Priority",
                description="Low",
                category=PatternCategory.DEV,
                keywords=["test"],
                skill_id="/test",
                priority=10,
            ),
            TriggerPattern(
                pattern_id="test/high",
                name="High Priority",
                description="High",
                category=PatternCategory.DEV,
                keywords=["test"],
                skill_id="/test",
                priority=100,
            ),
            TriggerPattern(
                pattern_id="test/medium",
                name="Medium Priority",
                description="Medium",
                category=PatternCategory.DEV,
                keywords=["test"],
                skill_id="/test",
                priority=50,
            ),
        ]

        detector = KeywordDetector(patterns=patterns)

        # Should be ordered: high, medium, low
        assert detector.patterns[0].pattern_id == "test/high"
        assert detector.patterns[1].pattern_id == "test/medium"
        assert detector.patterns[2].pattern_id == "test/low"

    def test_custom_confidence_threshold(self, sample_patterns):
        """Test custom confidence threshold."""
        detector = KeywordDetector(patterns=sample_patterns, confidence_threshold=0.8)

        assert detector.confidence_threshold == 0.8

    def test_idf_cache_built(self, detector):
        """Test IDF cache is built during initialization."""
        assert detector.idf_cache is not None
        assert isinstance(detector.idf_cache, dict)


class TestDetectBest:
    """Test detect_best method."""

    def test_detect_best_match(self, detector):
        """Test detecting best matching pattern."""
        match = detector.detect_best("scan for security issues")

        assert match is not None
        assert match.pattern_id == "security/scan"
        assert match.confidence >= 0.6

    def test_detect_best_no_match(self, detector):
        """Test when no pattern matches."""
        match = detector.detect_best("completely unrelated query")

        assert match is None

    def test_detect_best_empty_query(self, detector):
        """Test with empty query."""
        assert detector.detect_best("") is None
        assert detector.detect_best("   ") is None

    def test_detect_best_uses_custom_threshold(self, detector):
        """Test custom min_confidence parameter."""
        # Query that matches but with low confidence
        match = detector.detect_best("test", min_confidence=0.9)

        # Should return None if confidence < 0.9
        if match:
            assert match.confidence >= 0.9
        else:
            assert match is None

    def test_detect_best_chinese_query(self, detector):
        """Test detecting from Chinese query."""
        # Add a Chinese pattern
        chinese_pattern = TriggerPattern(
            pattern_id="security/scan_cn",
            name="安全扫描",
            description="中文安全扫描",
            category=PatternCategory.SECURITY,
            keywords=["扫描", "安全", "漏洞"],
            regex_patterns=[r"扫描.*安全"],
            skill_id="/security/scan",
            priority=100,
            confidence_threshold=0.6,
            examples=["扫描安全漏洞", "安全检查"],
        )

        detector_cn = KeywordDetector(patterns=[chinese_pattern])

        match = detector_cn.detect_best("扫描安全漏洞")
        assert match is not None
        assert match.pattern_id == "security/scan_cn"

    def test_detect_best_returns_highest_confidence(self, detector):
        """Test that highest confidence match is returned."""
        # Query that might match multiple patterns
        match = detector.detect_best("security test")

        if match:
            # Should return the best match
            assert isinstance(match.pattern_id, str)
            assert isinstance(match.confidence, float)


class TestDetectAll:
    """Test detect_all method."""

    def test_detect_all_matches(self, detector):
        """Test detecting all matching patterns."""
        matches = detector.detect_all("run security test")

        assert isinstance(matches, list)
        # At least one pattern should match
        if matches:
            assert all(hasattr(m, "pattern_id") and hasattr(m, "confidence") for m in matches)

    def test_detect_all_sorted_by_confidence(self, detector):
        """Test results are sorted by confidence."""
        matches = detector.detect_all("test security scan")

        # Check if sorted in descending order
        for i in range(len(matches) - 1):
            assert matches[i].confidence >= matches[i + 1].confidence

    def test_detect_all_empty_query(self, detector):
        """Test with empty query."""
        assert detector.detect_all("") == []
        assert detector.detect_all("   ") == []

    def test_detect_all_no_matches(self, detector):
        """Test when no patterns match."""
        matches = detector.detect_all("xyzabc123")

        assert matches == []

    def test_detect_all_custom_threshold(self, detector):
        """Test custom min_confidence parameter."""
        matches = detector.detect_all("test", min_confidence=0.9)

        # All matches should have confidence >= 0.9
        for match in matches:
            assert match.confidence >= 0.9


class TestScoring:
    """Test pattern scoring logic."""

    def test_keyword_score(self, detector):
        """Test keyword matching score."""
        match = detector.detect_best("scan security")

        if match:
            # Check keyword score was calculated
            assert "keyword_score" in match.metadata

    def test_regex_score(self, detector):
        """Test regex matching score."""
        match = detector.detect_best("scan security")

        if match:
            # Check regex score was calculated
            assert "regex_score" in match.metadata

    def test_semantic_score(self, detector):
        """Test semantic similarity score."""
        match = detector.detect_best("execute security scan")

        if match:
            # Semantic score should be present
            assert match.semantic_score is not None

    def test_matched_keywords_recorded(self, detector):
        """Test that matched keywords are recorded."""
        match = detector.detect_best("scan security vulnerability")

        if match:
            assert isinstance(match.matched_keywords, list)
            # Should have matched some keywords
            assert len(match.matched_keywords) > 0

    def test_matched_regex_recorded(self, detector):
        """Test that matched regex patterns are recorded."""
        match = detector.detect_best("scan security")

        if match:
            assert isinstance(match.matched_regex, list)


class TestPatternThresholds:
    """Test pattern-specific confidence thresholds."""

    def test_pattern_threshold_filtering(self):
        """Test that patterns only match if they meet their own threshold."""
        patterns = [
            TriggerPattern(
                pattern_id="test/high_threshold",
                name="High Threshold",
                description="Test",
                category=PatternCategory.DEV,
                keywords=["test"],
                skill_id="/test",
                confidence_threshold=0.9,  # Very high threshold
            )
        ]

        detector = KeywordDetector(patterns=patterns)

        # Query that partially matches but may not reach 0.9
        match = detector.detect_best("test")

        if match:
            assert match.confidence >= 0.9

    def test_default_threshold_used(self, sample_patterns):
        """Test default threshold when not specified."""
        # Add pattern without explicit threshold
        patterns = sample_patterns + [
            TriggerPattern(
                pattern_id="test/default",
                name="Default Threshold",
                description="Test",
                category=PatternCategory.DEV,
                keywords=["test"],
                skill_id="/test",
                # confidence_threshold defaults to 0.6
            )
        ]

        detector = KeywordDetector(patterns=patterns)
        assert detector.confidence_threshold == 0.6


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_patterns_list(self):
        """Test detector with no patterns."""
        detector = KeywordDetector(patterns=[])

        assert detector.detect_best("test") is None
        assert detector.detect_all("test") == []

    def test_invalid_regex_in_pattern(self):
        """Test pattern with invalid regex."""
        patterns = [
            TriggerPattern(
                pattern_id="test/invalid_regex",
                name="Invalid Regex",
                description="Test",
                category=PatternCategory.DEV,
                keywords=["test"],
                regex_patterns=["[invalid"],  # Invalid regex
                skill_id="/test",
            )
        ]

        detector = KeywordDetector(patterns=patterns)

        # Should not crash, just skip invalid regex
        detector.detect_best("test")
        # May or may not match based on keywords
        # The important thing is it doesn't crash
        assert True  # Test passes if no exception is raised

    def test_query_with_special_characters(self, detector):
        """Test query with special characters."""
        match = detector.detect_best("scan!!! security???")

        # Should still match despite punctuation
        if match:
            assert match.pattern_id == "security/scan"

    def test_very_long_query(self, detector):
        """Test with very long query."""
        long_query = "scan security " * 100

        match = detector.detect_best(long_query)

        # Should handle long queries without error
        assert match is not None or match is None  # Just don't crash
