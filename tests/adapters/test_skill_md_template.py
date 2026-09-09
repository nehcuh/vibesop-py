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
from pathlib import Path

from vibesop.adapters._content import generate_fallback_skill_content, render_skill_md
from vibesop.security.scanner import SecurityScanner
from vibesop.spec import SkillSpec


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


class TestDisableModelInvocationPreserved:
    """A skill declared explicit-only (``disable_model_invocation=True``,
    e.g. grill-me) must keep that flag in every generated platform copy.

    Both fallback generators used to drop it: the deployed stub then looked
    auto-invocable to platform-native skill loaders, silently breaking the
    人工点名 contract (pinned 2026-09-09).
    """

    def test_render_skill_md_preserves_flag_when_set(self) -> None:
        rendered = render_skill_md(_minimal_skill(disable_model_invocation=True))

        frontmatter = rendered.split("---")[1]
        assert "disable-model-invocation: true" in frontmatter

    def test_render_skill_md_omits_flag_when_unset(self) -> None:
        rendered = render_skill_md(_minimal_skill())

        assert "disable-model-invocation" not in rendered

    def test_fallback_content_preserves_flag_when_set(self) -> None:
        skill = SkillSpec(
            id="mattpocock/grill-me",
            name="grill-me",
            description="Interview the user relentlessly about a plan.",
            disable_model_invocation=True,
        )

        stub = generate_fallback_skill_content(skill)

        frontmatter = stub.split("---")[1]
        assert "disable-model-invocation: true" in frontmatter

    def test_fallback_content_omits_flag_when_unset(self) -> None:
        skill = SkillSpec(
            id="superpowers/optimize",
            name="optimize",
            description="Performance optimization and profiling guidance.",
        )

        stub = generate_fallback_skill_content(skill)

        assert "disable-model-invocation" not in stub

    def test_fallback_stub_flag_roundtrips_through_parser(self, tmp_path: Path) -> None:
        """The emitted stub must parse back as explicit-only — the flag is
        only real if the skill parser honors it."""
        from vibesop.core.skills.parser import parse_skill_md

        skill = SkillSpec(
            id="mattpocock/grill-me",
            name="grill-me",
            description="Interview the user relentlessly about a plan.",
            disable_model_invocation=True,
        )
        stub = generate_fallback_skill_content(skill)
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(stub, encoding="utf-8")

        parsed = parse_skill_md(skill_file)

        assert parsed is not None
        assert parsed.disable_model_invocation is True
