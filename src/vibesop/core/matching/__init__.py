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
    RoutingContext,
    SimilarityMetric,
    MatcherType,
)
from vibesop.core.matching.tokenizers import (
    tokenize,
    TokenizerConfig,
    TokenizerMode,
)
from vibesop.core.matching.similarity import (
    SimilarityCalculator,
    cosine_similarity,
)
from vibesop.core.matching.tfidf import (
    TFIDFCalculator,
    TFIDFVector,
)
from vibesop.core.matching.strategies import (
    KeywordMatcher,
    TFIDFMatcher,
    EmbeddingMatcher,
    LevenshteinMatcher,
    MatcherConfig,
)

__all__ = [
    # Base interfaces
    "IMatcher",
    "MatchResult",
    "RoutingContext",
    "SimilarityMetric",
    "MatcherType",
    # Tokenizers
    "tokenize",
    "TokenizerConfig",
    "TokenizerMode",
    # Similarity
    "SimilarityCalculator",
    "cosine_similarity",
    # TF-IDF
    "TFIDFCalculator",
    "TFIDFVector",
    # Strategies
    "KeywordMatcher",
    "TFIDFMatcher",
    "EmbeddingMatcher",
    "LevenshteinMatcher",
    "MatcherConfig",
]
