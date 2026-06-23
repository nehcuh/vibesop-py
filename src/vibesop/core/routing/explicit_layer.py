"""Explicit override layer — user-specified skill routing.

Layer 0: If the user explicitly specifies a skill (via !skill prefix,
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

# Pattern: verb followed by skill identifier (may include namespace:skill or prefix:id)
EXPLICIT_VERB_PATTERN = re.compile(r"(?:use|run|execute|try)\s+([\w\-/:]+)", re.IGNORECASE)

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
    # Priority 0: /skill_name (slash command — exact skill invocation).
    # This is the highest-priority match: the user typed the exact skill name.
    stripped = query.strip()
    if stripped.startswith("/"):
        slash_name = stripped[1:].split()[0] if len(stripped) > 1 else ""
        remainder = stripped[len(slash_name) + 1:].strip() if slash_name else ""
        if slash_name:
            # Exact ID match (e.g., /builtin/skill-name)
            for c in candidates:
                if c.get("id") == slash_name:
                    return slash_name, remainder
            # Namespace suffix match (e.g., /skill-name → builtin/skill-name)
            for c in candidates:
                cid = c.get("id", "")
                if cid.endswith(f"/{slash_name}") or cid.endswith(f"-{slash_name}"):
                    return cid, remainder

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
        # If the captured text contains a colon, try the part after colon
        # (e.g., "use skill:systematic-debugging" → "systematic-debugging")
        if ":" in skill_id:
            after_colon = skill_id.split(":", 1)[1]
            if _is_valid_skill(after_colon, candidates):
                return after_colon, query

    return None, None


def _is_valid_skill(skill_id: str, candidates: list[dict[str, Any]]) -> bool:
    """Check if skill_id exists in candidates."""
    return any(candidate.get("id") == skill_id for candidate in candidates)
