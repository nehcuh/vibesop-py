"""Task ID derivation — deterministic, query-only anchor.

Replaces contextvars-based ``bind_task_context`` propagation for the route
path. The original approach failed in two ways (see
``project-task-id-bug-and-cross-project`` memory):

1. ``cli/main.py:724`` never passed ``task_id`` to ``tracer.trace(...)``
2. ``contextvars`` does not cross process boundaries, so sub-agent CLIs
   (Claude Code / Kimi / Pi) cannot inherit the parent's bind

The fix: derive ``task_id`` deterministically from the query itself. Both
parent and child processes can compute the same value independently — no
propagation needed.

Design contract (v3, post grok+pi review):
- ``task_id = sha1(normalize(query))[:16]`` — pure query derivation
- ``project_path`` is NOT in the hash (would break cross-project cluster,
  per v2 review)
- ``normalize`` rules are FROZEN — any change must pass the fixture
  ``tests/fixtures/task_id_normalize.jsonl``

What normalize handles:
- Trim + collapse internal whitespace
- Lowercase (Unicode-aware via ``str.casefold()``)
- NFKC unicode normalization (fullwidth → halfwidth, ligatures → decomposed)
- Strip ASCII + CJK punctuation
- Strip simple XML-like wrapper tags (``<user_query>...</user_query>``)

What normalize does NOT handle (intentionally):
- Traditional ↔ Simplified Chinese (would require ``opencc`` heavy dep)
- Semantic synonyms (``截图`` vs ``截屏``) — that's embedding's job, W1
- Project-specific tags beyond simple XML stripping
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from functools import lru_cache

__all__ = ["derive_task_id", "normalize_query"]

# Simple XML-like wrapper tags: <tag>...</tag> or <tag attr="x">...</tag>
# Matches when the ENTIRE string (after trim) is wrapped — doesn't strip
# inline tags mid-string (preserves content like "see <b>note</b>").
_XML_WRAPPER_RE = re.compile(
    r"^\s*<[a-zA-Z_][\w\-]*(?:\s[^>]*)?>(.*?)</[a-zA-Z_][\w\-]*>\s*$",
    re.DOTALL,
)

# Strip anything that's NOT: word char (letter/digit/underscore, incl CJK),
# whitespace, or hyphen. CJK punctuation (「」、。) is non-word → stripped.
# Unicode-aware: \w matches CJK chars in Python's default re engine.
_KEEP_RE = re.compile(r"[^\w\s-]", re.UNICODE)


def normalize_query(query: str) -> str:
    """Normalize a query string for task_id derivation.

    Frozen rules — any change here requires updating
    ``tests/fixtures/task_id_normalize.jsonl``.

    Args:
        query: Raw user query (possibly with XML wrapper, mixed case,
            fullwidth chars, punctuation, irregular whitespace).

    Returns:
        Normalized form. Empty string if query is empty or normalizes
        to empty (e.g. only whitespace + punctuation).
    """
    if not query:
        return ""

    # 1. NFKC: fullwidth → halfwidth, ligatures → decomposed
    s = unicodedata.normalize("NFKC", query)

    # 2. Strip XML wrapper if entire string is wrapped
    m = _XML_WRAPPER_RE.match(s)
    if m:
        s = m.group(1)

    # 3. Casefold (more aggressive than lowercase for non-ASCII, e.g. ß → ss)
    s = s.casefold()

    # 4. Strip non-word, non-whitespace, non-hyphen chars (punctuation, symbols)
    s = _KEEP_RE.sub(" ", s)

    # 5. Collapse whitespace
    s = " ".join(s.split())

    return s


@lru_cache(maxsize=4096)
def derive_task_id(query: str) -> str | None:
    """Derive a deterministic task_id from a query.

    Same query → same task_id, across processes and projects.
    Returns ``None`` if query normalizes to empty (cannot derive meaningful
    task_id).

    Args:
        query: Raw user query.

    Returns:
        16-character hex string (64 bits entropy), or ``None``.
    """
    normalized = normalize_query(query)
    if not normalized:
        return None
    h = hashlib.sha1(normalized.encode("utf-8")).hexdigest()
    return h[:16]
