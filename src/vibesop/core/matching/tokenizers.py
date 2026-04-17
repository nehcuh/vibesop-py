"""Unified text tokenization for VibeSOP matching system.

This module consolidates tokenization logic from:
- triggers/utils.py (CJK-aware, multi-language)
- core/routing/semantic.py (stopword filtering)

The goal is to have ONE canonical tokenizer that serves all matchers.
"""

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol


class TokenizerMode(StrEnum):
    """Tokenization modes."""

    SIMPLE = "simple"  # Basic whitespace splitting
    CLEAN = "clean"  # Remove punctuation and stop words
    CJK = "cjk"  # CJK-aware (Chinese, Japanese, Korean)
    AGGRESSIVE = "aggressive"  # Split all characters


# Default stop words (English)
DEFAULT_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "he",
    "in",
    "is",
    "it",
    "its",
    "of",
    "on",
    "that",
    "the",
    "to",
    "was",
    "will",
    "with",
    "this",
    "but",
    "they",
    "have",
    # Common programming stop words
    "use",
    "can",
    "get",
    "make",
    "go",
    "do",
}


@dataclass
class TokenizerConfig:
    """Configuration for tokenization behavior."""

    mode: TokenizerMode = TokenizerMode.CJK
    lowercase: bool = True
    remove_punctuation: bool = True
    min_token_length: int = 1
    stop_words: set[str] = field(default_factory=DEFAULT_STOP_WORDS.copy)
    split_cjk: bool = True
    preserve_case: bool = False


class Tokenizer(Protocol):
    """Protocol for tokenizers."""

    def tokenize(self, text: str) -> list[str]:
        """Tokenize text into tokens."""
        ...

    def get_config(self) -> TokenizerConfig:
        """Get tokenizer configuration."""
        ...


def tokenize(
    text: str,
    config: TokenizerConfig | None = None,
) -> list[str]:
    """Tokenize text according to configuration.

    This is the main entry point for tokenization. It handles:
    - Lowercase conversion (optional)
    - Punctuation removal
    - Multi-language support (English, Chinese, Japanese, Korean)
    - CJK character splitting

    Args:
        text: Input text to tokenize
        config: Tokenization configuration (uses default if None)

    Returns:
        List of tokens

    Examples:
        >>> tokenize("Hello, World!")
        ["hello", "world"]
        >>> tokenize("扫描安全漏洞")
        ["扫描", "安全", "漏洞"]
        >>> tokenize("test code", config=TokenizerConfig(mode=TokenizerMode.AGGRESSIVE))
        ["t", "e", "s", "t", "c", "o", "d", "e"]
    """
    if not text:
        return []

    config = config or TokenizerConfig()

    # Apply lowercase
    if config.lowercase:
        text = text.lower()

    # Remove punctuation (preserve word characters and CJK)
    if config.remove_punctuation:
        # Keep word characters, whitespace, and CJK characters
        text = re.sub(r"[^\w\s\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]", " ", text)

    tokens: list[str] = []

    # Split into segments
    segments = text.split()

    for segment in segments:
        # Filter by minimum length
        if len(segment) < config.min_token_length:
            continue

        # Handle CJK text
        if (config.mode == TokenizerMode.CJK or config.split_cjk) and _contains_cjk(segment):
            tokens.extend(_tokenize_cjk(segment, config))
            continue

        # Non-CJK or simple mode
        tokens.append(segment)

    # Filter stop words (only for CLEAN mode)
    if config.mode == TokenizerMode.CLEAN:
        tokens = [t for t in tokens if t not in config.stop_words]

    return tokens


def _contains_cjk(text: str) -> bool:
    """Check if text contains CJK characters."""
    return bool(re.search(r"[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]", text))


def _tokenize_cjk(segment: str, _config: TokenizerConfig) -> list[str]:
    """Tokenize CJK text with overlapping 2-character tokens.

    Emits overlapping 2-character tokens so that 3-character segments
    like "做实验" produce "做实", "实验", "验" instead of missing the
    meaningful word "实验".

    Args:
        segment: Text segment containing CJK characters
        config: Tokenization configuration

    Returns:
        List of CJK tokens
    """
    tokens: list[str] = []
    i = 0

    while i < len(segment):
        # Try 2-character token first (common in Chinese)
        if i + 1 < len(segment):
            two_char = segment[i : i + 2]
            if re.match(r"[\u4e00-\u9fff]{2}", two_char):
                tokens.append(two_char)
                # For CJK, advance by 1 instead of 2 to capture overlapping
                # 2-character words (e.g., "做实验" -> "做实", "实验")
                i += 1
                continue

        # Single character token
        tokens.append(segment[i])
        i += 1

    return tokens


class CachedTokenizer:
    """Tokenizer with caching for frequently seen texts.

    This is useful for routing scenarios where the same queries
    are processed repeatedly.

    Example:
        >>> tokenizer = CachedTokenizer()
        >>> tokens1 = tokenizer.tokenize("Hello World")
        >>> tokens2 = tokenizer.tokenize("Hello World")  # Returns cached result
        >>> tokens1 == tokens2
        True
    """

    def __init__(self, config: TokenizerConfig | None = None):
        self._config = config or TokenizerConfig()
        self._cache: dict[str, list[str]] = {}

    def tokenize(self, text: str) -> list[str]:
        """Tokenize text with caching."""
        if text not in self._cache:
            self._cache[text] = tokenize(text, self._config)
        return self._cache[text]

    def clear_cache(self) -> None:
        """Clear the token cache."""
        self._cache.clear()

    def get_cache_size(self) -> int:
        """Get the number of cached tokenizations."""
        return len(self._cache)


# Convenience exports
__all__ = [
    "DEFAULT_STOP_WORDS",
    "CachedTokenizer",
    "TokenizerConfig",
    "TokenizerMode",
    "tokenize",
]
