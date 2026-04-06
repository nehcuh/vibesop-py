"""Unified TF-IDF calculation for VibeSOP matching system.

This module consolidates TF-IDF logic from:
- triggers/utils.py (calculate_tf, calculate_idf, calculate_tfidf)
- core/routing/semantic.py (_calculate_tf, _calculate_idf)

The goal is to have ONE canonical TF-IDF calculator.
"""

import math
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class TFIDFVector:
    """TF-IDF vector representation.

    This is the unified representation for TF-IDF vectors across
    the entire matching system, replacing multiple incompatible formats.

    Attributes:
        tf: Term frequency dictionary
        idf: Inverse document frequency dictionary
        tfidf: Pre-computed TF-IDF scores
        magnitude: Vector magnitude (for cosine similarity)
    """

    tf: dict[str, float] = field(default_factory=dict)
    idf: dict[str, float] = field(default_factory=dict)
    tfidf: dict[str, float] = field(default_factory=dict)
    magnitude: float = 0.0

    def to_dict(self) -> dict[str, float]:
        """Return TF-IDF dictionary."""
        return self.tfidf.copy()

    def normalize(self) -> None:
        """Normalize the vector and update magnitude."""
        if not self.tfidf:
            self.magnitude = 0.0
            return

        # Calculate magnitude
        self.magnitude = math.sqrt(sum(v**2 for v in self.tfidf.values()))

        # Normalize
        if self.magnitude > 0:
            self.tfidf = {k: v / self.magnitude for k, v in self.tfidf.items()}

    def dot_product(self, other: "TFIDFVector") -> float:
        """Calculate dot product with another vector."""
        all_terms = set(self.tfidf.keys()) | set(other.tfidf.keys())
        return sum(self.tfidf.get(term, 0) * other.tfidf.get(term, 0) for term in all_terms)


class ITFIDFCalculator(Protocol):
    """Protocol for TF-IDF calculators."""

    def fit(self, documents: list[list[str]]) -> "ITFIDFCalculator":
        """Fit IDF calculator on documents.

        Args:
            documents: List of tokenized documents

        Returns:
            Self for method chaining
        """
        ...

    def transform(self, tokens: list[str]) -> TFIDFVector:
        """Transform tokens to TF-IDF vector.

        Args:
            tokens: Tokenized document

        Returns:
            TF-IDF vector
        """
        ...

    def fit_transform(self, documents: list[list[str]]) -> list[TFIDFVector]:
        """Fit on documents and transform them.

        Args:
            documents: List of tokenized documents

        Returns:
            List of TF-IDF vectors, one per document
        """
        ...

    def get_idf(self, term: str) -> float:
        """Get IDF score for a term."""
        ...

    def get_vocabulary(self) -> list[str]:
        """Get all known terms."""
        ...


class TFIDFCalculator:
    """Unified TF-IDF calculator for skill matching.

    This consolidates TF-IDF logic from:
    - triggers/utils.py: calculate_tf, calculate_idf, calculate_tfidf
    - core/routing/semantic.py: _calculate_tf, _calculate_idf

    The calculator follows scikit-learn's fit/transform pattern.

    Example:
        >>> calc = TFIDFCalculator()
        >>> calc.fit([["hello", "world"], ["hello", "test"]])
        >>> vec = calc.transform(["hello", "world"])
        >>> vec.tfidf["hello"]
        0.5
    """

    def __init__(self, smooth: float = 1.0):
        """Initialize TF-IDF calculator.

        Args:
            smooth: Smoothing parameter to avoid division by zero
        """
        self._smooth = smooth
        self._idf: dict[str, float] = {}
        self._doc_count: int = 0
        self._term_doc_count: Counter[str] = Counter()

    def fit(self, documents: list[list[str]]) -> "TFIDFCalculator":
        """Fit the calculator on a corpus of documents.

        Args:
            documents: List of tokenized documents

        Returns:
            Self for method chaining
        """
        self._doc_count = len(documents)
        self._term_doc_count.clear()

        # Count documents containing each term
        for doc in documents:
            unique_terms = set(doc)
            for term in unique_terms:
                self._term_doc_count[term] += 1

        # Calculate IDF: log((N + smooth) / (df + smooth)) + 1
        # Add 1 to ensure non-negative
        for term, doc_count in self._term_doc_count.items():
            self._idf[term] = (
                math.log((self._doc_count + self._smooth) / (doc_count + self._smooth)) + 1
            )

        return self

    def transform(self, tokens: list[str]) -> TFIDFVector:
        """Transform a tokenized document into TF-IDF vector.

        Args:
            tokens: Tokenized document

        Returns:
            TF-IDF vector
        """
        # Calculate TF
        total = len(tokens)
        counts = Counter(tokens)
        tf = {term: count / total for term, count in counts.items()}

        # Calculate TF-IDF
        tfidf = {}
        for term, tf_score in tf.items():
            idf_score = self._idf.get(term, 1.0)
            tfidf[term] = tf_score * idf_score

        # Calculate magnitude
        magnitude = math.sqrt(sum(v**2 for v in tfidf.values()))

        return TFIDFVector(tf=tf, idf=self._idf.copy(), tfidf=tfidf, magnitude=magnitude)

    def fit_transform(self, documents: list[list[str]]) -> list[TFIDFVector]:
        """Fit on documents and transform them.

        Args:
            documents: List of tokenized documents

        Returns:
            List of TFIDF vectors, one per document
        """
        self.fit(documents)
        return [self.transform(doc) for doc in documents]

    def get_idf(self, term: str) -> float:
        """Get IDF score for a term.

        Args:
            term: Term to look up

        Returns:
            IDF score, or 1.0 if term not in vocabulary
        """
        return self._idf.get(term, 1.0)

    def get_vocabulary(self) -> list[str]:
        """Get all known terms (terms with IDF scores).

        Returns:
            Sorted list of terms
        """
        return sorted(self._idf.keys())

    def get_doc_frequency(self, term: str) -> int:
        """Get document frequency for a term.

        Args:
            term: Term to look up

        Returns:
            Number of documents containing the term
        """
        return self._term_doc_count.get(term, 0)

    def save(self, path: str) -> None:
        """Save IDF dictionary to file.

        Args:
            path: Path to save the IDF dictionary (JSON format)
        """
        import json

        with Path(path).open("w") as f:
            json.dump(
                {
                    "idf": self._idf,
                    "doc_count": self._doc_count,
                    "term_doc_count": dict(self._term_doc_count),
                },
                f,
            )

    @classmethod
    def load(cls, path: str) -> "TFIDFCalculator":
        """Load IDF dictionary from file.

        Args:
            path: Path to load the IDF dictionary from (JSON format)

        Returns:
            Loaded TFIDFCalculator
        """
        import json

        with Path(path).open() as f:
            data = json.load(f)

        calc = cls()
        calc._idf = data.get("idf", {})
        calc._doc_count = data.get("doc_count", 0)
        calc._term_doc_count = Counter(data.get("term_doc_count", {}))

        return calc


# Convenience functions for backward compatibility


def calculate_tf(tokens: list[str]) -> dict[str, float]:
    """Calculate term frequency (TF) for tokens.

    Legacy function from triggers/utils.py. Use TFIDFCalculator for new code.

    Args:
        tokens: List of tokens

    Returns:
        Dictionary mapping term to TF score
    """
    if not tokens:
        return {}

    total = len(tokens)
    counts = Counter(tokens)

    return {term: count / total for term, count in counts.items()}


def calculate_idf(documents: list[list[str]]) -> dict[str, float]:
    """Calculate inverse document frequency (IDF) for terms.

    Legacy function from triggers/utils.py. Use TFIDFCalculator for new code.

    Args:
        documents: List of tokenized documents

    Returns:
        Dictionary mapping term to IDF score
    """
    if not documents:
        return {}

    total_docs = len(documents)
    term_doc_count: Counter[str] = Counter()

    # Count documents containing each term
    for doc in documents:
        unique_terms: set[str] = set(doc)
        for term in unique_terms:
            term_doc_count[term] += 1

    # Calculate IDF: log(total_docs / doc_count) + 1
    idf: dict[str, float] = {}
    for term, doc_count in term_doc_count.items():
        idf[term] = math.log(total_docs / (doc_count + 1)) + 1

    return idf


def calculate_tfidf(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    """Calculate TF-IDF vector for tokens.

    Legacy function from triggers/utils.py. Use TFIDFCalculator for new code.

    Args:
        tokens: Tokenized document
        idf: Pre-calculated IDF scores

    Returns:
        Dictionary mapping term to TF-IDF score
    """
    tf = calculate_tf(tokens)

    tfidf: dict[str, float] = {}
    for term, tf_score in tf.items():
        idf_score = idf.get(term, 1.0)
        tfidf[term] = tf_score * idf_score

    return tfidf


# Convenience exports
__all__ = [
    "ITFIDFCalculator",
    "TFIDFCalculator",
    "TFIDFVector",
    "calculate_idf",
    "calculate_tf",
    "calculate_tfidf",
]
