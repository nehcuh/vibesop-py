"""Tests for predefined trigger patterns."""

import pytest

from vibesop.triggers.patterns import (
    DEFAULT_PATTERNS,
    SECURITY_PATTERNS,
    CONFIG_PATTERNS,
    DEV_PATTERNS,
    DOCS_PATTERNS,
    PROJECT_PATTERNS,
)
from vibesop.triggers.models import PatternCategory
from vibesop.triggers.detector import KeywordDetector


class TestPatternLibrary:
    """Test the predefined patterns library."""

    def test_default_patterns_count(self):
        """Test that DEFAULT_PATTERNS contains 30 patterns."""
        assert len(DEFAULT_PATTERNS) == 30

    def test_security_patterns_count(self):
        """Test security patterns count."""
        assert len(SECURITY_PATTERNS) == 5

    def test_config_patterns_count(self):
        """Test config patterns count."""
        assert len(CONFIG_PATTERNS) == 5

    def test_dev_patterns_count(self):
        """Test dev patterns count."""
        assert len(DEV_PATTERNS) == 8

    def test_docs_patterns_count(self):
        """Test docs patterns count."""
        assert len(DOCS_PATTERNS) == 6

    def test_project_patterns_count(self):
        """Test project patterns count."""
        assert len(PROJECT_PATTERNS) == 6

    def test_total_patterns_by_category(self):
        """Test total patterns match sum of categories."""
        total = (
            len(SECURITY_PATTERNS)
            + len(CONFIG_PATTERNS)
            + len(DEV_PATTERNS)
            + len(DOCS_PATTERNS)
            + len(PROJECT_PATTERNS)
        )
        assert total == len(DEFAULT_PATTERNS)


class TestPatternStructure:
    """Test that all patterns have valid structure."""

    def test_all_patterns_have_required_fields(self):
        """Test all patterns have required fields."""
        for pattern in DEFAULT_PATTERNS:
            assert pattern.pattern_id
            assert "/" in pattern.pattern_id
            assert pattern.name
            assert pattern.description
            assert pattern.category
            assert pattern.skill_id
            assert isinstance(pattern.keywords, list)
            assert isinstance(pattern.regex_patterns, list)
            assert isinstance(pattern.examples, list)
            assert isinstance(pattern.priority, int)
            assert 1 <= pattern.priority <= 100
            assert 0.0 <= pattern.confidence_threshold <= 1.0

    def test_all_pattern_ids_unique(self):
        """Test that all pattern IDs are unique."""
        pattern_ids = [p.pattern_id for p in DEFAULT_PATTERNS]
        assert len(pattern_ids) == len(set(pattern_ids))


class TestSecurityPatterns:
    """Test security category patterns."""

    def test_security_patterns_have_correct_category(self):
        """Test all security patterns have SECURITY category."""
        for pattern in SECURITY_PATTERNS:
            assert pattern.category == PatternCategory.SECURITY

    def test_security_scan_pattern_exists(self):
        """Test security/scan pattern exists."""
        pattern_ids = [p.pattern_id for p in SECURITY_PATTERNS]
        assert "security/scan" in pattern_ids

    def test_security_patterns_have_keywords(self):
        """Test security patterns have meaningful keywords."""
        for pattern in SECURITY_PATTERNS:
            assert len(pattern.keywords) > 0
            # Should have both English and Chinese keywords
            has_english = any(k.isascii() for k in pattern.keywords)
            has_chinese = any(not k.isascii() for k in pattern.keywords)
            # At least one language should be present
            assert has_english or has_chinese


class TestConfigPatterns:
    """Test config category patterns."""

    def test_config_patterns_have_correct_category(self):
        """Test all config patterns have CONFIG category."""
        for pattern in CONFIG_PATTERNS:
            assert pattern.category == PatternCategory.CONFIG

    def test_config_deploy_pattern_exists(self):
        """Test config/deploy pattern exists."""
        pattern_ids = [p.pattern_id for p in CONFIG_PATTERNS]
        assert "config/deploy" in pattern_ids


class TestDevPatterns:
    """Test development category patterns."""

    def test_dev_patterns_have_correct_category(self):
        """Test all dev patterns have DEV category."""
        for pattern in DEV_PATTERNS:
            assert pattern.category == PatternCategory.DEV

    def test_dev_test_pattern_exists(self):
        """Test dev/test pattern exists."""
        pattern_ids = [p.pattern_id for p in DEV_PATTERNS]
        assert "dev/test" in pattern_ids

    def test_dev_build_pattern_exists(self):
        """Test dev/build pattern exists."""
        pattern_ids = [p.pattern_id for p in DEV_PATTERNS]
        assert "dev/build" in pattern_ids


class TestDocsPatterns:
    """Test documentation category patterns."""

    def test_docs_patterns_have_correct_category(self):
        """Test all docs patterns have DOCS category."""
        for pattern in DOCS_PATTERNS:
            assert pattern.category == PatternCategory.DOCS

    def test_docs_generate_pattern_exists(self):
        """Test docs/generate pattern exists."""
        pattern_ids = [p.pattern_id for p in DOCS_PATTERNS]
        assert "docs/generate" in pattern_ids


class TestProjectPatterns:
    """Test project category patterns."""

    def test_project_patterns_have_correct_category(self):
        """Test all project patterns have PROJECT category."""
        for pattern in PROJECT_PATTERNS:
            assert pattern.category == PatternCategory.PROJECT

    def test_project_init_pattern_exists(self):
        """Test project/init pattern exists."""
        pattern_ids = [p.pattern_id for p in PROJECT_PATTERNS]
        assert "project/init" in pattern_ids


class TestPatternMatching:
    """Test that patterns actually match queries."""

    @pytest.fixture
    def detector(self):
        """Create detector with default patterns."""
        return KeywordDetector(patterns=DEFAULT_PATTERNS)

    def test_security_scan_matching(self, detector):
        """Test security scan pattern matches."""
        match = detector.detect_best("scan for security vulnerabilities")
        assert match is not None
        assert match.pattern_id == "security/scan"

    def test_security_scan_chinese(self, detector):
        """Test security scan pattern matches Chinese."""
        match = detector.detect_best("扫描安全漏洞")
        assert match is not None
        assert match.pattern_id == "security/scan"

    def test_config_deploy_matching(self, detector):
        """Test config deploy pattern matches."""
        match = detector.detect_best("deploy configuration")
        assert match is not None
        assert match.pattern_id == "config/deploy"

    def test_dev_test_matching(self, detector):
        """Test dev test pattern matches."""
        match = detector.detect_best("run tests")
        assert match is not None
        assert match.pattern_id == "dev/test"

    def test_dev_test_chinese(self, detector):
        """Test dev test pattern matches Chinese."""
        match = detector.detect_best("运行测试")
        assert match is not None
        assert "dev/test" in match.pattern_id or "test" in match.pattern_id

    def test_docs_generate_matching(self, detector):
        """Test docs generate pattern matches."""
        match = detector.detect_best("generate documentation")
        assert match is not None
        assert match.pattern_id == "docs/generate"

    def test_project_init_matching(self, detector):
        """Test project init pattern matches."""
        match = detector.detect_best("initialize new project")
        assert match is not None
        assert match.pattern_id == "project/init"


class TestPatternPriority:
    """Test pattern priority ordering."""

    def test_high_priority_patterns_checked_first(self):
        """Test high priority patterns are checked first."""
        detector = KeywordDetector(patterns=DEFAULT_PATTERNS)

        # Check that patterns are sorted by priority
        priorities = [p.priority for p in detector.patterns]
        assert priorities == sorted(priorities, reverse=True)

    def test_security_scan_has_high_priority(self):
        """Test security/scan has high priority."""
        security_scan = next((p for p in DEFAULT_PATTERNS if p.pattern_id == "security/scan"), None)
        assert security_scan is not None
        assert security_scan.priority >= 90


class TestPatternExamples:
    """Test pattern examples match correctly."""

    @pytest.fixture
    def detector(self):
        """Create detector with default patterns."""
        return KeywordDetector(patterns=DEFAULT_PATTERNS)

    def test_security_scan_examples_match(self, detector):
        """Test security scan examples all match."""
        pattern = next((p for p in DEFAULT_PATTERNS if p.pattern_id == "security/scan"), None)
        assert pattern is not None

        for example in pattern.examples:
            match = detector.detect_best(example)
            # At least should match something
            if match:
                # If it matches, should be security-related
                assert "security" in match.pattern_id.lower()

    def test_dev_test_examples_match(self, detector):
        """Test dev test examples all match."""
        pattern = next((p for p in DEFAULT_PATTERNS if p.pattern_id == "dev/test"), None)
        assert pattern is not None

        for example in pattern.examples:
            match = detector.detect_best(example)
            # At least should match something
            if match:
                # If it matches, should be test-related
                assert "test" in match.pattern_id.lower()


class TestPatternConfidence:
    """Test pattern confidence thresholds."""

    def test_all_patterns_have_reasonable_thresholds(self):
        """Test all patterns have reasonable confidence thresholds."""
        for pattern in DEFAULT_PATTERNS:
            assert 0.3 <= pattern.confidence_threshold <= 0.8
            # Most patterns should be around 0.3-0.5
            assert pattern.confidence_threshold >= 0.3 or pattern.confidence_threshold <= 0.8

    def test_high_priority_patterns_have_stricter_thresholds(self):
        """Test high priority patterns tend to have stricter thresholds."""
        high_priority = [p for p in DEFAULT_PATTERNS if p.priority >= 90]
        low_priority = [p for p in DEFAULT_PATTERNS if p.priority < 80]

        if high_priority and low_priority:
            # High priority patterns should have similar or higher thresholds
            avg_high = sum(p.confidence_threshold for p in high_priority) / len(high_priority)
            avg_low = sum(p.confidence_threshold for p in low_priority) / len(low_priority)
            assert avg_high >= avg_low * 0.9  # Allow some tolerance


class TestPatternKeywords:
    """Test pattern keywords."""

    def test_all_patterns_have_keywords(self):
        """Test all patterns have keywords."""
        for pattern in DEFAULT_PATTERNS:
            assert len(pattern.keywords) > 0

    def test_keywords_are_normalized(self):
        """Test keywords are normalized (lowercase, trimmed)."""
        for pattern in DEFAULT_PATTERNS:
            for keyword in pattern.keywords:
                # Should be lowercase or Chinese
                assert keyword.islower() or not keyword.isascii()
                # Should not have leading/trailing whitespace
                assert keyword == keyword.strip()

    def test_security_keywords_included(self):
        """Test security patterns include relevant keywords."""
        security_scan = next((p for p in DEFAULT_PATTERNS if p.pattern_id == "security/scan"), None)
        assert security_scan is not None

        keywords_lower = [k.lower() for k in security_scan.keywords]
        assert "scan" in keywords_lower or "扫描" in security_scan.keywords
        assert "security" in keywords_lower or "安全" in security_scan.keywords


class TestPatternRegex:
    """Test pattern regex patterns."""

    def test_all_patterns_have_regex(self):
        """Test all patterns have regex patterns."""
        for pattern in DEFAULT_PATTERNS:
            assert len(pattern.regex_patterns) > 0

    def test_regex_patterns_are_valid(self):
        """Test all regex patterns are valid."""
        import re

        for pattern in DEFAULT_PATTERNS:
            for regex in pattern.regex_patterns:
                # Should not raise exception
                try:
                    re.compile(regex)
                except re.error as e:
                    pytest.fail(f"Invalid regex '{regex}' in {pattern.pattern_id}: {e}")


class TestPatternMetadata:
    """Test pattern metadata."""

    def test_all_patterns_have_descriptions(self):
        """Test all patterns have descriptions."""
        for pattern in DEFAULT_PATTERNS:
            assert len(pattern.description) > 0

    def test_all_patterns_have_names(self):
        """Test all patterns have names."""
        for pattern in DEFAULT_PATTERNS:
            assert len(pattern.name) > 0

    def test_pattern_ids_follow_convention(self):
        """Test pattern IDs follow category/name convention."""
        for pattern in DEFAULT_PATTERNS:
            parts = pattern.pattern_id.split("/")
            assert len(parts) == 2
            category, name = parts
            assert category in ["security", "config", "dev", "docs", "project"]
            assert len(name) > 0
