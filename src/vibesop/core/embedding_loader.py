"""Shared SentenceTransformer loader — offline-first with explicit online retry.

gate40 主项 (r2.2 §1): hook cold-start paid 13-30s per prompt because every
``SentenceTransformer(...)`` load went online (HF Hub HEAD requests). All six
load sites route through :func:`load_sentence_transformer`: try
``local_files_only=True`` first (cache hit → no network), and on any
cache-miss-class failure retry exactly once online (first download, or
completion of a broken/partial cache — no silent downgrade).

Exception taxonomy (pinned by gate40 §1.2):

- ``ImportError`` / ``KeyboardInterrupt`` / ``SystemExit`` / ``MemoryError``
  from the offline attempt are re-raised WITHOUT retry. They are not
  cache-miss signals, and retrying would turn a millisecond fail-open into
  a 13-30s online wait (the Grok hook's 10s timeout would kill the process
  before fail-open even ran).
- Any other ``Exception`` from the offline attempt triggers one online
  retry; if the retry also raises, that exception propagates AS-IS — no
  new wrapper type — so each call site's existing ``except`` shape keeps
  its exact semantics.

The helper is stateless: every call is independent. Per-site sticky-failure
semantics (e.g. ``EmbeddingRecall._model_failed``) stay with the call sites.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["load_sentence_transformer"]


def load_sentence_transformer(model_name: str) -> Any:
    """Load a SentenceTransformer offline-first, with one explicit online retry.

    Raises whatever the underlying load raises (see module docstring for the
    retry taxonomy); the caller's existing fail-open handling applies.
    """
    from sentence_transformers import (
        SentenceTransformer,  # pyright: ignore[reportMissingImports]
    )

    try:
        model = SentenceTransformer(model_name, local_files_only=True)
    except (ImportError, KeyboardInterrupt, SystemExit, MemoryError):
        raise  # not a cache-miss class — never retry online
    except Exception:
        logger.debug(
            "offline load of %r failed; retrying online (first download or broken cache)",
            model_name,
        )
        model = SentenceTransformer(model_name)  # second failure re-raises as-is
        logger.debug("online retry of %r succeeded", model_name)
    else:
        logger.debug("loaded %r from local cache (local_files_only=True)", model_name)
    return model
