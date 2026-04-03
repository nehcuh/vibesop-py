"""Utility functions for keyword detection and scoring.

This module provides helper functions for:
- Text tokenization
- TF-IDF calculation
- Cosine similarity
- Multi-strategy score combination
"""

import re
import math
from collections import Counter


def tokenize(text: str) -> list[str]:
    """Tokenize text into words.

    Handles:
    - Lowercase conversion
    - Punctuation removal
    - Whitespace splitting
    - Multi-language support (basic)
    - Chinese character splitting

    Args:
        text: Input text to tokenize

    Returns:
        List of tokens

    Example:
        >>> tokenize("Hello, World!")
        ["hello", "world"]
        >>> tokenize("扫描安全漏洞")
        ["扫描", "安全", "漏洞"]
    """
    if not text:
        return []

    # Convert to lowercase
    text = text.lower()

    # Remove punctuation but preserve word characters
    # This works for both Latin and CJK characters
    text = re.sub(r'[^\w\s\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]', ' ', text)

    tokens = []

    # Split into segments
    segments = text.split()

    for segment in segments:
        # Check if segment contains CJK characters
        if re.search(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]', segment):
            # Split CJK text into individual characters/words
            # For Chinese, each character or pair of characters can be a word
            i = 0
            while i < len(segment):
                # Check for 2-character words (common in Chinese)
                if i + 1 < len(segment):
                    two_char = segment[i:i+2]
                    # If both are CJK characters, keep as 2-char token
                    if re.match(r'[\u4e00-\u9fff]{2}', two_char):
                        tokens.append(two_char)
                        i += 2
                        continue

                # Single character token
                tokens.append(segment[i])
                i += 1
        else:
            # Non-CJK text: keep as is
            tokens.append(segment)

    return tokens


def calculate_tf(tokens: list[str]) -> dict[str, float]:
    """Calculate term frequency (TF) for tokens.

    TF measures how frequently a term appears in a document.

    Args:
        tokens: List of tokens

    Returns:
        Dictionary mapping term to TF score

    Example:
        >>> calculate_tf(["hello", "world", "hello"])
        {"hello": 0.667, "world": 0.333}
    """
    if not tokens:
        return {}

    total = len(tokens)
    counts = Counter(tokens)

    return {term: count / total for term, count in counts.items()}


def calculate_idf(documents: list[list[str]]) -> dict[str, float]:
    """Calculate inverse document frequency (IDF) for terms.

    IDF measures how important a term is across all documents.
    Rare terms get higher IDF scores.

    Args:
        documents: List of tokenized documents

    Returns:
        Dictionary mapping term to IDF score

    Example:
        >>> docs = [["hello", "world"], ["hello", "test"]]
        >>> calculate_idf(docs)
        {"hello": 0.0, "world": 0.693, "test": 0.693}
    """
    if not documents:
        return {}

    total_docs = len(documents)
    term_doc_count = Counter()

    # Count documents containing each term
    for doc in documents:
        unique_terms = set(doc)
        for term in unique_terms:
            term_doc_count[term] += 1

    # Calculate IDF: log(total_docs / doc_count)
    idf = {}
    for term, doc_count in term_doc_count.items():
        # Add 1 to avoid division by zero
        idf[term] = math.log(total_docs / (doc_count + 1)) + 1

    return idf


def calculate_tfidf(
    tokens: list[str],
    idf: dict[str, float]
) -> dict[str, float]:
    """Calculate TF-IDF vector for tokens.

    TF-IDF combines term frequency (TF) and inverse document frequency (IDF)
    to measure term importance in a document.

    Args:
        tokens: Tokenized document
        idf: Pre-calculated IDF scores

    Returns:
        Dictionary mapping term to TF-IDF score

    Example:
        >>> tokens = ["hello", "world"]
        >>> idf = {"hello": 1.0, "world": 2.0}
        >>> calculate_tfidf(tokens, idf)
        {"hello": 0.5, "world": 1.0}
    """
    tf = calculate_tf(tokens)

    tfidf = {}
    for term, tf_score in tf.items():
        idf_score = idf.get(term, 1.0)
        tfidf[term] = tf_score * idf_score

    return tfidf


def cosine_similarity(
    vec1: dict[str, float],
    vec2: dict[str, float]
) -> float:
    """Calculate cosine similarity between two vectors.

    Returns:
        Similarity score between 0.0 and 1.0

    Example:
        >>> vec1 = {"hello": 1.0, "world": 0.5}
        >>> vec2 = {"hello": 0.5, "world": 1.0}
        >>> cosine_similarity(vec1, vec2)
        0.8
    """
    if not vec1 or not vec2:
        return 0.0

    # Get all unique terms
    all_terms = set(vec1.keys()) | set(vec2.keys())

    # Calculate dot product
    dot_product = sum(
        vec1.get(term, 0) * vec2.get(term, 0)
        for term in all_terms
    )

    # Calculate magnitudes
    mag1 = math.sqrt(sum(v ** 2 for v in vec1.values()))
    mag2 = math.sqrt(sum(v ** 2 for v in vec2.values()))

    if mag1 == 0 or mag2 == 0:
        return 0.0

    return dot_product / (mag1 * mag2)


def calculate_keyword_match_score(
    query: str,
    keywords: list[str]
) -> float:
    """Calculate keyword matching score.

    Score is based on how many keywords appear in the query.
    Case-insensitive matching.

    Args:
        query: User input query
        keywords: List of keywords to match

    Returns:
        Score between 0.0 and 1.0

    Example:
        >>> calculate_keyword_match_score("scan security", ["scan", "security"])
        1.0
        >>> calculate_keyword_match_score("scan code", ["scan", "security"])
        0.5
    """
    if not keywords:
        return 0.0

    query_lower = query.lower()
    matched = sum(1 for kw in keywords if kw.lower() in query_lower)

    return matched / len(keywords)


def calculate_regex_match_score(
    query: str,
    patterns: list[str]
) -> float:
    """Calculate regex pattern matching score.

    Score is based on how many patterns match the query.

    Args:
        query: User input query
        patterns: List of regex patterns

    Returns:
        Score between 0.0 and 1.0

    Example:
        >>> calculate_regex_match_score("scan security", [r"scan.*security"])
        1.0
        >>> calculate_regex_match_score("scan code", [r"scan.*security"])
        0.0
    """
    if not patterns:
        return 0.0

    matched = sum(
        1 for pattern in patterns
        if re.search(pattern, query, re.IGNORECASE)
    )

    return matched / len(patterns)


def calculate_combined_score(
    keyword_score: float,
    regex_score: float,
    semantic_score: float,
    weights: tuple[float, float, float] = (0.4, 0.3, 0.3)
) -> float:
    """Calculate combined confidence score from multiple strategies.

    Default weights: keywords (40%), regex (30%), semantic (30%)

    Args:
        keyword_score: Keyword matching score (0.0 - 1.0)
        regex_score: Regex matching score (0.0 - 1.0)
        semantic_score: Semantic similarity score (0.0 - 1.0)
        weights: Optional custom weights (must sum to 1.0)

    Returns:
        Combined score between 0.0 and 1.0

    Example:
        >>> calculate_combined_score(1.0, 0.5, 0.8)
        0.79
    """
    # Validate weights sum to 1.0
    if abs(sum(weights) - 1.0) > 0.01:
        raise ValueError(f"Weights must sum to 1.0, got {sum(weights)}")

    combined = (
        keyword_score * weights[0] +
        regex_score * weights[1] +
        semantic_score * weights[2]
    )

    return min(max(combined, 0.0), 1.0)
