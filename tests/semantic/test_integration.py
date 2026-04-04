"""Integration tests for semantic matching with routing engine."""

from __future__ import annotations

import pytest


class TestSemanticIntegration:
    """Tests for semantic module integration."""

    def test_semantic_encoder_import(self) -> None:
        """Test that semantic encoder can be imported."""
        try:
            from vibesop.semantic.encoder import SemanticEncoder

            assert SemanticEncoder is not None
        except ImportError:
            pytest.skip("sentence-transformers not installed")

    def test_semantic_similarity_import(self) -> None:
        """Test that semantic similarity can be imported."""
        try:
            from vibesop.semantic.similarity import SimilarityCalculator

            assert SimilarityCalculator is not None
        except ImportError:
            pytest.skip("sentence-transformers not installed")
