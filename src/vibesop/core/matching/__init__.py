"""Unified matching infrastructure for VibeSOP routing.

This module provides a unified interface for all matching strategies,
eliminating code duplication across triggers/, routing/, and semantic/.

Example:
    >>> from vibesop.core.matching import tokenize, SimilarityCalculator
    >>> tokens = tokenize("扫描安全漏洞")
    >>> calc = SimilarityCalculator()
    >>> scores = calc.calculate("query", ["doc1", "doc2"])
"""

from vibesop.core.matching.base import (
    IMatcher,
    MatchResult,
    MatcherType,
    RoutingContext,
    SimilarityMetric,
)
from vibesop.core.matching.similarity import (
    SimilarityCalculator,
    cosine_similarity,
)
from vibesop.core.matching.strategies import (
    EmbeddingMatcher,
    KeywordMatcher,
    LevenshteinMatcher,
    MatcherConfig,
    TFIDFMatcher,
)
from vibesop.core.matching.tfidf import (
    TFIDFCalculator,
    TFIDFVector,
)
from vibesop.core.matching.tokenizers import (
    TokenizerConfig,
    TokenizerMode,
    tokenize,
)

__all__ = [
    "EmbeddingMatcher",
    # Base interfaces
    "IMatcher",
    # Strategies
    "KeywordMatcher",
    "LevenshteinMatcher",
    "MatchResult",
    "MatcherConfig",
    "MatcherType",
    "RoutingContext",
    # Similarity
    "SimilarityCalculator",
    "SimilarityMetric",
    # TF-IDF
    "TFIDFCalculator",
    "TFIDFMatcher",
    "TFIDFVector",
    "TokenizerConfig",
    "TokenizerMode",
    "cosine_similarity",
    # Tokenizers
    "tokenize",
]
