"""Semantic matching strategies for pattern detection.

This module implements different strategies for semantic pattern matching,
including pure cosine similarity and hybrid approaches.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import numpy as np

from vibesop.semantic.models import SemanticMatch, SemanticMethod, SemanticPattern

if TYPE_CHECKING:
    from vibesop.semantic.cache import VectorCache
    from vibesop.semantic.encoder import SemanticEncoder

logger = logging.getLogger(__name__)


class MatchingStrategy:
    """Base class for semantic matching strategies."""

    def match(
        self,
        query: str,
        patterns: list[SemanticPattern],
    ) -> list[SemanticMatch]:
        """Execute matching strategy."""
        raise NotImplementedError


class CosineSimilarityStrategy(MatchingStrategy):
    """Pure cosine similarity matching strategy."""

    def __init__(
        self,
        encoder: SemanticEncoder,
        cache: VectorCache,
        threshold: float = 0.7,
    ) -> None:
        self.encoder = encoder
        self.cache = cache
        self.threshold = threshold

    def match(
        self,
        query: str,
        patterns: list[SemanticPattern],
    ) -> list[SemanticMatch]:
        import time

        start = time.time()
        query_vector = self.encoder.encode_query(query, normalize=True)
        encoding_time = time.time() - start

        pattern_ids: list[str] = []
        pattern_vectors_list: list[Any] = []

        for pattern in patterns:
            vector = self.cache.get_or_compute(pattern.pattern_id, pattern.examples)
            pattern_ids.append(pattern.pattern_id)
            pattern_vectors_list.append(vector)

        pattern_vectors_array: Any = np.array(pattern_vectors_list)
        similarities: Any = np.dot(pattern_vectors_array, query_vector)

        matches: list[SemanticMatch] = []
        for pattern_id, similarity in zip(pattern_ids, similarities):
            if similarity >= self.threshold:
                matches.append(
                    SemanticMatch(
                        pattern_id=pattern_id,
                        confidence=float(similarity),
                        semantic_score=float(similarity),
                        semantic_method=SemanticMethod.COSINE,
                        vector_similarity=float(similarity),
                        model_used=self.encoder.model_name,
                        encoding_time=encoding_time,
                    )
                )

        matches.sort(key=lambda m: m.confidence, reverse=True)
        return matches


class HybridMatchingStrategy(MatchingStrategy):
    """Hybrid matching strategy combining traditional and semantic methods."""

    def __init__(
        self,
        encoder: SemanticEncoder,
        cache: VectorCache,
        keyword_weight: float = 0.3,
        regex_weight: float = 0.2,
        semantic_weight: float = 0.5,
        threshold: float = 0.7,
    ) -> None:
        total = keyword_weight + regex_weight + semantic_weight
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Weights must sum to 1.0, got {total:.2f}")

        self.encoder = encoder
        self.cache = cache
        self.keyword_weight = keyword_weight
        self.regex_weight = regex_weight
        self.semantic_weight = semantic_weight
        self.threshold = threshold

    def match(
        self,
        query: str,
        patterns: list[SemanticPattern],
    ) -> list[SemanticMatch]:
        import time

        start = time.time()
        query_vector = self.encoder.encode_query(query, normalize=True)
        encoding_time = time.time() - start

        pattern_data: list[dict[str, Any]] = []

        for pattern in patterns:
            vector = self.cache.get_or_compute(pattern.pattern_id, pattern.examples)
            similarity = float(np.dot(query_vector, vector))
            pattern_data.append(
                {
                    "pattern_id": pattern.pattern_id,
                    "semantic_score": similarity,
                    "examples": pattern.examples,
                }
            )

        for data in pattern_data:
            keyword_score = self._calculate_keyword_score(query, data["examples"])
            regex_score = self._calculate_regex_score(query, data["examples"])
            traditional_score = (
                keyword_score * self.keyword_weight + regex_score * self.regex_weight
            ) / (self.keyword_weight + self.regex_weight)
            data["keyword_score"] = keyword_score
            data["regex_score"] = regex_score
            data["traditional_score"] = traditional_score

        matches: list[SemanticMatch] = []
        for data in pattern_data:
            traditional_score: float = data["traditional_score"]
            semantic_score: float = data["semantic_score"]

            if traditional_score > 0.8:
                final_score = traditional_score
            elif semantic_score > 0.8:
                final_score = semantic_score
            else:
                final_score = (
                    traditional_score * (self.keyword_weight + self.regex_weight)
                    + semantic_score * self.semantic_weight
                )

            if final_score >= self.threshold:
                matches.append(
                    SemanticMatch(
                        pattern_id=data["pattern_id"],
                        confidence=final_score,
                        semantic_score=semantic_score,
                        semantic_method=SemanticMethod.HYBRID,
                        vector_similarity=semantic_score,
                        model_used=self.encoder.model_name,
                        encoding_time=encoding_time,
                    )
                )

        matches.sort(key=lambda m: m.confidence, reverse=True)
        return matches

    def _calculate_keyword_score(self, query: str, examples: list[str]) -> float:
        if not examples:
            return 0.0

        query_lower = query.lower()
        matched = 0
        for example in examples:
            example_lower = example.lower()
            words = example_lower.split()
            for word in words:
                if word in query_lower:
                    matched += 1
                    break

        if matched == 0:
            return 0.0

        score = 0.5 + (matched - 1) * 0.5 / len(examples)
        return min(score, 1.0)

    def _calculate_regex_score(self, query: str, examples: list[str]) -> float:
        import re

        if not examples:
            return 0.0

        matched = 0
        for example in examples:
            pattern = re.escape(example)
            pattern = pattern.replace(r"\ ", r"\s+")
            if re.search(pattern, query, re.IGNORECASE):
                matched += 1

        if matched == 0:
            return 0.0

        score = 0.5 + (matched - 1) * 0.5 / len(examples)
        return min(score, 1.0)
