"""Tests for SessionAnalyzer - automatic pattern detection.

Tests session analysis, pattern detection, and skill suggestion
generation functionality.
"""

import json
from pathlib import Path

import pytest

from vibesop.core.session_analyzer import (
    QueryPattern,
    SessionAnalyzer,
    SkillSuggestion,
)


class TestSessionAnalyzer:
    """Test SessionAnalyzer class."""

    def test_initialization(self):
        """Test analyzer initialization."""
        analyzer = SessionAnalyzer(
            min_frequency=3,
            min_confidence=0.7,
        )

        assert analyzer.min_frequency == 3
        assert analyzer.min_confidence == 0.7

    def test_initialization_defaults(self):
        """Test default initialization values."""
        analyzer = SessionAnalyzer()

        assert analyzer.min_frequency == 3
        assert analyzer.min_confidence == 0.7


class TestQueryExtraction:
    """Test query extraction from session files."""

    @pytest.fixture
    def temp_session_file(self, tmp_path):
        """Create a temporary session file."""
        session_file = tmp_path / "test_session.jsonl"

        lines = [
            '{"role": "user", "content": "help me debug this error"}',
            '{"role": "assistant", "content": "I can help with that"}',
            '{"role": "user", "content": "please review my code"}',
            '{"role": "assistant", "content": "Sure"}',
        ]

        session_file.write_text("\n".join(lines))
        return session_file

    def test_load_jsonl(self, temp_session_file):
        """Test loading queries from JSONL file."""
        analyzer = SessionAnalyzer()
        queries = analyzer._load_jsonl(temp_session_file)

        assert len(queries) == 2
        assert "help me debug this error" in queries
        assert "please review my code" in queries

    def test_extract_query_from_entry(self):
        """Test extracting query from session entry."""
        analyzer = SessionAnalyzer()

        # Valid user entry
        entry = {"role": "user", "content": "test query here"}
        query = analyzer._extract_query_from_entry(entry)
        assert query == "test query here"

        # Short query (filtered out)
        short_entry = {"role": "user", "content": "hi"}
        query = analyzer._extract_query_from_entry(short_entry)
        assert query is None

        # Non-user entry
        assistant_entry = {"role": "assistant", "content": "I can help"}
        query = analyzer._extract_query_from_entry(assistant_entry)
        assert query is None


class TestPatternDetection:
    """Test pattern detection algorithm."""

    def test_extract_keywords(self):
        """Test keyword extraction from queries."""
        analyzer = SessionAnalyzer()

        # English query
        keywords = analyzer._extract_keywords("help me debug this error")
        assert "debug" in keywords
        assert "error" in keywords

        # Chinese query (should extract characters)
        keywords_cn = analyzer._extract_keywords("帮我调试代码")
        # Chinese extracts full sentence as single tokens
        assert len(keywords_cn) > 0

    def test_calculate_similarity(self):
        """Test string similarity calculation."""
        analyzer = SessionAnalyzer()

        # Identical strings
        sim = analyzer._calculate_similarity("test", "test")
        assert sim == 1.0

        # Completely different
        sim = analyzer._calculate_similarity("abc", "xyz")
        assert sim == 0.0

        # Similar strings
        sim = analyzer._calculate_similarity("test query", "test questions")
        assert sim > 0.5

    def test_cluster_by_similarity(self):
        """Test query clustering by similarity."""
        analyzer = SessionAnalyzer()

        queries = [
            "help me debug this code",
            "help me debug that code",
            "please review my code",
        ]

        clusters = analyzer._cluster_by_similarity(queries, similarity_threshold=0.3)

        # Should cluster similar queries
        assert len(clusters) >= 1
        # At least one cluster should have multiple queries
        assert any(len(c) >= 2 for c in clusters)

    def test_detect_patterns(self):
        """Test pattern detection."""
        analyzer = SessionAnalyzer(min_frequency=2, min_confidence=0.3)

        queries = [
            "help me refactor this code",
            "help me refactor that code",
            "please refactor the code",
            "review my code",
        ]

        patterns = analyzer._detect_patterns(queries)

        # Should detect at least one pattern
        assert len(patterns) >= 1

        # Check pattern structure
        pattern = patterns[0]
        assert hasattr(pattern, "queries")
        assert hasattr(pattern, "frequency")
        assert hasattr(pattern, "suggested_skill")
        assert hasattr(pattern, "confidence")


class TestSkillSuggestion:
    """Test skill suggestion generation."""

    def test_create_pattern(self):
        """Test pattern creation from query cluster."""
        analyzer = SessionAnalyzer()

        queries = [
            "help me refactor code",
            "help me refactor this",
        ]

        pattern = analyzer._create_pattern(queries)

        assert pattern.frequency == 2
        assert len(pattern.queries) == 2
        assert pattern.suggested_skill
        assert 0.0 <= pattern.confidence <= 1.0

    def test_generate_suggestions(self):
        """Test generating suggestions from patterns."""
        analyzer = SessionAnalyzer(min_frequency=2, min_confidence=0.3)

        patterns = [
            QueryPattern(
                queries=["test query 1", "test query 2"],
                frequency=2,
                suggested_skill="test-skill",
                confidence=0.5,
            )
        ]

        suggestions = analyzer._generate_suggestions(patterns)

        assert len(suggestions) == 1

        suggestion = suggestions[0]
        assert suggestion.skill_name == "test-skill"
        assert suggestion.frequency == 2
        assert suggestion.confidence == 0.5
        assert suggestion.estimated_value in ("high", "medium", "low")


class TestSessionAnalysis:
    """Test end-to-end session analysis."""

    @pytest.fixture
    def sample_session_file(self, tmp_path):
        """Create a sample session file with patterns."""
        session_file = tmp_path / "sample.jsonl"

        lines = [
            '{"role": "user", "content": "请帮我优化代码性能"}',
            '{"role": "assistant", "content": "OK"}',
            '{"role": "user", "content": "请帮我优化代码的性能"}',
            '{"role": "assistant", "content": "OK"}',
            '{"role": "user", "content": "请帮我优化一下性能"}',
            '{"role": "assistant", "content": "OK"}',
            '{"role": "user", "content": "check code for security issues"}',
            '{"role": "assistant", "content": "OK"}',
            '{"role": "user", "content": "scan for security vulnerabilities"}',
            '{"role": "assistant", "content": "OK"}',
            '{"role": "user", "content": "check security"}',
            '{"role": "assistant", "content": "OK"}',
        ]

        session_file.write_text("\n".join(lines))
        return session_file

    def test_analyze_session_file(self, sample_session_file):
        """Test analyzing a session file."""
        analyzer = SessionAnalyzer(min_frequency=3, min_confidence=0.3)

        suggestions = analyzer.analyze_session_file(sample_session_file)

        # Should detect patterns
        assert len(suggestions) >= 1

    def test_analyze_session_data(self):
        """Test analyzing session data directly."""
        analyzer = SessionAnalyzer(min_frequency=2, min_confidence=0.3)

        session_data = [
            {"role": "user", "content": "test query 1"},
            {"role": "user", "content": "test query 2"},
            {"role": "user", "content": "test query 1"},
        ]

        suggestions = analyzer.analyze_session_data(session_data)

        # Should detect pattern
        assert len(suggestions) >= 1


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_session(self, tmp_path):
        """Test handling empty session file."""
        session_file = tmp_path / "empty.jsonl"
        session_file.write_text("")

        analyzer = SessionAnalyzer()
        suggestions = analyzer.analyze_session_file(session_file)

        assert len(suggestions) == 0

    def test_invalid_json(self, tmp_path):
        """Test handling invalid JSON."""
        session_file = tmp_path / "invalid.jsonl"
        session_file.write_text("invalid json content")

        analyzer = SessionAnalyzer()
        suggestions = analyzer.analyze_session_file(session_file)

        # Should handle gracefully
        assert isinstance(suggestions, list)

    def test_no_patterns_detected(self, tmp_path):
        """Test when no patterns are detected."""
        session_file = tmp_path / "no_patterns.jsonl"

        lines = [
            '{"role": "user", "content": "unique query 1"}',
            '{"role": "user", "content": "different query 2"}',
            '{"role": "user", "content": "another unique query 3"}',
        ]

        session_file.write_text("\n".join(lines))

        analyzer = SessionAnalyzer(min_frequency=2)
        suggestions = analyzer.analyze_session_file(session_file)

        # Should return empty list
        assert len(suggestions) == 0

    def test_high_thresholds(self, tmp_path):
        """Test with high thresholds that filter out all patterns."""
        session_file = tmp_path / "high_threshold.jsonl"

        lines = [
            '{"role": "user", "content": "test query 1"}',
            '{"role": "user", "content": "test query 2"}',
        ]

        session_file.write_text("\n".join(lines))

        analyzer = SessionAnalyzer(min_frequency=10, min_confidence=0.9)
        suggestions = analyzer.analyze_session_file(session_file)

        # Should filter out all patterns
        assert len(suggestions) == 0


class TestChineseSupport:
    """Test Chinese language support."""

    def test_chinese_queries(self):
        """Test pattern detection with Chinese queries."""
        analyzer = SessionAnalyzer(min_frequency=3, min_confidence=0.3)

        queries = [
            "请帮我优化代码",
            "请帮我优化一下代码",
            "请帮我优化这个代码",
        ]

        patterns = analyzer._detect_patterns(queries)

        # Should detect Chinese patterns
        assert len(patterns) >= 1

    def test_mixed_language_queries(self):
        """Test mixed Chinese-English queries."""
        analyzer = SessionAnalyzer(min_frequency=2, min_confidence=0.3)

        queries = [
            "请帮我review代码",
            "请帮我review一下代码",
            "帮我review这段代码",
        ]

        patterns = analyzer._detect_patterns(queries)

        # Should detect mixed patterns with shared words
        assert len(patterns) >= 1

    def test_chinese_similarity_calculation(self):
        """Test similarity calculation with Chinese characters."""
        analyzer = SessionAnalyzer()

        # Chinese queries
        sim = analyzer._calculate_similarity("请帮我", "请帮")
        assert sim > 0.5  # High similarity for overlapping Chinese

        # Different Chinese
        sim = analyzer._calculate_similarity("优化", "检查")
        # Lower similarity for different words
        assert 0.0 <= sim <= 1.0


class TestConfidenceScoring:
    """Test confidence score calculation."""

    def test_confidence_from_frequency(self):
        """Test confidence based on frequency."""
        analyzer = SessionAnalyzer()

        # High frequency
        pattern = analyzer._create_pattern(
            ["q1"] * 10  # 10 identical queries
        )
        assert pattern.confidence == 1.0

        # Low frequency
        pattern = analyzer._create_pattern(
            ["q1", "q2"]  # 2 different queries
        )
        assert 0.0 <= pattern.confidence < 0.5

    def test_confidence_formula(self):
        """Test confidence calculation formula."""
        analyzer = SessionAnalyzer()

        # Test various frequencies
        for freq in range(1, 21):
            queries = [f"query {i}" for i in range(freq)]
            pattern = analyzer._create_pattern(queries)

            # Confidence should increase with frequency
            expected = min(1.0, freq / 10.0)
            assert abs(pattern.confidence - expected) < 0.01


class TestValueEstimation:
    """Test skill value estimation."""

    def test_high_value_estimation(self):
        """Test high value estimation."""
        patterns = [
            QueryPattern(
                queries=["q"] * 5,
                frequency=5,
                suggested_skill="test",
                confidence=0.8,
            )
        ]

        analyzer = SessionAnalyzer()
        suggestions = analyzer._generate_suggestions(patterns)

        assert suggestions[0].estimated_value == "high"

    def test_medium_value_estimation(self):
        """Test medium value estimation."""
        patterns = [
            QueryPattern(
                queries=["q"] * 3,
                frequency=3,
                suggested_skill="test",
                confidence=0.7,
            )
        ]

        analyzer = SessionAnalyzer()
        suggestions = analyzer._generate_suggestions(patterns)

        assert suggestions[0].estimated_value == "medium"

    def test_low_value_estimation(self):
        """Test low value estimation."""
        patterns = [
            QueryPattern(
                queries=["q"] * 2,
                frequency=2,
                suggested_skill="test",
                confidence=0.3,
            )
        ]

        analyzer = SessionAnalyzer(min_frequency=3)
        suggestions = analyzer._generate_suggestions(patterns)

        assert suggestions[0].estimated_value == "low"
