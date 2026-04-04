"""Integration tests for semantic detection in KeywordDetector.

These tests verify that semantic matching is properly integrated into the
trigger detection system.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import pytest

from vibesop.triggers.detector import KeywordDetector
from vibesop.triggers.models import TriggerPattern, PatternCategory, PatternMatch
from vibesop.semantic.models import EncoderConfig

pytest.importorskip("sentence_transformers", reason="sentence-transformers not installed")


@pytest.fixture
def sample_patterns():
    """Create sample trigger patterns for testing."""
    return [
        TriggerPattern(
            pattern_id="security/scan",
            name="Security Scan",
            description="Detects security scanning requests",
            category=PatternCategory.SECURITY,
            keywords=["scan", "scanning", "check", "security", "vulnerabilities"],
            regex_patterns=[r"scan.*security", r"security.*check"],
            skill_id="/security/scan",
            priority=100,
            confidence_threshold=0.6,
            examples=["scan for vulnerabilities", "check for security issues", "security scan"],
            # Semantic fields
            enable_semantic=True,
            semantic_threshold=0.7,
            semantic_examples=["检查安全性", "扫描漏洞", "analyze security"],
        ),
        TriggerPattern(
            pattern_id="dev/test",
            name="Run Tests",
            description="Detects test execution requests",
            category=PatternCategory.DEV,
            keywords=["test", "testing", "tests", "run", "execute"],
            regex_patterns=[r"run.*tests", r"execute.*test"],
            skill_id="/dev/test",
            priority=90,
            confidence_threshold=0.6,
            examples=["run tests", "execute tests", "testing suite"],
            enable_semantic=True,
            semantic_examples=["执行测试", "运行测试"],
        ),
        TriggerPattern(
            pattern_id="config/deploy",
            name="Deploy Configuration",
            description="Detects deployment requests",
            category=PatternCategory.CONFIG,
            keywords=["deploy", "deployment", "apply", "config"],
            regex_patterns=[r"deploy.*config"],
            skill_id="/config/deploy",
            priority=80,
            confidence_threshold=0.6,
            examples=["deploy configuration", "apply config"],
            enable_semantic=False,  # No semantic for this one
        ),
    ]


class TestDetectorWithSemanticEnabled:
    """Tests for KeywordDetector with semantic matching enabled."""

    def test_initialization_with_semantic(self, sample_patterns):
        """Test initializing detector with semantic enabled."""
        with patch('vibesop.triggers.detector.VectorCache'):
            with patch('vibesop.triggers.detector.SemanticEncoder') as MockEncoder:
                with patch('vibesop.triggers.detector.SimilarityCalculator'):
                    # Setup mock
                    mock_encoder_instance = Mock()
                    mock_encoder_instance.model_name = "test-model"
                    MockEncoder.return_value = mock_encoder_instance

                    detector = KeywordDetector(
                        patterns=sample_patterns,
                        enable_semantic=True,
                    )

                    assert detector.enable_semantic is True
                    assert detector.semantic_encoder is not None

    def test_detect_best_with_semantic(self, sample_patterns):
        """Test detect_best with semantic matching."""
        with patch('vibesop.triggers.detector.VectorCache') as MockCache:
            with patch('vibesop.triggers.detector.SemanticEncoder') as MockEncoder:
                with patch('vibesop.triggers.detector.SimilarityCalculator') as MockCalc:
                    # Setup mocks
                    mock_encoder = Mock()
                    mock_encoder.model_name = "test-model"
                    mock_encoder.encode_query.return_value = np.random.rand(384)
                    MockEncoder.return_value = mock_encoder

                    mock_cache = Mock()
                    mock_cache.get_or_compute.return_value = np.random.rand(384)
                    MockCache.return_value = mock_cache

                    mock_calc = Mock()
                    mock_calc.calculate.return_value = np.array([0.85])
                    MockCalc.return_value = mock_calc

                    detector = KeywordDetector(
                        patterns=sample_patterns,
                        enable_semantic=True,
                    )

                    match = detector.detect_best("scan for vulnerabilities")

                    assert match is not None
                    assert match.pattern_id == "security/scan"
                    assert match.semantic_score is not None

    def test_semantic_refine_high_confidence(self, sample_patterns):
        """Test semantic refine with high traditional confidence."""
        with patch('vibesop.triggers.detector.VectorCache'):
            with patch('vibesop.triggers.detector.SemanticEncoder'):
                with patch('vibesop.triggers.detector.SimilarityCalculator'):
                    detector = KeywordDetector(
                        patterns=sample_patterns,
                        enable_semantic=True,
                    )

                    # Create mock matches
                    from vibesop.triggers.models import PatternMatch
                    candidates = [
                        PatternMatch(
                            pattern_id="security/scan",
                            confidence=0.95,  # High confidence
                            semantic_score=0.5,
                        )
                    ]

                    match = detector._semantic_refine("test query", candidates, 0.6)

                    # Should keep high traditional confidence
                    assert match is not None
                    assert match.confidence >= 0.9

    def test_semantic_refine_low_traditional_high_semantic(self, sample_patterns):
        """Test semantic refine with low traditional but high semantic."""
        with patch('vibesop.triggers.detector.VectorCache'):
            with patch('vibesop.triggers.detector.SemanticEncoder') as MockEncoder:
                with patch('vibesop.triggers.detector.SimilarityCalculator') as MockCalc:
                    # Setup mocks
                    mock_encoder = Mock()
                    mock_encoder.model_name = "test-model"
                    mock_encoder.encode_query.return_value = np.random.rand(384)
                    MockEncoder.return_value = mock_encoder

                    mock_calc = Mock()
                    mock_calc.calculate.return_value = np.array([0.9])  # High semantic
                    MockCalc.return_value = mock_calc

                    detector = KeywordDetector(
                        patterns=sample_patterns,
                        enable_semantic=True,
                    )

                    # Create mock matches
                    from vibesop.triggers.models import PatternMatch
                    candidates = [
                        PatternMatch(
                            pattern_id="security/scan",
                            confidence=0.4,  # Low traditional
                            semantic_score=0.4,
                        )
                    ]

                    match = detector._semantic_refine("test query", candidates, 0.6)

                    # Should use high semantic score
                    assert match is not None
                    assert match.semantic_score == 0.9

    def test_detect_all_with_semantic(self, sample_patterns):
        """Test detect_all with semantic matching."""
        with patch('vibesop.triggers.detector.VectorCache'):
            with patch('vibesop.triggers.detector.SemanticEncoder'):
                with patch('vibesop.triggers.detector.SimilarityCalculator'):
                    detector = KeywordDetector(
                        patterns=sample_patterns,
                        enable_semantic=True,
                    )

                    matches = detector.detect_all("scan for vulnerabilities")

                    # Should return matches
                    assert isinstance(matches, list)

    def test_synonym_detection(self, sample_patterns):
        """Test synonym detection using semantic matching."""
        with patch('vibesop.triggers.detector.VectorCache') as MockCache:
            with patch('vibesop.triggers.detector.SemanticEncoder') as MockEncoder:
                with patch('vibesop.triggers.detector.SimilarityCalculator') as MockCalc:
                    # Setup mocks
                    mock_encoder = Mock()
                    mock_encoder.model_name = "test-model"
                    mock_encoder.encode_query.return_value = np.random.rand(384)
                    MockEncoder.return_value = mock_encoder

                    mock_cache = Mock()
                    mock_cache.get_or_compute.return_value = np.random.rand(384)
                    MockCache.return_value = mock_cache

                    mock_calc = Mock()
                    mock_calc.calculate.return_value = np.array([0.8])  # High similarity
                    MockCalc.return_value = mock_calc

                    detector = KeywordDetector(
                        patterns=sample_patterns,
                        enable_semantic=True,
                    )

                    # Test with synonym (not in keywords)
                    match = detector.detect_best("check for vulnerabilities")

                    # Should still match due to semantic similarity
                    assert match is not None

    def test_multilingual_matching(self, sample_patterns):
        """Test multilingual query matching."""
        with patch('vibesop.triggers.detector.VectorCache') as MockCache:
            with patch('vibesop.triggers.detector.SemanticEncoder') as MockEncoder:
                with patch('vibesop.triggers.detector.SimilarityCalculator') as MockCalc:
                    # Setup mocks
                    mock_encoder = Mock()
                    mock_encoder.model_name = "test-model"
                    mock_encoder.encode_query.return_value = np.random.rand(384)
                    MockEncoder.return_value = mock_encoder

                    mock_cache = Mock()
                    mock_cache.get_or_compute.return_value = np.random.rand(384)
                    MockCache.return_value = mock_cache

                    mock_calc = Mock()
                    mock_calc.calculate.return_value = np.array([0.85])
                    MockCalc.return_value = mock_calc

                    detector = KeywordDetector(
                        patterns=sample_patterns,
                        enable_semantic=True,
                    )

                    # Test with Chinese query
                    match = detector.detect_best("扫描安全漏洞")

                    # Should match due to semantic examples
                    assert match is not None


class TestDetectorWithSemanticDisabled:
    """Tests for KeywordDetector with semantic matching disabled (backward compatibility)."""

    def test_initialization_without_semantic(self, sample_patterns):
        """Test initializing detector without semantic (default)."""
        detector = KeywordDetector(
            patterns=sample_patterns,
            enable_semantic=False,
        )

        assert detector.enable_semantic is False
        assert detector.semantic_encoder is None
        assert detector.semantic_cache is None
        assert detector.semantic_calculator is None

    def test_detect_best_without_semantic(self, sample_patterns):
        """Test detect_best without semantic matching (traditional only)."""
        detector = KeywordDetector(
            patterns=sample_patterns,
            enable_semantic=False,
        )

        match = detector.detect_best("scan for vulnerabilities")

        assert match is not None
        assert match.pattern_id == "security/scan"
        # Should have semantic_score from TF-IDF
        assert match.semantic_score is not None
        # But not from embeddings
        assert match.semantic_method == "tfidf"

    def test_detect_all_without_semantic(self, sample_patterns):
        """Test detect_all without semantic matching."""
        detector = KeywordDetector(
            patterns=sample_patterns,
            enable_semantic=False,
        )

        matches = detector.detect_all("scan for vulnerabilities")

        assert isinstance(matches, list)
        # All matches should use TF-IDF semantic
        for match in matches:
            assert match.semantic_method == "tfidf"

    def test_backward_compatibility(self, sample_patterns):
        """Test that behavior is consistent when semantic is disabled."""
        detector_old = KeywordDetector(
            patterns=sample_patterns,
            enable_semantic=False,
        )

        detector_new = KeywordDetector(
            patterns=sample_patterns,
            enable_semantic=False,
        )

        # Both should produce same results
        match_old = detector_old.detect_best("scan for vulnerabilities")
        match_new = detector_new.detect_best("scan for vulnerabilities")

        assert match_old is not None
        assert match_new is not None
        assert match_old.pattern_id == match_new.pattern_id


class TestDetectorGracefulDegradation:
    """Tests for graceful degradation when sentence-transformers is not available."""

    def test_init_without_sentence_transformers(self, sample_patterns):
        """Test initialization when sentence-transformers is not available."""
        with patch('vibesop.triggers.detector.SENTENCE_TRANSFORMERS_AVAILABLE', False):
            detector = KeywordDetector(
                patterns=sample_patterns,
                enable_semantic=True,
            )

            # Should disable semantic gracefully
            assert detector.enable_semantic is False
            assert detector.semantic_encoder is None

    def test_detect_best_when_unavailable(self, sample_patterns):
        """Test detect_best when semantic is unavailable."""
        with patch('vibesop.triggers.detector.SENTENCE_TRANSFORMERS_AVAILABLE', False):
            detector = KeywordDetector(
                patterns=sample_patterns,
                enable_semantic=True,
            )

            match = detector.detect_best("scan for vulnerabilities")

            # Should still work with traditional methods
            assert match is not None
            assert match.semantic_method == "tfidf"


class TestDetectorSemanticScoring:
    """Tests for semantic score calculation and fusion."""

    def test_score_fusion_high_traditional(self, sample_patterns):
        """Test score fusion keeps high traditional scores."""
        with patch('vibesop.triggers.detector.VectorCache'):
            with patch('vibesop.triggers.detector.SemanticEncoder'):
                with patch('vibesop.triggers.detector.SimilarityCalculator'):
                    detector = KeywordDetector(
                        patterns=sample_patterns,
                        enable_semantic=True,
                    )

                    from vibesop.triggers.models import PatternMatch
                    candidates = [
                        PatternMatch(
                            pattern_id="security/scan",
                            confidence=0.9,
                            semantic_score=0.5,
                        )
                    ]

                    match = detector._semantic_refine("test", candidates, 0.6)

                    # Should keep high traditional score
                    assert match.confidence == 0.9

    def test_score_fusion_high_semantic(self, sample_patterns):
        """Test score fusion uses high semantic scores."""
        with patch('vibesop.triggers.detector.VectorCache'):
            with patch('vibesop.triggers.detector.SemanticEncoder') as MockEncoder:
                with patch('vibesop.triggers.detector.SimilarityCalculator') as MockCalc:
                    mock_encoder = Mock()
                    mock_encoder.model_name = "test-model"
                    mock_encoder.encode_query.return_value = np.random.rand(384)
                    MockEncoder.return_value = mock_encoder

                    mock_calc = Mock()
                    mock_calc.calculate.return_value = np.array([0.9])
                    MockCalc.return_value = mock_calc

                    detector = KeywordDetector(
                        patterns=sample_patterns,
                        enable_semantic=True,
                    )

                    from vibesop.triggers.models import PatternMatch
                    candidates = [
                        PatternMatch(
                            pattern_id="security/scan",
                            confidence=0.5,
                            semantic_score=0.5,
                        )
                    ]

                    match = detector._semantic_refine("test", candidates, 0.6)

                    # Should use high semantic score
                    assert match.semantic_score == 0.9

    def test_score_fusion_weighted_average(self, sample_patterns):
        """Test score fusion uses weighted average for medium scores."""
        with patch('vibesop.triggers.detector.VectorCache'):
            with patch('vibesop.triggers.detector.SemanticEncoder') as MockEncoder:
                with patch('vibesop.triggers.detector.SimilarityCalculator') as MockCalc:
                    mock_encoder = Mock()
                    mock_encoder.model_name = "test-model"
                    mock_encoder.encode_query.return_value = np.random.rand(384)
                    MockEncoder.return_value = mock_encoder

                    mock_calc = Mock()
                    mock_calc.calculate.return_value = np.array([0.7])  # Medium
                    MockCalc.return_value = mock_calc

                    detector = KeywordDetector(
                        patterns=sample_patterns,
                        enable_semantic=True,
                    )

                    from vibesop.triggers.models import PatternMatch
                    candidates = [
                        PatternMatch(
                            pattern_id="security/scan",
                            confidence=0.6,
                            semantic_score=0.6,
                        )
                    ]

                    match = detector._semantic_refine("test", candidates, 0.6)

                    # Should use weighted average: 0.6 * 0.4 + 0.7 * 0.6 = 0.66
                    expected = 0.6 * 0.4 + 0.7 * 0.6
                    assert abs(match.confidence - expected) < 0.01


class TestDetectorSemanticMetadata:
    """Tests for semantic metadata in matches."""

    def test_match_includes_semantic_info(self, sample_patterns):
        """Test that matches include semantic information."""
        with patch('vibesop.triggers.detector.VectorCache'):
            with patch('vibesop.triggers.detector.SemanticEncoder') as MockEncoder:
                with patch('vibesop.triggers.detector.SimilarityCalculator') as MockCalc:
                    mock_encoder = Mock()
                    mock_encoder.model_name = "test-model"
                    mock_encoder.encode_query.return_value = np.random.rand(384)
                    MockEncoder.return_value = mock_encoder

                    mock_calc = Mock()
                    mock_calc.calculate.return_value = np.array([0.8])
                    MockCalc.return_value = mock_calc

                    detector = KeywordDetector(
                        patterns=sample_patterns,
                        enable_semantic=True,
                    )

                    match = detector.detect_best("test query")

                    if match and match.semantic_score:
                        assert match.semantic_method == "cosine"
                        assert match.model_used == "test-model"
                        assert match.encoding_time is not None
                        assert match.encoding_time >= 0

    def test_match_without_semantic_uses_tfidf(self, sample_patterns):
        """Test that matches without semantic use TF-IDF method."""
        detector = KeywordDetector(
            patterns=sample_patterns,
            enable_semantic=False,
        )

        match = detector.detect_best("scan for vulnerabilities")

        assert match is not None
        assert match.semantic_method == "tfidf"
        assert match.model_used is None
        assert match.encoding_time is None


class TestDetectorFastFilter:
    """Tests for fast filter stage (Stage 1)."""

    def test_fast_filter_returns_candidates(self, sample_patterns):
        """Test that fast filter returns candidate matches."""
        detector = KeywordDetector(
            patterns=sample_patterns,
            enable_semantic=False,
        )

        candidates = detector._fast_filter("scan for vulnerabilities")

        assert isinstance(candidates, list)
        assert len(candidates) > 0
        # Should be sorted by confidence
        confidences = [m.confidence for m in candidates]
        assert confidences == sorted(confidences, reverse=True)

    def test_fast_filter_empty_query(self, sample_patterns):
        """Test fast filter with empty query."""
        detector = KeywordDetector(
            patterns=sample_patterns,
            enable_semantic=False,
        )

        candidates = detector._fast_filter("")

        assert candidates == []


class TestDetectorPatternLookup:
    """Tests for pattern lookup utility."""

    def test_get_pattern_by_id_found(self, sample_patterns):
        """Test getting pattern by ID when found."""
        detector = KeywordDetector(
            patterns=sample_patterns,
            enable_semantic=False,
        )

        pattern = detector._get_pattern_by_id("security/scan")

        assert pattern is not None
        assert pattern.pattern_id == "security/scan"

    def test_get_pattern_by_id_not_found(self, sample_patterns):
        """Test getting pattern by ID when not found."""
        detector = KeywordDetector(
            patterns=sample_patterns,
            enable_semantic=False,
        )

        pattern = detector._get_pattern_by_id("nonexistent/pattern")

        assert pattern is None
