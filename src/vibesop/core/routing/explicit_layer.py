"""Explicit override layer — user-specified skill routing.

Layer 1: If the user explicitly specifies a skill (via !skill prefix,
or by skill_id in the query), route directly to it without matching.

Examples:
    "!systematic-debugging help me" → systematic-debugging
    "use omx/ralph to implement this" → omx/ralph
    "run ralph" → omx/ralph
"""

from __future__ import annotations

import re
from typing import Any

# Pattern: !skill_id at the start of query
EXPLICIT_PREFIX_PATTERN = re.compile(r"^!(\S+)\s+(.*)")

# Pattern: verb followed by skill identifier
EXPLICIT_VERB_PATTERN = re.compile(r"(?:use|run|execute|try)\s+([\w\-/]+)", re.IGNORECASE)

# Pattern: skill_id anywhere in query (must look like a valid skill ID)
SKILL_ID_PATTERN = re.compile(r"\b([\w\-]+/[\w\-]+|[\w\-]{3,})\b")


def check_explicit_override(
    query: str,
    candidates: list[dict[str, Any]],
) -> tuple[str | None, str | None]:
    """Check if query contains an explicit skill override.

    Args:
        query: User's query
        candidates: Available skill candidates

    Returns:
        Tuple of (skill_id, cleaned_query) or (None, None) if no override.
    """
    # Priority 1: !skill_id prefix
    match = EXPLICIT_PREFIX_PATTERN.match(query)
    if match:
        skill_id = match.group(1)
        cleaned_query = match.group(2).strip()
        if _is_valid_skill(skill_id, candidates):
            return skill_id, cleaned_query

    # Priority 2: "use/run/execute <skill_id>"
    match = EXPLICIT_VERB_PATTERN.search(query)
    if match:
        skill_id = match.group(1)
        if _is_valid_skill(skill_id, candidates):
            return skill_id, query

    return None, None


def _is_valid_skill(skill_id: str, candidates: list[dict[str, Any]]) -> bool:
    """Check if skill_id exists in candidates."""
    return any(candidate.get("id") == skill_id for candidate in candidates)
