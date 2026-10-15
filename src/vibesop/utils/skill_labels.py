"""Identifier rendering shared across injection surfaces."""

from __future__ import annotations

import re

__all__ = ["sanitize_skill_label"]

_SAFE_LABEL = re.compile(r"[^\w.\-/]")


def sanitize_skill_label(skill_id: str) -> str:
    """Neutralize control/quote characters in rendered skill identifiers.

    Frontmatter ``id`` values are pack-controlled and only length-validated
    upstream; they are interpolated into mandatory, never-truncated
    directive text (envelope headers, banners, XML attributes, notices).
    A newline or quote there can fabricate instructions or break out of
    markup. Legitimate ids — word characters (including CJK), dots,
    slashes, hyphens — pass through unchanged; anything else collapses
    to ``_``.
    """
    return _SAFE_LABEL.sub("_", skill_id)
