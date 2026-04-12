"""Concrete matcher implementations for unified matching system.

This module provides production-ready implementations of the IMatcher protocol:
- KeywordMatcher: Fast keyword-based matching (<1ms)
- TFIDFMatcher: TF-IDF semantic matching (~5ms)
- EmbeddingMatcher: Vector embedding matching (~20ms)
- LevenshteinMatcher: Fuzzy matching for typos (~10ms)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from vibesop.core.matching.base import (
    MatchResult,
    MatcherType,
    RoutingContext,
    SimilarityMetric,
)
from vibesop.core.matching.similarity import SimilarityCalculator
from vibesop.core.matching.tfidf import TFIDFCalculator
from vibesop.core.matching.tokenizers import TokenizerConfig, tokenize

if TYPE_CHECKING:
    from vibesop.core.types import (
        ConfidenceScore,
        MatcherCapabilitiesDict,
        SkillCandidateDict,
    )

if TYPE_CHECKING:
    import numpy as np
else:
    try:
        import numpy as np
    except ImportError:
        np = None


@dataclass
class MatcherConfig:
    """Configuration for matchers."""

    min_confidence: float = 0.3
    case_sensitive: bool = False
    use_cache: bool = True
    tokenizer_config: TokenizerConfig = field(default_factory=TokenizerConfig)


class KeywordMatcher:
    """Fast keyword-based matcher.

    Matches skills based on keyword presence in query text.
    This is the fastest matcher for exact keyword matches.

    Example:
        >>> matcher = KeywordMatcher()
        >>> results = matcher.match("debug database error", candidates)
    """

    def __init__(self, config: MatcherConfig | None = None):
        self._config = config or MatcherConfig()
        self._cache: dict[str, list[MatchResult]] = {}

    def match(
        self,
        query: str,
        candidates: list[SkillCandidateDict],
        _context: RoutingContext | None = None,
        top_k: int = 10,
    ) -> list[MatchResult]:
        """Match query against candidates using keyword detection."""
        cache_key = f"keyword:{query}"
        if self._config.use_cache and cache_key in self._cache:
            return self._cache[cache_key][:top_k]

        # Tokenize query
        query_tokens = set(
            tokenize(query, self._config.tokenizer_config)
            if not self._config.case_sensitive
            else query.split()
        )

        results: list[MatchResult] = []

        for candidate in candidates:
            score = self._score(query_tokens, candidate)
            if score >= self._config.min_confidence:
                results.append(
                    MatchResult(
                        skill_id=candidate.get("id", ""),
                        confidence=score,
                        score_breakdown={"keyword_match": score},
                        matcher_type=MatcherType.KEYWORD,
                        matched_keywords=self._get_matched_keywords(query_tokens, candidate),
                        metadata={
                            "matcher": "keyword",
                            "namespace": candidate.get("namespace", "builtin"),
                        },
                    )
                )

        # Sort by confidence descending
        results.sort(key=lambda r: r.confidence, reverse=True)

        if self._config.use_cache:
            self._cache[cache_key] = results

        return results[:top_k]

    def score(
        self,
        query: str,
        candidate: SkillCandidateDict,
        _context: RoutingContext | None = None,
    ) -> ConfidenceScore:
        """Score a single candidate."""
        query_tokens = set(
            tokenize(query, self._config.tokenizer_config)
            if not self._config.case_sensitive
            else query.split()
        )
        return self._score(query_tokens, candidate)

    def _score(self, query_tokens: set[str], candidate: SkillCandidateDict) -> ConfidenceScore:
        """Calculate keyword match score."""
        # Get text fields from candidate
        text_fields = [
            candidate.get("name", ""),
            candidate.get("description", ""),
            candidate.get("intent", ""),
            " ".join(candidate.get("keywords", [])),
        ]

        combined_text = " ".join(text_fields).lower()
        candidate_tokens = set(tokenize(combined_text))

        # Calculate Jaccard similarity
        intersection = query_tokens & candidate_tokens
        union = query_tokens | candidate_tokens

        if not union:
            return 0.0

        return len(intersection) / len(union)

    def _get_matched_keywords(
        self,
        query_tokens: set[str],
        candidate: SkillCandidateDict,
    ) -> list[str]:
        """Get list of matched keywords."""
        text_fields = [
            candidate.get("name", ""),
            candidate.get("description", ""),
            " ".join(candidate.get("keywords", [])),
        ]

        combined_text = " ".join(text_fields).lower()
        candidate_tokens = set(tokenize(combined_text))

        return list(query_tokens & candidate_tokens)

    def get_capabilities(self) -> MatcherCapabilitiesDict:
        """Return matcher capabilities."""
        return {
            "type": "keyword",
            "speed": "fast",
            "accuracy": "medium",
            "requires_semantic": False,
        }


class TFIDFMatcher:
    """TF-IDF based semantic matcher.

    Uses TF-IDF vectorization and cosine similarity for semantic matching.
    Good for matching intent beyond exact keywords.

    Example:
        >>> matcher = TFIDFMatcher()
        >>> matcher.fit(candidates)  # Fit on corpus
        >>> results = matcher.match("database connection issue", candidates)
    """

    def __init__(self, config: MatcherConfig | None = None):
        self._config = config or MatcherConfig()
        self._tfidf_calc = TFIDFCalculator()
        self._similarity_calc = SimilarityCalculator(metric=SimilarityMetric.COSINE)
        self._fitted = False
        self._candidate_vectors: dict[str, dict[str, float]] = {}

    def fit(self, candidates: list[dict[str, Any]]) -> None:
        """Fit TF-IDF calculator on candidate corpus."""
        # Collect all documents
        documents = []
        self._candidate_ids = []

        for candidate in candidates:
            text = self._candidate_to_text(candidate)
            tokens = tokenize(text, self._config.tokenizer_config)
            documents.append(tokens)
            self._candidate_ids.append(candidate.get("id", ""))

        # Fit TF-IDF
        self._tfidf_calc.fit(documents)
        self._fitted = True

    def match(
        self,
        query: str,
        candidates: list[SkillCandidateDict],
        _context: RoutingContext | None = None,
        top_k: int = 10,
    ) -> list[MatchResult]:
        """Match query against candidates using TF-IDF similarity."""
        if not self._fitted:
            self.fit(candidates)

        # Transform query
        query_tokens = tokenize(query, self._config.tokenizer_config)
        query_vec = self._tfidf_calc.transform(query_tokens)

        results: list[MatchResult] = []

        for candidate in candidates:
            skill_id = candidate.get("id", "")
            candidate_text = self._candidate_to_text(candidate)
            candidate_tokens = tokenize(candidate_text, self._config.tokenizer_config)
            candidate_vec = self._tfidf_calc.transform(candidate_tokens)

            # Calculate cosine similarity using TF-IDF vectors
            score = query_vec.dot_product(candidate_vec)

            if score >= self._config.min_confidence:
                results.append(
                    MatchResult(
                        skill_id=skill_id,
                        confidence=score,
                        score_breakdown={"tfidf_cosine": score},
                        matcher_type=MatcherType.TFIDF,
                        semantic_score=score,
                        metadata={
                            "matcher": "tfidf",
                            "namespace": candidate.get("namespace", "builtin"),
                        },
                    )
                )

        results.sort(key=lambda r: r.confidence, reverse=True)
        return results[:top_k]

    def score(
        self,
        query: str,
        candidate: SkillCandidateDict,
        _context: RoutingContext | None = None,
    ) -> ConfidenceScore:
        """Score a single candidate."""
        if not self._fitted:
            # Single candidate fit
            self.fit([candidate])

        query_tokens = tokenize(query, self._config.tokenizer_config)
        query_vec = self._tfidf_calc.transform(query_tokens)

        candidate_text = self._candidate_to_text(candidate)
        candidate_tokens = tokenize(candidate_text, self._config.tokenizer_config)
        candidate_vec = self._tfidf_calc.transform(candidate_tokens)

        return query_vec.dot_product(candidate_vec)

    def _candidate_to_text(self, candidate: SkillCandidateDict) -> str:
        """Convert candidate to searchable text."""
        fields = [
            candidate.get("name", ""),
            candidate.get("description", ""),
            candidate.get("intent", ""),
            " ".join(candidate.get("keywords", [])),
            " ".join(candidate.get("triggers", [])),
        ]
        return " ".join(fields)

    def get_capabilities(self) -> MatcherCapabilitiesDict:
        """Return matcher capabilities."""
        return {
            "type": "tfidf",
            "speed": "medium",
            "accuracy": "good",
            "requires_semantic": False,
        }


class EmbeddingMatcher:
    """Vector embedding matcher using sentence transformers.

    Provides the most accurate semantic matching but requires
    sentence-transformers to be installed.

    Example:
        >>> matcher = EmbeddingVectorizer()
        >>> results = matcher.match("I need help with testing", candidates)
    """

    def __init__(
        self,
        model_name: str = "paraphrase-multilingual-MiniLM-L12-v2",
        config: MatcherConfig | None = None,
    ):
        self._config = config or MatcherConfig()
        self._model_name = model_name
        self._model = None
        self._candidate_embeddings: dict[str, Any] | None = None

    def _load_model(self) -> None:
        """Lazy load the embedding model."""
        if self._model is not None:
            return

        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
        except ImportError:
            raise ImportError(
                "sentence-transformers is required for EmbeddingMatcher. "
                "Install with: pip install sentence-transformers"
            ) from None

    def fit(self, candidates: list[dict[str, Any]]) -> None:
        """Pre-compute embeddings for all candidates."""
        if np is None:
            raise ImportError("numpy is required for EmbeddingMatcher")

        self._load_model()

        texts = [self._candidate_to_text(c) for c in candidates]
        embeddings = self._model.encode(texts)

        self._candidate_embeddings = {
            c.get("id", ""): embeddings[i] for i, c in enumerate(candidates)
        }
        self._candidate_ids = [c.get("id", "") for c in candidates]

    def match(
        self,
        query: str,
        candidates: list[SkillCandidateDict],
        _context: RoutingContext | None = None,
        top_k: int = 10,
    ) -> list[MatchResult]:
        """Match query using vector embeddings."""
        if np is None:
            return []

        self._load_model()

        # Fit if not already done
        if self._candidate_embeddings is None:
            self.fit(candidates)

        # Encode query
        query_embedding = self._model.encode([query])[0]

        results: list[MatchResult] = []

        for candidate in candidates:
            skill_id = candidate.get("id", "")
            if skill_id not in self._candidate_embeddings:
                continue

            candidate_embedding = self._candidate_embeddings[skill_id]

            # Calculate cosine similarity
            score = float(
                np.dot(query_embedding, candidate_embedding)
                / (np.linalg.norm(query_embedding) * np.linalg.norm(candidate_embedding) + 1e-10)
            )

            if score >= self._config.min_confidence:
                results.append(
                    MatchResult(
                        skill_id=skill_id,
                        confidence=score,
                        score_breakdown={"embedding_cosine": score},
                        matcher_type=MatcherType.EMBEDDING,
                        semantic_score=score,
                        metadata={
                            "matcher": "embedding",
                            "model": self._model_name,
                            "namespace": candidate.get("namespace", "builtin"),
                        },
                    )
                )

        results.sort(key=lambda r: r.confidence, reverse=True)
        return results[:top_k]

    def score(
        self,
        query: str,
        candidate: dict[str, Any],
        context: RoutingContext | None = None,
    ) -> float:
        """Score a single candidate."""
        results = self.match(query, [candidate], context, top_k=1)
        return results[0].confidence if results else 0.0

    def _candidate_to_text(self, candidate: SkillCandidateDict) -> str:
        """Convert candidate to searchable text."""
        fields = [
            candidate.get("name", ""),
            candidate.get("description", ""),
            candidate.get("intent", ""),
        ]
        return " ".join(f for f in fields if f)

    def get_capabilities(self) -> MatcherCapabilitiesDict:
        """Return matcher capabilities."""
        return {
            "type": "embedding",
            "speed": "slow",
            "accuracy": "excellent",
            "requires_semantic": True,
        }


class LevenshteinMatcher:
    """Fuzzy matcher using Levenshtein distance.

    Good for catching typos and similar-but-not-exact matches.

    Example:
        >>> matcher = LevenshteinMatcher()
        >>> results = matcher.match("databse error", candidates)  # typo in "database"
    """

    def __init__(self, config: MatcherConfig | None = None):
        self._config = config or MatcherConfig()

    def match(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        context: RoutingContext | None = None,
        top_k: int = 10,
    ) -> list[MatchResult]:
        """Match query using Levenshtein distance."""
        results: list[MatchResult] = []

        for candidate in candidates:
            score = self.score(query, candidate, context)

            if score >= self._config.min_confidence:
                results.append(
                    MatchResult(
                        skill_id=candidate.get("id", ""),
                        confidence=score,
                        score_breakdown={"levenshtein": score},
                        matcher_type=MatcherType.LEVENSHTEIN,
                        metadata={
                            "matcher": "levenshtein",
                            "namespace": candidate.get("namespace", "builtin"),
                        },
                    )
                )

        results.sort(key=lambda r: r.confidence, reverse=True)
        return results[:top_k]

    def score(
        self,
        query: str,
        candidate: SkillCandidateDict,
        _context: RoutingContext | None = None,
    ) -> ConfidenceScore:
        """Score a single candidate using token-aware Levenshtein similarity.

        Instead of comparing the entire query against the full description,
        we tokenize the query and match each token against the candidate's
        name and keywords. This avoids pathologically low scores for long
        queries against short skill descriptions.
        """
        query_tokens = self._tokenize(query)
        candidate_tokens = self._candidate_tokens(candidate)

        if not query_tokens or not candidate_tokens:
            # Fallback to full-string comparison for very short inputs
            text = self._candidate_to_text(candidate)
            return self._normalized_similarity(query, text)

        # Score each query token against the best-matching candidate token
        token_scores = []
        for qt in query_tokens:
            if len(qt) <= 2:
                continue  # Skip very short tokens
            best = max(
                self._normalized_similarity(qt, ct)
                for ct in candidate_tokens
            )
            token_scores.append(best)

        if not token_scores:
            return 0.0

        # Also include a bonus for exact name match
        name = candidate.get("name", "").lower()
        name_bonus = 0.0
        if any(qt == name for qt in query_tokens):
            name_bonus = 0.15

        avg_score = sum(token_scores) / len(token_scores)
        return min(1.0, avg_score + name_bonus)

    def _normalized_similarity(self, s1: str, s2: str) -> float:
        """Normalized Levenshtein similarity (0-1)."""
        distance = self._levenshtein_distance(s1, s2)
        max_len = max(len(s1), len(s2))
        if max_len == 0:
            return 1.0
        return 1.0 - (distance / max_len)

    def _tokenize(self, text: str) -> list[str]:
        """Simple whitespace and punctuation tokenizer."""
        import re

        return [
            t.lower()
            for t in re.findall(r"[a-zA-Z0-9\u4e00-\u9fff]+", text)
            if len(t) > 1
        ]

    def _candidate_tokens(self, candidate: SkillCandidateDict) -> list[str]:
        """Extract searchable tokens from a candidate."""
        tokens: set[str] = set()
        for key in ("name", "keywords", "tags"):
            value = candidate.get(key)
            if isinstance(value, str):
                tokens.update(self._tokenize(value))
            elif isinstance(value, list):
                for item in value:
                    tokens.update(self._tokenize(str(item)))
        # Include skill ID parts as tokens
        skill_id = candidate.get("id", "")
        tokens.update(skill_id.replace("/", " ").replace("-", " ").lower().split())
        return list(tokens)

    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """Calculate Levenshtein distance between two strings."""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        previous_row = list(range(len(s2) + 1))

        for i, c1 in enumerate(s1):
            current_row = [i + 1]

            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)

                current_row.append(min(insertions, deletions, substitutions))

            previous_row = current_row

        return previous_row[-1]

    def _candidate_to_text(self, candidate: SkillCandidateDict) -> str:
        """Convert candidate to searchable text."""
        return candidate.get("name", "") + " " + candidate.get("description", "")

    def get_capabilities(self) -> MatcherCapabilitiesDict:
        """Return matcher capabilities."""
        return {
            "type": "levenshtein",
            "speed": "medium",
            "accuracy": "medium",
            "requires_semantic": False,
        }


# Convenience exports
__all__ = [
    "EmbeddingMatcher",
    "KeywordMatcher",
    "LevenshteinMatcher",
    "MatcherConfig",
    "TFIDFMatcher",
]
