"""Keyword detection engine for pattern matching.

This module provides the core detection logic for matching user input
against trigger patterns using multiple strategies.
"""

import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from vibesop.triggers.models import TriggerPattern, PatternMatch

# Conditionally import numpy (optional dependency for semantic features)
if TYPE_CHECKING:
    import numpy as np
else:
    try:
        import numpy as np
    except ImportError:
        np = None  # type: ignore
from vibesop.triggers.utils import (
    tokenize,
    calculate_tfidf,
    cosine_similarity,
    calculate_keyword_match_score,
    calculate_regex_match_score,
    calculate_combined_score,
)


class KeywordDetector:
    """Detect user intent from natural language input.

    Uses multi-strategy matching:
    1. Rule-based patterns (regex, keywords)
    2. TF-IDF vector similarity (traditional)
    3. Semantic embeddings (optional, v2.1.0)
    4. Confidence scoring

    Two-Stage Detection (v2.1.0):
        - Stage 1: Fast filter (< 1ms) using keywords/regex/TF-IDF
        - Stage 2: Semantic refine (< 20ms) using sentence embeddings

    Attributes:
        patterns: List of trigger patterns to match against
        confidence_threshold: Default minimum confidence for matches
        idf_cache: Pre-computed IDF scores for all patterns
        enable_semantic: Whether semantic matching is enabled
        semantic_encoder: SemanticEncoder instance (lazy loaded)
        semantic_cache: VectorCache instance (lazy loaded)
        semantic_calculator: SimilarityCalculator instance (lazy loaded)

    Example:
        >>> detector = KeywordDetector(patterns=DEFAULT_PATTERNS)
        >>> match = detector.detect_best("扫描安全漏洞")
        >>> print(match.pattern_id)  # "security/scan"
        >>> print(match.confidence)  # 0.95
        >>>
        >>> # With semantic matching enabled
        >>> detector = KeywordDetector(
        ...     patterns=DEFAULT_PATTERNS,
        ...     enable_semantic=True
        ... )
        >>> match = detector.detect_best("帮我检查代码安全问题")
        >>> print(match.semantic_score)  # 0.87
    """

    def __init__(
        self,
        patterns: list[TriggerPattern],
        confidence_threshold: float = 0.6,
        enable_semantic: bool = False,
        semantic_config: Optional["EncoderConfig"] = None,
    ):
        """Initialize keyword detector.

        Args:
            patterns: List of trigger patterns
            confidence_threshold: Default minimum confidence threshold
            enable_semantic: Enable semantic matching (default: False)
            semantic_config: Semantic encoder configuration (optional)
        """
        self.patterns = sorted(
            patterns,
            key=lambda p: p.priority,
            reverse=True
        )
        self.confidence_threshold = confidence_threshold

        # Pre-compute IDF scores for all pattern examples
        self.idf_cache = self._build_idf_cache()

        # Semantic components (v2.1.0)
        self.enable_semantic = enable_semantic
        self.semantic_config = semantic_config

        # Lazy-loaded semantic components
        self.semantic_encoder = None
        self.semantic_cache = None
        self.semantic_calculator = None

        # Initialize semantic components if enabled
        if self.enable_semantic:
            self._init_semantic_components()

    def _build_idf_cache(self) -> dict[str, float]:
        """Build IDF cache from all pattern examples and keywords.

        Returns:
            Dictionary mapping term to IDF score
        """
        from vibesop.triggers.utils import calculate_idf

        # Collect all text from patterns
        documents = []

        for pattern in self.patterns:
            # Add keywords as a document
            if pattern.keywords:
                documents.append(pattern.keywords)

            # Add examples as documents
            for example in pattern.examples:
                documents.append(tokenize(example))

        return calculate_idf(documents)

    def _init_semantic_components(self) -> None:
        """Initialize semantic components with lazy loading and graceful degradation.

        Attempts to initialize semantic encoder, cache, and calculator.
        If sentence-transformers is not installed or initialization fails,
        disables semantic matching and logs a warning.

        Raises:
            ImportError: If sentence-transformers is not available
        """
        try:
            from vibesop.semantic.models import EncoderConfig
            from vibesop.semantic.encoder import SemanticEncoder
            from vibesop.semantic.cache import VectorCache
            from vibesop.semantic.similarity import SimilarityCalculator

            # Use provided config or create from environment
            config = self.semantic_config or EncoderConfig.from_env()

            # Initialize semantic encoder
            self.semantic_encoder = SemanticEncoder(
                model_name=config.model_name,
                device=config.device,
                cache_dir=config.cache_dir,
                batch_size=config.batch_size,
            )

            # Initialize vector cache
            cache_dir = config.cache_dir or Path.home() / ".cache" / "vibesop" / "semantic"
            self.semantic_cache = VectorCache(
                cache_dir=cache_dir,
                encoder=self.semantic_encoder,
                ttl=86400,  # 24 hours
            )

            # Initialize similarity calculator
            self.semantic_calculator = SimilarityCalculator(
                metric="cosine",
                normalize=True,
            )

            # Precompute pattern vectors (warmup)
            self._precompute_pattern_vectors()

        except ImportError as e:
            import logging
            logging.warning(
                f"Semantic matching requires sentence-transformers: {e}. "
                "Install with: pip install vibesop[semantic]"
            )
            self.enable_semantic = False

    def _precompute_pattern_vectors(self) -> None:
        """Precompute semantic vectors for all patterns.

        This is called during initialization to warm up the cache.
        Computes vectors for patterns that have semantic matching enabled.
        """
        patterns_with_semantic = [
            p for p in self.patterns
            if p.enable_semantic or p.semantic_examples
        ]

        if not patterns_with_semantic:
            return

        # Compute vectors in batch
        for pattern in patterns_with_semantic:
            examples = pattern.examples + pattern.semantic_examples
            if examples:
                self.semantic_cache.get_or_compute(
                    pattern.pattern_id,
                    examples
                )

    def detect_best(
        self,
        query: str,
        min_confidence: Optional[float] = None
    ) -> Optional[PatternMatch]:
        """Detect best matching pattern for query.

        Uses two-stage detection:
        1. Fast filter: Keywords + regex + TF-IDF (< 1ms)
        2. Semantic refine: Embedding similarity (if enabled, < 20ms)

        Args:
            query: User input query
            min_confidence: Minimum confidence threshold (uses default if None)

        Returns:
            PatternMatch with best match, or None if no match meets threshold
        """
        if not query or not query.strip():
            return None

        threshold = min_confidence or self.confidence_threshold

        # Stage 1: Fast filter using traditional methods
        matches = self._fast_filter(query)

        if not matches:
            return None

        # Quick return for single high-confidence match
        if len(matches) == 1 and matches[0].confidence > 0.9:
            return matches[0]

        # Stage 2: Semantic refine (if enabled)
        if self.enable_semantic and self.semantic_calculator:
            return self._semantic_refine(query, matches, threshold)

        # Return highest confidence match
        best_match = max(matches, key=lambda m: m.confidence)

        # Check against overall threshold
        if best_match.confidence >= threshold:
            return best_match

        return None

    def _fast_filter(self, query: str) -> list[PatternMatch]:
        """Stage 1: Fast filter using traditional methods.

        Uses keywords, regex, and TF-IDF to quickly filter patterns.

        Args:
            query: User input query

        Returns:
            List of candidate matches, sorted by confidence
        """
        matches = []
        for pattern in self.patterns:
            match = self._score_pattern(query, pattern)
            if match and match.confidence >= pattern.confidence_threshold:
                matches.append(match)

        # Sort by confidence
        matches.sort(key=lambda m: m.confidence, reverse=True)
        return matches

    def _semantic_refine(
        self,
        query: str,
        candidates: list[PatternMatch],
        threshold: float
    ) -> Optional[PatternMatch]:
        """Stage 2: Semantic refinement using sentence embeddings.

        Enhances candidate matches with semantic similarity scores.
        Uses score fusion to combine traditional and semantic scores.

        Score Fusion Strategy:
        - Traditional score > 0.8: Keep as-is (high confidence)
        - Semantic score > 0.8: Use semantic score (high semantic confidence)
        - Otherwise: Weighted average (40% traditional + 60% semantic)

        Args:
            query: User input query
            candidates: Candidate matches from fast filter
            threshold: Minimum confidence threshold

        Returns:
            Enhanced PatternMatch with best score, or None
        """
        if not candidates:
            return None

        # Encode query
        start_time = time.time()
        query_vector = self.semantic_encoder.encode_query(query)
        encoding_time = time.time() - start_time

        # Get pattern vectors
        pattern_vectors = []
        for match in candidates:
            pattern = self._get_pattern_by_id(match.pattern_id)
            if not pattern:
                continue

            # Use semantic examples if available
            examples = pattern.examples + pattern.semantic_examples
            if not examples:
                # Fallback to keywords and regex patterns
                examples = pattern.keywords + pattern.regex_patterns

            if examples:
                vector = self.semantic_cache.get_or_compute(
                    pattern.pattern_id,
                    examples
                )
                pattern_vectors.append((match, vector))

        if not pattern_vectors:
            # No vectors available, return best traditional match
            return max(candidates, key=lambda m: m.confidence)

        # Calculate similarities
        matches_with_vectors = [m for m, _ in pattern_vectors]
        vectors = np.array([v for _, v in pattern_vectors])
        similarities = self.semantic_calculator.calculate(
            query_vector,
            vectors
        )

        # Fuse scores and update matches
        best_match = None
        best_score = 0.0

        for match, similarity in zip(matches_with_vectors, similarities):
            # Score fusion strategy
            if match.confidence > 0.8:
                # High traditional confidence, keep as-is
                final_score = match.confidence
            elif similarity > 0.8:
                # High semantic confidence, use semantic
                final_score = similarity
            else:
                # Medium scores, use weighted average
                final_score = match.confidence * 0.4 + similarity * 0.6

            # Update match with semantic info
            match.confidence = min(final_score, 1.0)
            match.semantic_score = float(similarity)
            match.semantic_method = "cosine"
            match.model_used = self.semantic_encoder.model_name
            match.encoding_time = encoding_time

            if final_score > best_score:
                best_score = final_score
                best_match = match

        # Check threshold
        if best_match and best_match.confidence >= threshold:
            return best_match

        return None

    def _get_pattern_by_id(self, pattern_id: str) -> Optional[TriggerPattern]:
        """Get pattern by ID.

        Args:
            pattern_id: Pattern identifier

        Returns:
            TriggerPattern or None if not found
        """
        for pattern in self.patterns:
            if pattern.pattern_id == pattern_id:
                return pattern
        return None

    def detect_all(
        self,
        query: str,
        min_confidence: Optional[float] = None
    ) -> list[PatternMatch]:
        """Detect all matching patterns for query.

        Args:
            query: User input query
            min_confidence: Minimum confidence threshold

        Returns:
            List of PatternMatch objects, sorted by confidence (descending)
        """
        if not query or not query.strip():
            return []

        threshold = min_confidence or self.confidence_threshold

        # Stage 1: Fast filter
        matches = self._fast_filter(query)

        # Filter by threshold
        matches = [m for m in matches if m.confidence >= threshold]

        # Stage 2: Semantic refine (if enabled)
        if self.enable_semantic and matches and self.semantic_calculator:
            # Refine all matches with semantic scores
            refined_match = self._semantic_refine(query, matches, threshold)
            if refined_match:
                # Return all matches with updated semantic scores
                # Need to re-run semantic refinement for all candidates
                self._semantic_refine_all(query, matches)
                matches.sort(key=lambda m: m.confidence, reverse=True)

        return matches

    def _semantic_refine_all(
        self,
        query: str,
        candidates: list[PatternMatch]
    ) -> None:
        """Apply semantic refinement to all candidates.

        Updates candidates in-place with semantic scores.

        Args:
            query: User input query
            candidates: Candidate matches to refine
        """
        if not candidates or not self.semantic_calculator:
            return

        # Encode query
        start_time = time.time()
        query_vector = self.semantic_encoder.encode_query(query)
        encoding_time = time.time() - start_time

        # Get pattern vectors
        pattern_vectors = []
        for match in candidates:
            pattern = self._get_pattern_by_id(match.pattern_id)
            if not pattern:
                continue

            examples = pattern.examples + pattern.semantic_examples
            if not examples:
                examples = pattern.keywords + pattern.regex_patterns

            if examples:
                vector = self.semantic_cache.get_or_compute(
                    pattern.pattern_id,
                    examples
                )
                pattern_vectors.append((match, vector))

        if not pattern_vectors:
            return

        # Calculate similarities
        matches_with_vectors = [m for m, _ in pattern_vectors]
        vectors = np.array([v for _, v in pattern_vectors])
        similarities = self.semantic_calculator.calculate(
            query_vector,
            vectors
        )

        # Update all matches with semantic info
        for match, similarity in zip(matches_with_vectors, similarities):
            # Score fusion
            if match.confidence > 0.8:
                final_score = match.confidence
            elif similarity > 0.8:
                final_score = similarity
            else:
                final_score = match.confidence * 0.4 + similarity * 0.6

            match.confidence = min(final_score, 1.0)
            match.semantic_score = float(similarity)
            match.semantic_method = "cosine"
            match.model_used = self.semantic_encoder.model_name
            match.encoding_time = encoding_time

    def _score_pattern(
        self,
        query: str,
        pattern: TriggerPattern
    ) -> Optional[PatternMatch]:
        """Score a single pattern against the query.

        Calculates combined confidence using:
        - Keyword matching (40%)
        - Regex matching (30%)
        - Semantic similarity (30%)

        Args:
            query: User input query
            pattern: Pattern to score

        Returns:
            PatternMatch with confidence score, or None if no match
        """
        # Calculate keyword score
        keyword_score = calculate_keyword_match_score(
            query,
            pattern.keywords
        )

        # Calculate regex score
        regex_score = calculate_regex_match_score(
            query,
            pattern.regex_patterns
        )

        # Calculate semantic score
        semantic_score = self._calculate_semantic_score(
            query,
            pattern
        )

        # Calculate combined score
        combined_score = calculate_combined_score(
            keyword_score,
            regex_score,
            semantic_score
        )

        # If combined score is very low, no match
        if combined_score < 0.1:
            return None

        # Collect matched keywords
        matched_keywords = [
            kw for kw in pattern.keywords
            if kw.lower() in query.lower()
        ]

        # Collect matched regex
        matched_regex = [
            pattern_str for pattern_str in pattern.regex_patterns
            if _regex_matches(pattern_str, query)
        ]

        return PatternMatch(
            pattern_id=pattern.pattern_id,
            confidence=combined_score,
            metadata={
                "category": pattern.category,
                "name": pattern.name,
                "keyword_score": keyword_score,
                "regex_score": regex_score,
            },
            matched_keywords=matched_keywords,
            matched_regex=matched_regex,
            semantic_score=semantic_score,
            # Additional semantic fields (v2.1.0)
            semantic_method="tfidf" if semantic_score > 0 else None,
            model_used=None,  # TF-IDF doesn't use embedding models
            encoding_time=None,
        )

    def _calculate_semantic_score(
        self,
        query: str,
        pattern: TriggerPattern
    ) -> float:
        """Calculate semantic similarity score using TF-IDF.

        Compares query against pattern examples using TF-IDF + cosine similarity.

        Args:
            query: User input query
            pattern: Pattern to compare against

        Returns:
            Similarity score between 0.0 and 1.0
        """
        if not pattern.examples:
            return 0.0

        # Tokenize query
        query_tokens = tokenize(query)
        query_tfidf = calculate_tfidf(query_tokens, self.idf_cache)

        # Calculate similarity with each example
        similarities = []
        for example in pattern.examples:
            example_tokens = tokenize(example)
            example_tfidf = calculate_tfidf(example_tokens, self.idf_cache)

            sim = cosine_similarity(query_tfidf, example_tfidf)
            similarities.append(sim)

        # Return maximum similarity, clamped to [0, 1]
        max_sim = max(similarities) if similarities else 0.0
        return min(max(max_sim, 0.0), 1.0)


def _regex_matches(pattern: str, text: str) -> bool:
    """Check if regex pattern matches text.

    Args:
        pattern: Regex pattern string
        text: Text to match against

    Returns:
        True if pattern matches text
    """
    try:
        return bool(re.search(pattern, text, re.IGNORECASE))
    except re.error:
        # Invalid regex pattern
        return False
