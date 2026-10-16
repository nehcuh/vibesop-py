"""Identifier rendering shared across injection surfaces."""

from __future__ import annotations

import re

__all__ = ["contains_glob_metachar", "sanitize_skill_label"]

_SAFE_LABEL = re.compile(r"[^\w.\-/]")
_GLOB_META_CHARS = "*?["


def contains_glob_metachar(skill_id: str) -> bool:
    """True when the id would act as a wildcard inside a walk glob.

    Pack-controlled ids are interpolated into path-walk globs
    (``*-{id}``, ``**/{id}.skill/...``). On 3.13+ a ``**`` fragment acts
    as a cross-separator wildcard that matches an UNRELATED skill
    (executed repro); a single ``*``/``?``/``[`` wildcard-matches on every
    version; pre-3.13 pathlib raised ValueError for non-component ``**``
    instead. Callers must refuse glob lookups for such ids — the skills
    demote to the no-content notice rather than inject the wrong skill.
    """
    return any(ch in skill_id for ch in _GLOB_META_CHARS)


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
