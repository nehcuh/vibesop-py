"""Semantic matching using TF-IDF and cosine similarity.

Implements Layer 3 of the routing system:
- TF-IDF (Term Frequency-Inverse Document Frequency)
- Cosine similarity for document comparison
- Stop word filtering for better results
"""

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from vibesop.core.config_module import ConfigLoader

# Common stop words (English and Chinese)
STOP_WORDS = {
    # English
    "a",
    "an",
    "the",
    "and",
    "or",
    "but",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "could",
    "should",
    "may",
    "might",
    "must",
    "can",
    "to",
    "of",
    "in",
    "on",
    "at",
    "by",
    "for",
    "with",
    "about",
    "from",
    "as",
    "into",
    "through",
    "during",
    "before",
    "after",
    "above",
    "below",
    "between",
    "under",
    "again",
    "further",
    "then",
    "once",
    "here",
    "there",
    "when",
    "where",
    "why",
    "how",
    "all",
    "each",
    "few",
    "more",
    "most",
    "other",
    "some",
    "such",
    "no",
    "nor",
    "not",
    "only",
    "own",
    "same",
    "so",
    "than",
    "too",
    "very",
    "just",
    "help",
    "use",
    "make",
    "want",
    "need",
    # Chinese
    "的",
    "了",
    "是",
    "在",
    "有",
    "和",
    "就",
    "不",
    "人",
    "都",
    "一",
    "一个",
    "上",
    "也",
    "很",
    "到",
    "说",
    "要",
    "去",
    "你",
    "会",
    "着",
    "没有",
    "看",
    "好",
    "自己",
    "这",
    "那",
    "我",
    "他",
    "她",
    "它",
    "我们",
    "你们",
    "他们",
    "什么",
    "怎么",
    "为什么",
    "哪里",
    "哪个",
    "多少",
    "几个",
    "帮我",
    "请",
    "麻烦",
    "可以",
    "能不能",
    "如何",
}


@dataclass
class Document:
    """A document for TF-IDF processing.

    Attributes:
        text: Document text
        tokens: Tokenized and filtered terms
        metadata: Associated metadata (skill_id, etc.)
    """

    text: str
    tokens: list[str]
    metadata: dict[str, Any]


@dataclass
class SemanticMatch:
    """Result of semantic matching.

    Attributes:
        skill_id: Matched skill ID
        score: Similarity score (0.0 to 1.0)
        metadata: Additional metadata
    """

    skill_id: str
    score: float
    metadata: dict[str, Any]


class SemanticMatcher:
    """TF-IDF based semantic matcher.

    Usage:
        matcher = SemanticMatcher()
        matcher.index_skills(config_loader.get_all_skills())
        result = matcher.match("帮我调试这个 bug")
        print(result.skill_id)  # systematic-debugging
    """

    def __init__(
        self,
        min_score: float = 0.3,
    ) -> None:
        """Initialize the semantic matcher.

        Args:
            min_score: Minimum similarity score to consider a match
        """
        self.min_score = min_score
        self._documents: list[Document] = []
        self._idf: dict[str, float] = {}
        self._config_loader: ConfigLoader | None = None

    def index_skills(
        self,
        skills: list[dict[str, Any]],
        config_loader: ConfigLoader | None = None,
    ) -> None:
        """Index skills for semantic matching.

        Args:
            skills: List of skill definitions
            config_loader: Optional config loader for skill content
        """
        self._config_loader = config_loader
        self._documents.clear()

        # Build documents from skills
        for skill in skills:
            # Use intent as primary text
            intent = skill.get("intent", "")
            skill_id = skill.get("id", "")

            # Also add keywords from skill_id
            text = f"{intent} {skill_id}"

            tokens = self._tokenize(text)

            doc = Document(
                text=text,
                tokens=tokens,
                metadata={
                    "skill_id": skill_id,
                    "namespace": skill.get("namespace"),
                    "priority": skill.get("priority"),
                },
            )
            self._documents.append(doc)

        # Calculate IDF
        self._calculate_idf()

    def match(
        self,
        query: str,
        top_k: int = 3,
    ) -> list[SemanticMatch]:
        """Find matching skills for a query.

        Args:
            query: User query string
            top_k: Number of top results to return

        Returns:
            List of semantic matches, sorted by score descending
        """
        if not self._documents:
            return []

        # Tokenize query
        query_tokens = self._tokenize(query)

        if not query_tokens:
            return []

        # Calculate TF-IDF for query
        query_tf = self._calculate_tf(query_tokens)
        query_tfidf = {term: tf * self._idf.get(term, 0) for term, tf in query_tf.items()}

        # Calculate cosine similarity with each document
        matches: list[SemanticMatch] = []
        for doc in self._documents:
            score = self._cosine_similarity(query_tfidf, doc)

            if score >= self.min_score:
                matches.append(
                    SemanticMatch(
                        skill_id=doc.metadata["skill_id"],
                        score=score,
                        metadata=doc.metadata,
                    )
                )

        # Sort by score descending
        matches.sort(key=lambda m: m.score, reverse=True)

        return matches[:top_k]

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text into terms.

        Args:
            text: Input text

        Returns:
            List of filtered tokens
        """
        # Convert to lowercase
        text = text.lower()

        # Remove punctuation
        text = re.sub(r"[^\w\s]", " ", text)

        # Split into words
        tokens = text.split()

        # Filter stop words and short tokens
        filtered = [token for token in tokens if token not in STOP_WORDS and len(token) > 1]

        return filtered

    def _calculate_tf(self, tokens: list[str]) -> dict[str, float]:
        """Calculate term frequency.

        Args:
            tokens: List of tokens

        Returns:
            Dictionary mapping term to TF value
        """
        if not tokens:
            return {}

        # Count term frequencies
        counts = Counter(tokens)

        # Normalize by max count (TF normalization)
        max_count = max(counts.values())

        return {term: count / max_count for term, count in counts.items()}

    def _calculate_idf(self) -> None:
        """Calculate inverse document frequency for all terms."""
        if not self._documents:
            self._idf = {}
            return

        # Count documents containing each term
        doc_counts: dict[str, int] = {}
        total_docs = len(self._documents)

        for doc in self._documents:
            unique_terms = set(doc.tokens)
            for term in unique_terms:
                doc_counts[term] = doc_counts.get(term, 0) + 1

        # Calculate IDF: log(total_docs / doc_count)
        self._idf = {term: math.log(total_docs / count) for term, count in doc_counts.items()}

    def _cosine_similarity(
        self,
        query_tfidf: dict[str, float],
        doc: Document,
    ) -> float:
        """Calculate cosine similarity between query and document.

        Args:
            query_tfidf: Query TF-IDF vector
            doc: Document to compare

        Returns:
            Similarity score (0.0 to 1.0)
        """
        # Calculate document TF-IDF
        doc_tf = self._calculate_tf(doc.tokens)
        doc_tfidf = {term: tf * self._idf.get(term, 0) for term, tf in doc_tf.items()}

        # Get all unique terms
        all_terms = set(query_tfidf.keys()) | set(doc_tfidf.keys())

        if not all_terms:
            return 0.0

        # Calculate dot product and magnitudes
        dot_product = sum(query_tfidf.get(term, 0) * doc_tfidf.get(term, 0) for term in all_terms)

        query_magnitude = math.sqrt(sum(v * v for v in query_tfidf.values()))
        doc_magnitude = math.sqrt(sum(v * v for v in doc_tfidf.values()))

        # Avoid division by zero
        if query_magnitude == 0 or doc_magnitude == 0:
            return 0.0

        return dot_product / (query_magnitude * doc_magnitude)

    def get_term_importance(
        self,
        term: str,
    ) -> float:
        """Get IDF score for a term (indicates importance).

        Args:
            term: Term to check

        Returns:
            IDF score (higher = more important/rare)
        """
        return self._idf.get(term.lower(), 0.0)
