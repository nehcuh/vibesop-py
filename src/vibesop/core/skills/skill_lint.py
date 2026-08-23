"""L1 minimal skill lint (gate37) — advisory-only static checks.

Three static rules (gate37 synthesis §6 修订 A), each producing one
plain-language finding line (no rule numbers, no internal jargon):

1. ``triggers:`` is present and not composed entirely of hygiene-shaped
   text (agent-prompt echoes / machine wrappers) — judged read-only via
   the frozen ``_is_agent_prompt_shape`` predicate
   (observability/skill_promote.py).
2. The body is not an unedited gate31 auto-draft skeleton — detected via
   leftover ``_render_skill_md`` TODO slots.
3. ``description`` exists and clears the same >=10-character bar as
   ``pack_installer._is_valid_skill`` (installer/pack_installer.py).

Discipline (修订 A): findings are ADVISORY ONLY. They are surfaced as
warnings and must never feed the security audit's ``is_safe``/``has_high``
fail-closed gates, never produce a score, and never block an install.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# Same hard bar as pack_installer._is_valid_skill (description >= 10 chars
# after strip) — reused, not reinvented (gate37 修订 A rule ③).
_MIN_DESCRIPTION_CHARS = 10

# gate31 skeleton literals emitted by skill_promote._render_skill_md
# (observability/skill_promote.py). The HTML comment is definitive; the
# TODO slot lines require >=2 distinct slots so a single hand-written
# TODO in an otherwise human-authored skill is NOT flagged (must-NOT-catch).
_GATE31_SKELETON_COMMENT = "<!-- gate31 skeleton"
_TODO_SLOT_MARKERS = (
    "- [ ] TODO: verifiable outcome",
    "- TODO: known failure mode",
    "- TODO: requests that resemble this pattern but differ",
    "TODO: reconstruct the procedure from",
)


def _split_frontmatter(content: str) -> tuple[dict, str]:
    """Split SKILL.md into (frontmatter dict, body). Tolerant of bad input."""
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content
    try:
        fm = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        fm = None
    return (fm if isinstance(fm, dict) else {}), parts[2]


def lint_skill(skill_md: Path) -> list[str]:
    """Lint a single SKILL.md. Returns plain-language findings ([] = clean).

    Never raises on malformed files — an unreadable/unparseable file is
    reported as findings, matching the fail-soft advisory contract.
    """
    try:
        content = skill_md.read_text(encoding="utf-8")
    except OSError as e:
        return [f"Cannot read {skill_md.name}: {e}"]

    fm, body = _split_frontmatter(content)
    findings: list[str] = []

    # Rule ③: description existence (>=10 chars, _is_valid_skill bar).
    desc = fm.get("description")
    if not isinstance(desc, str) or len(desc.strip()) < _MIN_DESCRIPTION_CHARS:
        findings.append(
            "Description is missing or too short — without at least a sentence, "
            "neither humans nor the router can tell what this skill is for."
        )

    # Rule ①: triggers present and not all hygiene-shaped.
    raw_triggers = fm.get("triggers")
    triggers = (
        [t for t in raw_triggers if isinstance(t, str) and t.strip()]
        if isinstance(raw_triggers, list)
        else []
    )
    if not triggers:
        findings.append(
            "No triggers declared — the router can never match this skill "
            "automatically; it only fires if invoked by hand."
        )
    else:
        # Lazy import: read-only call into the frozen hygiene predicate
        # (skill_promote._is_agent_prompt_shape). The predicate itself is
        # NOT modified here.
        from vibesop.core.observability.skill_promote import _is_agent_prompt_shape

        if all(_is_agent_prompt_shape(t) for t in triggers):
            findings.append(
                "Every trigger looks like a machine-generated prompt (agent "
                "echoes, system wrappers, or over-long pasted text) — these "
                "would route automated agent traffic, not real user requests. "
                "Write intent phrases a user would actually type."
            )

    # Rule ②: gate31 auto-draft skeleton residue in the body.
    if _GATE31_SKELETON_COMMENT in body or (
        sum(1 for marker in _TODO_SLOT_MARKERS if marker in body) >= 2
    ):
        findings.append(
            "The body still contains the unedited auto-draft template (TODO "
            "slots for boundaries / acceptance checks) — fill these in with "
            "real, verifiable content before relying on this skill."
        )

    return findings


def lint_skill_path(path: Path) -> list[str]:
    """Lint a skill directory (containing SKILL.md) or a SKILL.md file."""
    skill_md = path / "SKILL.md" if path.is_dir() else path
    if not skill_md.exists():
        return [f"SKILL.md not found at {skill_md}"]
    return lint_skill(skill_md)
