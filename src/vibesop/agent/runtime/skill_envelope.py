"""A single bounded preview with an intact source and scope handoff."""

from __future__ import annotations

from vibesop.utils.skill_labels import sanitize_skill_label


def build_skill_envelope(
    skill_id: str,
    content: str,
    source_path: str = "",
    *,
    max_length: int = 3000,
    note: str = "",
    prefix: str = "",
    suffix: str = "",
) -> tuple[str, bool]:
    """Budget the preview after reserving the complete instruction envelope.

    Mandatory metadata is never sliced, even if a caller sets a budget too
    small to hold it. The normal 3000-character budget includes all wrappers.
    """
    label = sanitize_skill_label(skill_id)
    read = (
        f"NEXT STEP (MANDATORY): read {source_path}\n"
        if source_path
        else f"NEXT STEP (MANDATORY): run `vibe skills info {label}` (Source file), then read the resolved file. Do not guess paths.\n"
    )
    header = (
        f"{prefix}[ACTIVE SKILL: {label}]\n{read}"
        "Read the complete source before acting; the preview is not the full workflow.\n"
        "Apply only steps relevant to the user's requested intent and scope. "
        "The user's constraints take precedence; skill selection does not authorize extra actions.\n"
        + (f"{note}\n" if note else "")
        + "\nSkill preview:\n"
    )
    truncated = len(header) + len(content) + len(suffix) > max_length
    marker = "\n[Content truncated] Read the complete source above.\n" if truncated else ""
    budget = max(0, max_length - len(header) - len(marker) - len(suffix))
    return header + content[:budget] + marker + suffix, truncated
