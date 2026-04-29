"""Lazy proxy that defers EmbeddingMatcher construction until warm-up.

EmbeddingMatcher loads a SentenceTransformer model (~100-200ms),
so deferring to warm-up keeps router initialization fast.
"""

from __future__ import annotations

import threading
from typing import Any

from vibesop.core.matching.base import IMatcher, MatcherConfig


class LazyEmbeddingMatcher:
    """Lazy proxy that defers EmbeddingMatcher construction until warm-up.

    EmbeddingMatcher loads a SentenceTransformer model (~100-200ms),
    so deferring to warm-up keeps router initialization fast.
    """

    def __init__(self, config: MatcherConfig):
        self._config = config
        self._real: IMatcher | None = None
        self._init_lock = threading.Lock()

    def _ensure_real(self) -> IMatcher:
        if self._real is None:
            with self._init_lock:
                if self._real is None:
                    from vibesop.core.matching import EmbeddingMatcher

                    self._real = EmbeddingMatcher(config=self._config)
        return self._real

    def warm_up(self, candidates: list[dict[str, Any]]) -> None:
        self._ensure_real().warm_up(candidates)

    def match(self, query: str, candidates: list[dict[str, Any]], context: Any = None) -> Any:
        return self._ensure_real().match(query, candidates, context)

    def preprocess(self, query: str) -> str:
        return self._ensure_real().preprocess(query)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._ensure_real(), name)
