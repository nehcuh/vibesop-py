"""Regression tests for the shared SKILL.md stub template.

2026-08-27 incident: a manifest stub with an empty ``trigger_when`` rendered
4 consecutive blank lines (empty "When to Use" section + skipped tags block),
which tripped the runtime scanner's (now removed) ``\\n{5,}`` injection
heuristic — VibeSOP flagged its own generated stub as possibly tampered.
The template now if-guards empty sections and ``render_skill_md`` collapses
3+ blank lines defensively; these tests pin both layers.
"""

from __future__ import annotations

import re

from vibesop.adapters._content import render_skill_md
from vibesop.security.scanner import SecurityScanner


def _minimal_skill(**overrides: object) -> dict[str, object]:
    skill: dict[str, object] = {
        "id": "superpowers/optimize",
        "name": "superpowers/optimize",
        "description": "Performance optimization and profiling guidance.",
        "skill_type": "prompt",
    }
    skill.update(overrides)
    return skill


def test_stub_without_trigger_when_has_no_blank_runs() -> None:
    rendered = render_skill_md(_minimal_skill())

    assert not re.search(r"\n{4,}", rendered), (
        "generated stub must not ship 3+ consecutive blank lines"
    )


def test_stub_without_trigger_when_omits_empty_section_header() -> None:
    rendered = render_skill_md(_minimal_skill())

    assert "## When to Use" not in rendered, "empty section header must not render"


def test_stub_with_trigger_when_renders_section() -> None:
    rendered = render_skill_md(_minimal_skill(trigger_when="Use when profiling."))

    assert "## When to Use" in rendered
    assert "Use when profiling." in rendered
    assert not re.search(r"\n{4,}", rendered)


def test_generated_stub_passes_runtime_security_scan() -> None:
    """End-to-end guard for the incident: whatever the generator emits for a
    contentless registry entry must be injectable (scan-safe)."""
    rendered = render_skill_md(_minimal_skill())

    result = SecurityScanner().scan(rendered)
    assert result.safe, f"stub flagged unsafe: {result.summary}"
