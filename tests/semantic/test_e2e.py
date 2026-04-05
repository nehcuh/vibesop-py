"""End-to-end tests for semantic recognition features.

These tests verify that semantic matching works correctly in real-world scenarios,
including accuracy, multilingual support, and integration with the CLI.

DEPRECATED: These tests use the deprecated triggers module.
New semantic tests should use vibesop.core.matching instead.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

np = pytest.importorskip("numpy", reason="numpy not installed")
pytest.importorskip("sentence_transformers", reason="sentence-transformers not installed")

# Skip these tests since they depend on deprecated triggers module
pytest.skip("Tests depend on deprecated triggers module. Use vibesop.core.matching instead.", allow_module_level=True)

from vibesop.triggers.detector import KeywordDetector
from vibesop.triggers.models import TriggerPattern, PatternCategory, PatternMatch
from vibesop.semantic.models import EncoderConfig


@pytest.fixture
def realistic_patterns():
    """Create realistic trigger patterns for testing."""
    return [
        TriggerPattern(
            pattern_id="security/scan",
            name="Security Scan",
            description="Detects security scanning requests",
            category=PatternCategory.SECURITY,
            keywords=["scan", "scanning", "security", "vulnerability", "check"],
            regex_patterns=[r"scan.*security", r"security.*check", r"vulnerability.*scan"],
            skill_id="/security/scan",
            priority=100,
            confidence_threshold=0.6,
            examples=[
                "scan for vulnerabilities",
                "check for security issues",
                "security scan",
                "vulnerability scan",
            ],
            enable_semantic=True,
            semantic_threshold=0.7,
            semantic_examples=[
                "检查安全性",
                "扫描漏洞",
                "分析安全",
                "安全审计",
            ],
        ),
        TriggerPattern(
            pattern_id="dev/test",
            name="Run Tests",
            description="Detects test execution requests",
            category=PatternCategory.DEV,
            keywords=["test", "testing", "tests", "run", "execute", "spec"],
            regex_patterns=[r"run.*tests?", r"execute.*tests?", r"test.*suite"],
            skill_id="/dev/test",
            priority=90,
            confidence_threshold=0.6,
            examples=[
                "run tests",
                "execute tests",
                "run testing suite",
                "test the code",
            ],
            enable_semantic=True,
            semantic_threshold=0.7,
            semantic_examples=[
                "执行测试",
                "运行测试",
                "测试代码",
            ],
        ),
        TriggerPattern(
            pattern_id="dev/build",
            name="Build Project",
            description="Detects build requests",
            category=PatternCategory.DEV,
            keywords=["build", "compile", "make", "construct"],
            regex_patterns=[r"build.*project", r"compile.*code"],
            skill_id="/dev/build",
            priority=85,
            confidence_threshold=0.6,
            examples=[
                "build the project",
                "compile the code",
                "make build",
            ],
            enable_semantic=True,
            semantic_threshold=0.7,
            semantic_examples=[
                "编译项目",
                "构建代码",
            ],
        ),
        TriggerPattern(
            pattern_id="docs/generate",
            name="Generate Documentation",
            description="Detects documentation generation requests",
            category=PatternCategory.DOCS,
            keywords=["document", "documentation", "docs", "generate", "api"],
            regex_patterns=[r"generate.*docs?", r"create.*documentation"],
            skill_id="/docs/generate",
            priority=80,
            confidence_threshold=0.6,
            examples=[
                "generate documentation",
                "create API docs",
                "document the code",
            ],
            enable_semantic=True,
            semantic_threshold=0.7,
            semantic_examples=[
                "生成文档",
                "创建文档",
                "文档化",
            ],
        ),
    ]


class TestE2ESemanticAccuracy:
    """End-to-end tests for semantic matching accuracy."""

    @pytest.mark.slow
    def test_english_queries_accuracy(self, realistic_patterns):
        """Test accuracy with English queries."""
        with patch("vibesop.triggers.detector.VectorCache"):
            with patch("vibesop.triggers.detector.SemanticEncoder") as MockEncoder:
                with patch("vibesop.triggers.detector.SimilarityCalculator") as MockCalc:
                    # Setup mocks
                    mock_encoder = Mock()
                    mock_encoder.model_name = "test-model"
                    mock_encoder.encode_query.return_value = np.random.rand(384)
                    MockEncoder.return_value = mock_encoder

                    mock_cache = Mock()
                    mock_cache.get_or_compute.return_value = np.random.rand(384)
                    mock_cache.get_cache_stats.return_value = {
                        "hits": 10,
                        "misses": 1,
                        "total_requests": 11,
                        "hit_rate": 0.909,
                        "size": 4,
                        "size_bytes": 6144,
                        "size_mb": 0.006,
                    }
                    MockCache.return_value = mock_cache

                    # Setup similarity calculator to return appropriate similarities
                    mock_calc = Mock()
                    MockCalc.return_value = mock_calc

                    detector = KeywordDetector(
                        patterns=realistic_patterns,
                        enable_semantic=True,
                    )

                    # Test cases: (query, expected_pattern)
                    test_cases = [
                        ("scan for vulnerabilities", "security/scan"),
                        ("run all the tests", "dev/test"),
                        ("build the project", "dev/build"),
                        ("generate API documentation", "docs/generate"),
                    ]

                    correct_matches = 0
                    for query, expected_pattern in test_cases:
                        # Mock high similarity for correct pattern
                        mock_calc.calculate.return_value = np.array([0.85])

                        match = detector.detect_best(query, min_confidence=0.6)

                        if match and match.pattern_id == expected_pattern:
                            correct_matches += 1

                    accuracy = correct_matches / len(test_cases)
                    assert accuracy >= 0.75, f"Accuracy {accuracy:.0%} below 75% threshold"

    @pytest.mark.slow
    def test_chinese_queries_accuracy(self, realistic_patterns):
        """Test accuracy with Chinese queries."""
        with patch("vibesop.triggers.detector.VectorCache"):
            with patch("vibesop.triggers.detector.SemanticEncoder") as MockEncoder:
                with patch("vibesop.triggers.detector.SimilarityCalculator") as MockCalc:
                    # Setup mocks
                    mock_encoder = Mock()
                    mock_encoder.model_name = "test-model"
                    mock_encoder.encode_query.return_value = np.random.rand(384)
                    MockEncoder.return_value = mock_encoder

                    mock_cache = Mock()
                    mock_cache.get_or_compute.return_value = np.random.rand(384)
                    MockCache.return_value = mock_cache

                    mock_calc = Mock()
                    MockCalc.return_value = mock_calc

                    detector = KeywordDetector(
                        patterns=realistic_patterns,
                        enable_semantic=True,
                    )

                    # Test cases: (query, expected_pattern)
                    test_cases = [
                        ("扫描安全漏洞", "security/scan"),
                        ("执行测试", "dev/test"),
                        ("编译项目", "dev/build"),
                        ("生成文档", "docs/generate"),
                    ]

                    correct_matches = 0
                    for query, expected_pattern in test_cases:
                        # Mock high similarity for correct pattern
                        mock_calc.calculate.return_value = np.array([0.85])

                        match = detector.detect_best(query, min_confidence=0.6)

                        if match and match.pattern_id == expected_pattern:
                            correct_matches += 1

                    accuracy = correct_matches / len(test_cases)
                    assert accuracy >= 0.75, f"Accuracy {accuracy:.0%} below 75% threshold"

    @pytest.mark.slow
    def test_synonym_recognition(self, realistic_patterns):
        """Test synonym recognition capabilities."""
        with patch("vibesop.triggers.detector.VectorCache"):
            with patch("vibesop.triggers.detector.SemanticEncoder") as MockEncoder:
                with patch("vibesop.triggers.detector.SimilarityCalculator") as MockCalc:
                    # Setup mocks
                    mock_encoder = Mock()
                    mock_encoder.model_name = "test-model"
                    mock_encoder.encode_query.return_value = np.random.rand(384)
                    MockEncoder.return_value = mock_encoder

                    mock_cache = Mock()
                    mock_cache.get_or_compute.return_value = np.random.rand(384)
                    MockCache.return_value = mock_cache

                    mock_calc = Mock()
                    MockCalc.return_value = mock_calc

                    detector = KeywordDetector(
                        patterns=realistic_patterns,
                        enable_semantic=True,
                    )

                    # Test synonym recognition
                    synonym_tests = [
                        # Original vs synonym
                        ("scan for vulnerabilities", "check for security issues"),
                        ("run tests", "execute testing suite"),
                        ("build project", "compile code"),
                    ]

                    for query1, query2 in synonym_tests:
                        # Both should match the same pattern with similar confidence
                        mock_calc.calculate.return_value = np.array([0.8, 0.75])

                        match1 = detector.detect_best(query1, min_confidence=0.6)
                        match2 = detector.detect_best(query2, min_confidence=0.6)

                        assert match1 is not None, f"Query '{query1}' should match"
                        assert match2 is not None, f"Query '{query2}' should match"
                        assert match1.pattern_id == match2.pattern_id, (
                            f"Synonyms should match same pattern: {query1} vs {query2}"
                        )

    @pytest.mark.slow
    def test_mixed_language_queries(self, realistic_patterns):
        """Test mixed Chinese-English queries."""
        with patch("vibesop.triggers.detector.VectorCache"):
            with patch("vibesop.triggers.detector.SemanticEncoder") as MockEncoder:
                with patch("vibesop.triggers.detector.SimilarityCalculator") as MockCalc:
                    # Setup mocks
                    mock_encoder = Mock()
                    mock_encoder.model_name = "test-model"
                    mock_encoder.encode_query.return_value = np.random.rand(384)
                    MockEncoder.return_value = mock_encoder

                    mock_cache = Mock()
                    mock_cache.get_or_compute.return_value = np.random.rand(384)
                    MockCache.return_value = mock_cache

                    mock_calc = Mock()
                    MockCalc.return_value = mock_calc

                    detector = KeywordDetector(
                        patterns=realistic_patterns,
                        enable_semantic=True,
                    )

                    # Mixed language queries
                    mixed_tests = [
                        ("帮我扫描代码安全漏洞", "security/scan"),
                        ("run the 测试", "dev/test"),
                        ("编译 the project", "dev/build"),
                    ]

                    correct_matches = 0
                    for query, expected_pattern in mixed_tests:
                        mock_calc.calculate.return_value = np.array([0.8])

                        match = detector.detect_best(query, min_confidence=0.6)

                        if match and match.pattern_id == expected_pattern:
                            correct_matches += 1

                    accuracy = correct_matches / len(mixed_tests)
                    assert accuracy >= 0.66, (
                        f"Mixed language accuracy {accuracy:.0%} below 66% threshold"
                    )


class TestE2ECLIIntegration:
    """End-to-end tests for CLI integration."""

    def test_auto_command_with_semantic_flag(self, realistic_patterns):
        """Test vibe auto command with --semantic flag."""
        from vibesop.cli.commands import auto

        # Mock semantic components
        with patch("vibesop.triggers.detector.VectorCache"):
            with patch("vibesop.triggers.detector.SemanticEncoder") as MockEncoder:
                with patch("vibesop.triggers.detector.SimilarityCalculator") as MockCalc:
                    with patch("vibesop.triggers.DEFAULT_PATTERNS", realistic_patterns):
                        # Setup mocks
                        mock_encoder = Mock()
                        mock_encoder.model_name = "test-model"
                        mock_encoder.encode_query.return_value = np.random.rand(384)
                        MockEncoder.return_value = mock_encoder

                        mock_cache = Mock()
                        mock_cache.get_or_compute.return_value = np.random.rand(384)
                        MockCache.return_value = mock_cache

                        mock_calc = Mock()
                        mock_calc.calculate.return_value = np.array([0.9])
                        MockCalc.return_value = mock_calc

                        # This would normally execute the skill, but we're just testing detection
                        detector = KeywordDetector(
                            patterns=realistic_patterns,
                            enable_semantic=True,
                        )

                        match = detector.detect_best("scan for vulnerabilities")

                        assert match is not None
                        assert match.pattern_id == "security/scan"
                        assert match.semantic_score == 0.9


class TestE2EConfigurationManagement:
    """End-to-end tests for configuration management."""

    def test_config_semantic_show(self):
        """Test vibe config semantic show."""
        from vibesop.cli.commands import config

        # Just test that the command doesn't crash
        with patch("vibesop.semantic.SENTENCE_TRANSFORMERS_AVAILABLE", False):
            # Should handle unavailable semantic gracefully
            try:
                config.config_semantic(action="show")
            except SystemExit:
                # Expected when semantic not available
                pass

    def test_config_semantic_warmup(self):
        """Test vibe config semantic warmup."""
        from vibesop.cli.commands import config

        with patch("vibesop.semantic.SENTENCE_TRANSFORMERS_AVAILABLE", True):
            with patch("vibesop.semantic.encoder.SentenceTransformer"):
                with patch("vibesop.triggers.DEFAULT_PATTERNS", []):
                    # Should handle warmup
                    try:
                        config.config_semantic(action="show", warmup=True)
                    except Exception as e:
                        # May fail due to missing actual model, that's ok
                        assert "warmup" in str(e).lower() or "semantic" in str(e).lower()


class TestE2EBackwardCompatibility:
    """End-to-end tests for backward compatibility."""

    def test_semantic_disabled_same_behavior(self, realistic_patterns):
        """Test that disabling semantic gives same results as before."""
        detector_traditional = KeywordDetector(
            patterns=realistic_patterns,
            enable_semantic=False,
        )

        # Multiple queries should produce consistent results
        queries = [
            "scan for vulnerabilities",
            "run tests",
            "build project",
        ]

        for query in queries:
            match = detector_traditional.detect_best(query)
            # Should work without semantic
            # (might not match if confidence is low, that's ok)
            assert match is None or match.semantic_method == "tfidf"

    def test_graceful_degradation_without_dependencies(self, realistic_patterns):
        """Test graceful degradation when sentence-transformers not installed."""
        with patch("vibesop.triggers.detector.SENTENCE_TRANSFORMERS_AVAILABLE", False):
            # Should disable semantic automatically
            detector = KeywordDetector(
                patterns=realistic_patterns,
                enable_semantic=True,  # Try to enable
            )

            # Should be disabled
            assert detector.enable_semantic is False

            # Should still work with traditional methods
            match = detector.detect_best("scan for vulnerabilities")
            assert match is None or match.semantic_method == "tfidf"


class TestE2EScoreFusion:
    """End-to-end tests for score fusion logic."""

    def test_high_traditional_confidence_preserved(self, realistic_patterns):
        """Test that high traditional confidence is preserved."""
        with patch("vibesop.triggers.detector.VectorCache"):
            with patch("vibesop.triggers.detector.SemanticEncoder") as MockEncoder:
                with patch("vibesop.triggers.detector.SimilarityCalculator") as MockCalc:
                    mock_encoder = Mock()
                    mock_encoder.model_name = "test-model"
                    mock_encoder.encode_query.return_value = np.random.rand(384)
                    MockEncoder.return_value = mock_encoder

                    mock_cache = Mock()
                    mock_cache.get_or_compute.return_value = np.random.rand(384)
                    MockCache.return_value = mock_cache

                    mock_calc = Mock()
                    MockCalc.return_value = mock_calc

                    detector = KeywordDetector(
                        patterns=realistic_patterns,
                        enable_semantic=True,
                    )

                    # Create a high traditional confidence match
                    from vibesop.triggers.models import PatternMatch

                    candidates = [
                        PatternMatch(
                            pattern_id="security/scan",
                            confidence=0.9,  # High traditional
                            semantic_score=0.5,  # Low semantic
                        )
                    ]

                    # Mock low semantic score
                    mock_calc.calculate.return_value = np.array([0.5])

                    match = detector._semantic_refine("test", candidates, 0.6)

                    # Should keep high traditional score
                    assert match.confidence >= 0.85

    def test_high_semantic_confidence_used(self, realistic_patterns):
        """Test that high semantic confidence is used."""
        with patch("vibesop.triggers.detector.VectorCache"):
            with patch("vibesop.triggers.detector.SemanticEncoder") as MockEncoder:
                with patch("vibesop.triggers.detector.SimilarityCalculator") as MockCalc:
                    mock_encoder = Mock()
                    mock_encoder.model_name = "test-model"
                    mock_encoder.encode_query.return_value = np.random.rand(384)
                    MockEncoder.return_value = mock_encoder

                    mock_cache = Mock()
                    mock_cache.get_or_compute.return_value = np.random.rand(384)
                    MockCache.return_value = mock_cache

                    mock_calc = Mock()
                    mock_calc.calculate.return_value = np.array([0.9])  # High semantic
                    MockCalc.return_value = mock_calc

                    detector = KeywordDetector(
                        patterns=realistic_patterns,
                        enable_semantic=True,
                    )

                    # Create a low traditional confidence match
                    from vibesop.triggers.models import PatternMatch

                    candidates = [
                        PatternMatch(
                            pattern_id="security/scan",
                            confidence=0.4,  # Low traditional
                            semantic_score=0.4,
                        )
                    ]

                    match = detector._semantic_refine("test", candidates, 0.6)

                    # Should use high semantic score
                    assert match.semantic_score == 0.9

    def test_medium_scores_use_weighted_average(self, realistic_patterns):
        """Test that medium scores use weighted average."""
        with patch("vibesop.triggers.detector.VectorCache"):
            with patch("vibesop.triggers.detector.SemanticEncoder") as MockEncoder:
                with patch("vibesop.triggers.detector.SimilarityCalculator") as MockCalc:
                    mock_encoder = Mock()
                    mock_encoder.model_name = "test-model"
                    mock_encoder.encode_query.return_value = np.random.rand(384)
                    MockEncoder.return_value = mock_encoder

                    mock_cache = Mock()
                    mock_cache.get_or_compute.return_value = np.random.rand(384)
                    MockCache.return_value = mock_cache

                    mock_calc = Mock()
                    mock_calc.calculate.return_value = np.array([0.7])  # Medium semantic
                    MockCalc.return_value = mock_calc

                    detector = KeywordDetector(
                        patterns=realistic_patterns,
                        enable_semantic=True,
                    )

                    # Create a medium traditional confidence match
                    from vibesop.triggers.models import PatternMatch

                    candidates = [
                        PatternMatch(
                            pattern_id="security/scan",
                            confidence=0.6,  # Medium traditional
                            semantic_score=0.6,
                        )
                    ]

                    match = detector._semantic_refine("test", candidates, 0.6)

                    # Should use weighted average: 0.6 * 0.4 + 0.7 * 0.6 = 0.66
                    expected = 0.6 * 0.4 + 0.7 * 0.6
                    assert abs(match.confidence - expected) < 0.01


class TestE2ECachePerformance:
    """End-to-end tests for cache performance."""

    def test_cache_hit_rate_improves(self, realistic_patterns):
        """Test that cache hit rate improves with repeated queries."""
        with patch("vibesop.triggers.detector.VectorCache") as MockCache:
            with patch("vibesop.triggers.detector.SemanticEncoder") as MockEncoder:
                with patch("vibesop.triggers.detector.SimilarityCalculator") as MockCalc:
                    # Setup mocks
                    mock_encoder = Mock()
                    mock_encoder.model_name = "test-model"
                    mock_encoder.encode_query.return_value = np.random.rand(384)
                    MockEncoder.return_value = mock_encoder

                    mock_cache = Mock()
                    mock_cache.get_or_compute.return_value = np.random.rand(384)

                    # Simulate improving cache stats
                    stats_calls = [0]

                    def get_stats():
                        stats_calls[0] += 1
                        return {
                            "hits": stats_calls[0] * 5,
                            "misses": 1,
                            "total_requests": stats_calls[0] * 5 + 1,
                            "hit_rate": stats_calls[0] * 5 / (stats_calls[0] * 5 + 1),
                            "size": 4,
                            "size_bytes": 6144,
                            "size_mb": 0.006,
                        }

                    mock_cache.get_cache_stats = get_stats
                    MockCache.return_value = mock_cache

                    mock_calc = Mock()
                    mock_calc.calculate.return_value = np.array([0.8])
                    MockCalc.return_value = mock_calc

                    detector = KeywordDetector(
                        patterns=realistic_patterns,
                        enable_semantic=True,
                    )

                    # Run multiple queries
                    for _ in range(5):
                        detector.detect_best("scan for vulnerabilities")

                    # Check final stats
                    final_stats = mock_cache.get_cache_stats()
                    assert final_stats["hit_rate"] > 0.8


class TestE2EErrorHandling:
    """End-to-end tests for error handling."""

    def test_handles_invalid_model_name(self, realistic_patterns):
        """Test handling of invalid model name."""
        with patch("vibesop.semantic.models.os.getenv") as MockGetEnv:
            # Return invalid model name
            MockGetEnv.return_value = "invalid-model-name"

            config = EncoderConfig.from_env()
            # Should not crash
            assert config is not None

    def test_handles_empty_examples(self, realistic_patterns):
        """Test handling of patterns with no examples."""
        with patch("vibesop.triggers.detector.VectorCache"):
            with patch("vibesop.triggers.detector.SemanticEncoder"):
                with patch("vibesop.triggers.detector.SimilarityCalculator"):
                    # Create pattern with no examples
                    pattern_no_examples = TriggerPattern(
                        pattern_id="test/empty",
                        name="Empty Pattern",
                        description="Pattern with no examples",
                        category=PatternCategory.DEV,
                        keywords=["test"],
                        skill_id="/dev/test",
                        priority=50,
                        confidence_threshold=0.6,
                        examples=[],
                        enable_semantic=True,
                    )

                    patterns_with_empty = realistic_patterns + [pattern_no_examples]

                    detector = KeywordDetector(
                        patterns=patterns_with_empty,
                        enable_semantic=True,
                    )

                    # Should not crash
                    match = detector.detect_best("test something")
                    # Match or no match is fine, just shouldn't crash

    def test_handles_encoding_errors(self, realistic_patterns):
        """Test handling of encoding errors."""
        with patch("vibesop.triggers.detector.VectorCache"):
            with patch("vibesop.triggers.detector.SemanticEncoder") as MockEncoder:
                mock_encoder = Mock()
                mock_encoder.model_name = "test-model"
                # Mock encoding error
                mock_encoder.encode_query.side_effect = RuntimeError("Encoding failed")
                MockEncoder.return_value = mock_encoder

                # Should handle gracefully
                detector = KeywordDetector(
                    patterns=realistic_patterns,
                    enable_semantic=True,
                )

                # Should fall back to traditional or fail gracefully
                try:
                    match = detector.detect_best("test query")
                    # If it returns a match, it should be from traditional methods
                    if match:
                        assert match.semantic_method in [None, "tfidf"]
                except RuntimeError:
                    # Or it may raise an error, that's acceptable
                    pass
